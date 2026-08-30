#!/usr/bin/env python3
"""Fail if the viewer's copy of the pipeline's tool tables has drifted.

`viewer/api/stores.py` keeps a written-out copy of `BOARD_TOOLS`, `BOARD_SERVERS` and
`BOARD_AGENT_NAMES` because the viewer runs in its own virtualenv and cannot import
`pipeline_core` (that needs agentic_core). A copy is fine; a copy nobody checks is not —
the pipeline would change and only the picture would go stale, which is exactly the kind
of quietly-wrong output this project keeps having to dig out.

Run with the *core* interpreter, which can import both sides::

    ../../agentic-core/.venv/bin/python check_definitions.py

↑ 뷰어가 들고 있는 "파이프라인 도구 표 사본"이 **원본과 어긋났으면 실패하는** 검사기다.

  왜 사본이 있는가: `viewer/api/stores.py` 는 `BOARD_TOOLS`, `BOARD_SERVERS`,
  `BOARD_AGENT_NAMES` 를 손으로 적어 둔 사본으로 갖고 있다. 뷰어는 자기만의
  virtualenv 에서 돌기 때문에 `pipeline_core` 를 import 할 수 없기 때문이다
  (그건 agentic_core 가 필요하다).

  사본 자체는 괜찮다. **아무도 안 보는 사본이 문제다** — 파이프라인이 바뀌면 그림만
  조용히 낡아 버린다. 이 프로젝트가 계속 파내야 했던 "조용히 틀린 출력"이 바로 그것이다.
  그래서 이 파일이 정기적으로 둘을 맞대 본다.

  **core 인터프리터로 돌려야 한다.** 양쪽을 다 import 할 수 있는 건 그쪽뿐이다::

      ../../agentic-core/.venv/bin/python check_definitions.py

==============================================================================
 이 파일을 읽는 법
==============================================================================

 무엇을 하는 파일인가
   파이프라인의 진짜 정의(`pipeline_core`)와 뷰어가 베껴 둔 대체 표(`stores.py` 의
   `_pipeline_definitions()` 안 fallback)를 대조한다. 어긋나면 종료 코드 1,
   pipeline_core 를 못 읽으면 2, 전부 일치하면 0.

 주요 함수
   _copy_from_stores()  stores.py 를 **import 하지 않고 파싱해서** 사본만 꺼낸다
   main()               세 표를 대조하고, 이어서 장면 자리·도구 매핑까지 확인한다

 검사 항목 네 가지
   1. BOARD_TOOLS       단계별로 어떤 도구를 쓰는가
   2. BOARD_SERVERS     단계별로 어떤 MCP 서버에 붙는가
   3. BOARD_AGENT_NAMES 단계 → agents 테이블의 이름
   4. 장면 자리 / 도구→저장소  모든 단계에 HOME·라벨이 있고, 모든 도구에 저장소가 있는가

 놓치기 쉬운 핵심
   ★ `_copy_from_stores` 가 **import 대신 ast 파싱**을 쓰는 이유. import 를 하면
     stores.py 안의 try 블록이 성공해서 *진짜* 정의가 로드되고, 결국 원본을 원본과
     비교하는 꼴이 된다 — 늘 통과하는 무의미한 검사가 된다. 그래서 소스 코드를
     글자 그대로 읽어 fallback 쪽 값만 뽑아낸다.
   ★ 3번까지만 보면 안 된다. 4번(장면 자리)이 없으면 단계가 새로 생겼을 때
     그림에서 캐릭터 하나가 **말없이 사라진다.**
==============================================================================
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
SANDBOX = HERE.parent
# ↑ HERE = viewer/ , SANDBOX = 그 위 (memstara/). pipeline_core 가
#   sandbox 루트에 있으므로 나중에 sys.path 에 SANDBOX 를 끼워 넣는다.


def _copy_from_stores() -> dict[str, object]:
    """Read the fallback tables out of stores.py without importing it.

    Parsing rather than importing keeps this honest: importing would let the *real*
    definitions load and the comparison would compare them with themselves.

    ↑ stores.py 를 **import 하지 않고** 대체 표만 읽어 낸다.

    import 이 아니라 파싱을 하는 것이 이 검사를 정직하게 만든다: import 를 하면
    *진짜* 정의가 로드돼 버리고, 그러면 원본을 원본과 비교하게 된다 — 무조건
    통과하는 가짜 검사가 된다.
    """
    tree = ast.parse((HERE / "api" / "stores.py").read_text(encoding="utf-8"))
    # ↑ 소스를 문법 트리로만 읽는다. 실행은 전혀 하지 않는다.
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_pipeline_definitions")
    # ↑ `_pipeline_definitions` 함수 노드를 찾아서,
    ret = [n for n in ast.walk(fn) if isinstance(n, ast.Return)][-1]
    # ↑ 그 안의 **마지막** return 을 집는다. 첫 return 은 try 안의 "진짜 정의를
    #   그대로 돌려주는" 쪽이고, 마지막 return 이 except 절의 **대체 표**다.
    #   `literal_eval` 은 dict/set/str 같은 리터럴만 계산하므로 코드가 실행될 위험이 없다.
    tools, servers, names = ast.literal_eval(ret.value)
    return {"tools": tools, "servers": servers, "names": names}


def main() -> int:
    # ↑ 종료 코드가 곧 결과다: 0 전부 일치 / 1 어긋남 / 2 pipeline_core 를 못 읽음.
    #   CI 나 셸에서 그대로 실패로 잡을 수 있게 하려는 것이다.
    sys.path.insert(0, str(SANDBOX))
    # ↑ 여기서 진짜 파이프라인 정의를 가져온다. 실패하면 2번(= "검사를 못 했다")로
    #   끝내지, 1번(= "어긋났다")로 끝내지 않는다. 둘을 섞으면 인터프리터를 잘못
    #   골랐을 뿐인데 정의가 깨진 줄 알게 된다.
    try:
        from pipeline_core import BOARD_AGENT_NAMES, BOARD_SERVERS, BOARD_TOOLS
    except Exception as e:  # noqa: BLE001
        print(f"  pipeline_core 를 못 읽었다 — core 인터프리터로 실행하십시오: {e}")
        return 2

    copy = _copy_from_stores()
    # ↑ 아래 checks:  (이름, 진짜 정의, 뷰어 사본) 세 쌍. dict() 로 감싸는 이유는 파이프라인 쪽이
    #   MappingProxy 같은 다른 타입일 수도 있어서 — 그러면 `==` 가 내용이 같아도
    #   거짓이 되어 없는 불일치를 만들어 낸다.
    checks = [
        ("BOARD_TOOLS", dict(BOARD_TOOLS), copy["tools"]),
        ("BOARD_SERVERS", dict(BOARD_SERVERS), copy["servers"]),
        ("BOARD_AGENT_NAMES", dict(BOARD_AGENT_NAMES), copy["names"]),
    ]

    bad = False
    # ↑ 첫 불일치에서 멈추지 않고 **끝까지 다 돌면서** 어긋난 항목을 전부 출력한다.
    #   고치는 사람이 한 번에 다 보고 고칠 수 있게 하려는 것이다.
    for label, real, mirror in checks:
        if real == mirror:
            print(f"  {label:20} 일치")
            continue
        bad = True
        print(f"  {label:20} ⛔ 어긋남")
        for key in sorted(set(real) | set(mirror)):
            if real.get(key) != mirror.get(key):
                # ↑ 어느 쪽에만 있는 키도 잡히도록 합집합을 돌면서 get() 으로 비교한다.
                #   파이프라인 값과 뷰어 값을 위아래로 나란히 찍어 준다.
                print(f"     {key}: 파이프라인 {real.get(key)}")
                print(f"     {' ' * len(key)}  뷰어     {mirror.get(key)}")

    # The scene also needs a place and a home for every stage, or a character would be
    # silently dropped from the drawing.
    #
    # ↑ 장면(scene)에는 단계마다 **자리(HOME)와 이름표(AGENT_LABELS)**가 있어야 한다.
    #   없으면 그 캐릭터는 에러도 없이 그림에서 그냥 빠진다. 표 세 개가 일치해도
    #   이 검사가 없으면 "새 단계가 생겼는데 화면엔 안 보이는" 상태를 놓친다.
    sys.path.insert(0, str(HERE / "api"))
    import stores  # noqa: PLC0415
    # ↑ 여기서는 stores 를 **진짜로 import 한다.** 위(_copy_from_stores)와 목적이
    #   다르기 때문이다: 위는 "베껴 둔 표"를 봐야 했지만, 여기서는 HOME·AGENT_LABELS·
    #   store_of() 같은 **뷰어의 실제 동작**을 확인해야 한다.

    # `real` is rebound by the loop above; name the table we actually mean.
    stages = set(BOARD_TOOLS)
    # ↑ 위 for 문에서 `real` 이라는 이름이 계속 덮어써졌으므로, 여기서는 뜻이 분명한
    #   BOARD_TOOLS 를 직접 쓴다. (원 주석이 지적하는 함정이 바로 이것)
    missing_home = stages - set(stores.HOME)
    missing_label = stages - set(stores.AGENT_LABELS)
    if missing_home or missing_label:
        bad = True
        print(f"  장면 자리            ⛔ 빠진 단계 home={missing_home} label={missing_label}")
    else:
        print(f"  장면 자리            일치 — 단계 {len(stores.HOME)}개 전부 자리와 이름이 있다")

    every_tool = {t for ts in BOARD_TOOLS.values() for t in ts} | {"read_board", "count_waiting"}
    # ↑ 단계들이 쓰는 모든 도구 + 아무 단계에도 안 붙은 두 도구.
    #   `read_board` 는 구동 스크립트 몫이고 `count_waiting` 은 아무도 안 쓰지만,
    #   그래도 저장소 매핑은 있어야 한다 — 화면의 "창문" 목록에 나와야 하기 때문이다.
    unmapped = {t for t in every_tool if stores.store_of(t) == "unknown"}
    # ↑ `store_of` 가 "unknown" 을 돌려주면 그 도구 호출은 화면에서 **어느 장소도
    #   밝히지 못한다.** 조용히 사라지는 대신 여기서 걸리게 해 둔다.
    if unmapped:
        bad = True
        print(f"  도구→저장소          ⛔ 매핑 없는 도구 {sorted(unmapped)}")
    else:
        print(f"  도구→저장소          일치 — 도구 {len(every_tool)}개 전부 저장소가 있다")

    print("\n  " + ("⛔ 어긋남 — stores.py 의 대체 표를 고치십시오" if bad else "전부 일치"))
    return 1 if bad else 0


if __name__ == "__main__":
    # ↑ 반환값을 그대로 종료 코드로 쓴다.
    raise SystemExit(main())
