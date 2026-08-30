"""Two connection pools, deliberately independent.

The board lives in Memstara's database, the agent run history in core's. They were
split apart on 2026-08-17 precisely so one going down does not take the other with
it — so the viewer must not undo that by treating them as one source. Each pool is
acquired separately and each query is wrapped by `guarded`, which turns an
unreachable database into a reported condition rather than a 500.

Read-only by permission, not by convention: the account is `memstara_viewer`, which
holds SELECT and nothing else. Verified — UPDATE and DELETE are refused.

↑ 데이터베이스 연결 풀 두 개. **서로 완전히 남남인 것이 설계다.**

  판(blackboard)은 Memstara 쪽 DB에 있고, 에이전트 실행 이력은 core 쪽 DB에 있다.
  2026-08-17 에 일부러 둘을 갈라 놓았다 — **한쪽이 죽어도 다른 쪽은 살아 있게**
  하려는 것이다. 그러니 뷰어가 둘을 한 덩어리로 다뤄서 그 결정을 도로 무르면 안 된다.
  풀은 각각 따로 잡고, 질의는 전부 `guarded` 로 감싼다. `guarded` 덕분에 "DB에 못
  붙었다"가 500 에러가 아니라 **보고되는 상태**가 된다.

  읽기 전용은 관습이 아니라 **권한**으로 막혀 있다. 접속 계정 `memstara_viewer` 는
  SELECT 권한만 있다. 실제로 확인했다 — UPDATE·DELETE 는 거부된다.
  (코드가 조심해서가 아니라 DB가 막아 주는 것이라, 실수로도 못 쓴다.)

==============================================================================
 이 파일을 읽는 법
==============================================================================

 무엇을 하는 파일인가
   서로 독립된 두 PostgreSQL 에 붙는 연결 풀을 관리한다. 한쪽 DB가 죽어도 뷰어
   전체가 죽지 않도록, 실패를 예외가 아니라 `Health` 라는 "상태 보고"로 바꾼다.
   읽기 전용 계정으로만 붙기 때문에 이 파일을 거쳐 나가는 어떤 질의도 쓰기를 못 한다.

 주요 등장인물
   MEMSTARA_DSN_DEFAULT  판·결과표가 있는 DB (memstara-postgres:5463)
   CORE_DSN_DEFAULT      에이전트·실행이력 DB (agentic-core-postgres:5453)
   _dsn()                환경변수에서 접속 문자열을 읽고 SQLAlchemy 접두사를 떼어 낸다
   Health                마지막 시도에서 어느 DB가 응답했는지, 아니면 왜 못 했는지
   Pools                 풀 두 개를 들고 있는 그릇
   Pools._pool()         첫 사용 시점에 풀을 만든다 (지연 생성)
   Pools.guarded()       ★ 이 파일의 핵심. 질의를 감싸서 실패를 fallback 으로 바꾼다
   pools                 모듈 전역 인스턴스. 다른 파일은 전부 이것 하나를 쓴다

 놓치기 쉬운 핵심
   1. 풀을 **import 시점이 아니라 첫 사용 시점에** 만든다. import 때 만들면 core DB가
      꺼져 있을 때 뷰어가 아예 못 뜬다 — 분리해 놓은 의미가 사라진다.
   2. `guarded` 는 예외를 **삼킨다.** 이게 맞다. "판은 보여 주고 core 는 연결 안 됨이라고
      말하는 화면"이 "데이터 절반이 없어서 빈 페이지"보다 훨씬 쓸모 있다.
   3. 실패하면 그 풀을 **None 으로 버린다.** 죽은 소켓을 재사용하지 않고 다음 폴링
      때 새로 붙기 위해서다. 이걸 빼먹으면 DB가 살아나도 뷰어는 계속 죽었다고 한다.
   4. 성공했을 때 health 를 다시 True 로 **되돌리는 코드가 있다.** 없으면 한 번 실패한
      DB가 영원히 "죽음"으로 표시된다.
==============================================================================
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

import asyncpg

T = TypeVar("T")

MEMSTARA_DSN_DEFAULT = "postgresql://memstara_viewer:viewer@localhost:5463/memstara"
CORE_DSN_DEFAULT = "postgresql://memstara_viewer:viewer@localhost:5453/agentic_core"
# ↑ 두 DB의 기본 접속 문자열. 포트가 다르다는 점이 곧 "완전히 다른 서버"라는 뜻이다.
#   5463 = 판·결과표(memstara) / 5453 = 에이전트·실행이력(agentic_core).
#   Docker 로 띄우면 환경변수가 이 기본값을 덮어쓴다.


def _dsn(env_name: str, default: str) -> str:
    # ↑ 환경변수에서 접속 문자열을 읽되, 비어 있거나 공백뿐이면 기본값을 쓴다.
    #   `re.sub` 는 `postgresql+asyncpg://` 같은 SQLAlchemy 식 접두사를 `postgresql://`
    #   로 되돌린다. 다른 곳(파이프라인 등)에서 쓰던 DSN 을 그대로 복사해 와도
    #   asyncpg 가 받아들이도록 하려는 배려다.
    url = os.environ.get(env_name, "").strip() or default
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


@dataclass
class Health:
    """Which stores answered on the last attempt, and why not if they did not."""

    # ↑ 마지막 시도에서 어느 저장소가 응답했는지, 응답 못 했다면 그 이유는 무엇인지.
    #
    #   이게 왜 dataclass 로 따로 있냐면 — 실패를 **예외로 던지지 않고 값으로 들고
    #   다니기** 위해서다. 화면은 "core: 연결 안 됨"이라고 사람에게 보여 줘야 하고,
    #   그러려면 실패가 어딘가에 남아 있어야 한다.
    #   기본값이 True 인 것도 의도적이다: 아직 한 번도 안 붙어 봤으면 "죽었다"고
    #   단정하지 않는다.

    memstara: bool = True
    core: bool = True
    memstara_error: str = ""
    core_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        # ↑ 그대로 JSON 으로 나가는 모양. 프론트엔드가 `health.core.up` 으로 읽는다.
        return {
            "memstara": {"up": self.memstara, "error": self.memstara_error},
            "core": {"up": self.core, "error": self.core_error},
        }


class Pools:
    # ↑ 풀 두 개를 들고 있는 그릇. 인스턴스는 파일 맨 아래 `pools` 하나뿐이고,
    #   main.py·scene.py 는 전부 그 하나를 가져다 쓴다.
    def __init__(self) -> None:
        self._memstara: asyncpg.Pool | None = None
        self._core: asyncpg.Pool | None = None
        self.health = Health()

    async def close(self) -> None:
        # ↑ 앱이 내려갈 때(main.py 의 lifespan) 호출된다. 아직 안 만들어진 풀은
        #   None 이라 건너뛴다. 닫은 뒤 None 으로 되돌려 놓는 것이 중요하다 —
        #   그래야 다시 뜰 때 `_pool` 이 새로 만든다.
        for pool in (self._memstara, self._core):
            if pool is not None:
                await pool.close()
        self._memstara = self._core = None

    async def _pool(self, which: str) -> asyncpg.Pool:
        """Create the pool on first use and keep it.

        Lazily, because the viewer has to start even when a database is down — that is
        the whole point of the split. A pool built at import time would make an
        unreachable core database a startup crash.

        ↑ 풀을 **처음 쓸 때 만들어서** 계속 들고 있는다.

        왜 미리 안 만드냐면 — DB 하나가 꺼져 있어도 뷰어는 떠야 하기 때문이다.
        그게 두 DB 를 갈라 놓은 이유 그 자체다. import 시점에 풀을 만들면
        core DB 가 안 떠 있을 때 **뷰어가 아예 시작을 못 한다.**
        """
        attr = f"_{which}"
        pool = getattr(self, attr)
        if pool is None:
            dsn = (
                _dsn("MEMSTARA_VIEWER_DSN", MEMSTARA_DSN_DEFAULT)
                if which == "memstara"
                else _dsn("CORE_VIEWER_DSN", CORE_DSN_DEFAULT)
            )
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, timeout=5,
                                             command_timeout=10)
            # ↑ 위 create_pool: 풀 크기를 1~4로 작게 잡았다. 뷰어는 2초마다 한 번 폴링하는 읽기
            #   전용 앱이라 커넥션이 많이 필요 없다. timeout=5 는 "붙는 데" 걸리는
            #   한계, command_timeout=10 은 "질의 하나"의 한계 — 둘 다 있어야
            #   느린 DB가 화면 전체를 붙잡아 두지 않는다.
            setattr(self, attr, pool)
        return pool

    async def guarded(self, which: str, fn: Callable[[asyncpg.Connection], Awaitable[T]],
                      fallback: T) -> T:
        """Run *fn* against one database; on any failure record it and return *fallback*.

        Swallowing the exception is right here: a viewer that shows the board and says
        "core is unreachable" is more useful than one that shows a blank page because
        half its data is missing.

        ↑ *fn* 을 DB 하나에 대고 실행한다. **어떤 이유로든 실패하면** 그 사실을
        기록하고 *fallback* 을 대신 돌려준다.

        여기서 예외를 삼키는 것은 옳다: "판은 보여 주면서 core 는 연결이 안 된다고
        말해 주는 화면"이 "데이터 절반이 없다는 이유로 새하얀 화면"보다 훨씬 쓸모
        있기 때문이다. 즉 이 함수가 **부분 실패를 부분 화면으로 바꿔 주는 장치**다.
        """
        try:
            pool = await self._pool(which)
            async with pool.acquire() as conn:
                result = await fn(conn)
        except Exception as e:  # noqa: BLE001 - every failure is the same to a reader
            # ↑ 예외 종류를 가리지 않는다. 보는 사람 입장에서 "연결 거부"든 "인증
            #   실패"든 "질의 시간 초과"든 결과는 똑같이 "이 DB 는 지금 못 읽는다"다.
            #   그래서 하나로 뭉뚱그린다. 대신 종류 이름과 메시지는 200자까지 남겨서
            #   화면에 이유를 띄운다.
            msg = f"{type(e).__name__}: {e}"[:200]
            if which == "memstara":
                self.health.memstara, self.health.memstara_error = False, msg
            else:
                self.health.core, self.health.core_error = False, msg
            # Drop the pool so the next tick reconnects instead of reusing dead sockets.
            #
            # ↑ 실패한 풀은 **버린다.** 죽은 소켓을 계속 재사용하면 DB 가 살아나도
            #   뷰어는 영영 "죽었다"고 표시한다. None 으로 되돌려 놓으면 다음 폴링
            #   때 `_pool` 이 새 풀을 만들어 자동으로 복구된다.
            setattr(self, f"_{which}", None)
            return fallback
        # ↑ 여기까지 왔으면 성공. health 를 True 로 **되돌려 놓는다.**
        #   이 두 줄이 없으면 한 번 실패한 DB 가 영원히 빨간불로 남는다.
        if which == "memstara":
            self.health.memstara, self.health.memstara_error = True, ""
        else:
            self.health.core, self.health.core_error = True, ""
        return result


pools = Pools()
# ↑ 모듈 전역 인스턴스 하나. 다른 파일은 `from db import pools` 로 이것만 쓴다.
#   풀을 한 군데서만 들고 있어야 연결 수가 예측 가능해진다.
