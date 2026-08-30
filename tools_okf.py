#!/usr/bin/env python3
"""Core's OKF server, plus a reading surface that suits a real literature bundle.

Registered in place of `python -m agentic_core.mcp_servers.okf`. Core's tools are run
unchanged — nothing here reimplements them, and nothing here removes them. Two things
are added on top:

1. One PyYAML behaviour is turned off so `list_concepts` stops failing (below).
2. Three reading tools — `okf_list_domains`, `okf_search`, `okf_read` — that read the
   same bundle the way a consumer of it needs to. See "The reading surface" further
   down for what core's three read tools do to a 142-paper bundle.

↑ 이 파일은 core 의 OKF 서버를 **대신 실행**한다. 대신이라고 해서 갈아엎는 것이
  아니다. core 의 도구는 손대지 않은 채 그대로 등록돼 있고, 여기서는 두 가지만
  얹는다 — (1) PyYAML 의 동작 하나를 꺼서 core 의 `list_concepts` 가 죽지 않게
  하고, (2) 실제 논문 번들을 읽기에 맞는 도구 세 개를 더한다.

The defect
----------
`list_concepts` fails on any bundle core did not write itself::

    Error executing tool list_concepts: Object of type datetime is not JSON serializable

Three steps get there:

1. A concept file carries a timestamp, unquoted, which is ordinary YAML::

       generated:
         at: 2026-08-10T00:00:00Z

2. YAML has a timestamp type, so `safe_load` returns a `datetime` — not a string.
3. `list_concepts` copies `generated`, `verified` and `status` straight out of the
   frontmatter (okf.py:271-272) and hands the result to `json.dumps` (okf.py:276).
   JSON has no date type and no `default=` was given, so it raises.

`search_concepts` returns only id/type/title/tags (okf.py:305-312), which is why search
works and only the listing breaks — the contrast is what identified the cause.

Core never hits this on its own output: it writes `datetime.now(UTC).isoformat()`, a
*string* (okf.py:373), and `yaml.safe_dump` quotes it (okf.py:136), so it round-trips as
a string. The failure needs a bundle written by somebody else — which is every bundle
that matters here. Measured on the sample bundle: 29 of 31 files carry such a timestamp,
and one is enough, because `json.dumps` serialises the whole result at once.

↑ 고장 난 경위를 우리말로 풀면 이렇다.

  1. 논문 파일 머리말에 `at: 2026-08-10T00:00:00Z` 처럼 따옴표 없는 날짜가 있다.
     그냥 평범한 YAML 이다.
  2. YAML 에는 "날짜" 라는 타입이 있어서, 읽으면 문자열이 아니라 파이썬의
     `datetime` 객체가 나온다.
  3. `list_concepts` 는 그 값을 그대로 JSON 으로 바꾸려 한다. JSON 에는 날짜
     타입이 없으므로 거기서 터진다.

  `search_concepts` 는 id/type/title/tags 만 돌려주기 때문에 날짜를 건드리지
  않는다. 그래서 **검색은 되는데 목록만 죽는** 이상한 증상이 나왔고, 바로 그
  대비가 원인을 짚어 줬다.

  core 자신이 만든 번들에서는 이 일이 안 생긴다. core 는 날짜를 문자열로 적고
  따옴표까지 붙여 두기 때문이다. 즉 **남이 만든 번들**에서만 터지는데, 우리가
  쓰는 번들은 전부 남이 만든 것이다. 표본 번들에서는 31개 중 29개가 이런 날짜를
  갖고 있었다. 하나만 있어도 전체가 죽는다 — JSON 변환은 결과를 통째로 하니까.

The fix here
------------
Remove PyYAML's implicit resolver for timestamps, so an unquoted ISO date loads as the
string it was written as. That removes the `datetime` at the source rather than patching
each tool that trips over one, so no core logic is copied and every tool benefits.

Nothing else changes: integers, booleans and quoted strings resolve exactly as before,
and JSON has no date type anyway, so a consumer could not have received one.

Report upstream regardless — `json.dumps(..., default=str)` at okf.py:276 would fix it
for everyone. This only fixes it for us.

↑ 고친 방법: PyYAML 에게 "따옴표 없는 날짜를 날짜로 알아보지 말라"고 일러 둔다.
  그러면 적혀 있던 그대로 문자열로 읽힌다. 도구마다 따라다니며 땜질하는 대신
  **원인 한 곳**을 막는 방식이라, core 코드를 한 줄도 베끼지 않고 모든 도구가
  같이 낫는다.

  다른 것은 그대로다. 숫자·참거짓·따옴표 친 문자열은 전과 똑같이 읽힌다. 어차피
  JSON 에는 날짜 타입이 없으니 이 도구를 쓰는 쪽이 날짜 객체를 받았을 리도 없다.

  다만 이건 **우리만** 고친 것이다. 근본 수정은 core 쪽에서 해야 하므로 위로
  보고는 따로 한다.

==============================================================================
 이 파일을 읽는 법
==============================================================================

 이 파일은 **지식원(OKF) 도구 서버**다. core 가 만든 OKF 서버를 그대로 켜 두고,
 그 위에 읽기 도구 세 개를 얹는다. 논문 번들(마크다운 묶음)을 목록으로 훑고,
 검색하고, 한 편씩 열어 보는 창구 노릇을 한다.

 주요 함수·클래스
 ----------------
 disable_yaml_timestamps()  YAML 이 날짜를 datetime 으로 바꾸는 기능을 끈다.
                            core 의 `list_concepts` 가 죽던 원인을 뿌리에서 없앤다.
 _Doc                       문서 한 편. 경로·도메인·주소·머리말·본문·검색용 낱말.
 _text / _tag_list          머리말 값을 안전한 문자열 / 태그 목록으로 다듬는다.
 _tokens                    글을 검색용 "낱말"로 쪼갠다. 부분 문자열이 아니다.
 _sections                  본문을 `# 제목` 단위의 절로 나눈다.
 _signature                 번들이 바뀌었는지 싸게 확인하는 도장(파일 수정시각).
 _load(root)                번들 전체를 읽어 문서 목록과 "건너뛴 파일" 목록을 낸다.
 _idf                       낱말마다 가중치. 모든 문서에 있는 낱말은 값이 낮다.
 _index                     한 문서가 응답하는 모든 이름표(주소·PMID·파일명).
 _split                     쉼표로 갈라 공백을 턴다.
 okf_list_domains()  [도구]  도메인 목록과 각 도메인의 문서 수. 가장 먼저 부를 것.
 okf_search()        [도구]  제목·태그·설명·저널로 검색한다. 본문은 보지 않는다.
 okf_read()          [도구]  문서를 통째로, 또는 절 하나만 연다.

 놓치기 쉬운 것
 --------------
 1. 목록은 **도메인 폴더 안만** 훑는다. 루트에서 통째로 glob 하지 않는다.
    그래서 reviewer 의 hiv-suppression 번들이 152장이 아니라 142장으로 나온다 —
    빠진 열 장은 `index.md` 같은 "선반 이름표"이지 근거 문서가 아니다.
 2. 그런데 **평평한 번들**(도메인 폴더가 없이 루트에 .md 가 늘어선 번들)이 있다.
    이 프로젝트의 합성 번들과 NHANES 번들이 그렇다. 폴더만 보는 규칙으로는
    **0장**이 되고, 오류도 안 난다 — 그냥 조용히 비어 있다. 그래서 폴더에서 한
    장도 못 찾으면 루트를 하나의 도메인으로 읽는 갈래가 나중에 붙었다(`_load`).
 3. 검색은 **본문을 색인하지 않는다.** 제목 3.0 · 태그 2.0 · 설명 1.0 ·
    저널 1.0 만 본다. 저자가 일부러 채워 넣은 칸만 믿는다는 뜻이다.
 4. `export_safe` 는 번들에 따옴표 붙은 `"false"` 로 적혀 있다. 파이썬에서
    비어 있지 않은 문자열은 **참**이라, `if export_safe:` 는 항상 통과한다.
    그래서 여기서는 판단하지 않고 **적힌 문자열 그대로** 돌려준다.
"""

from __future__ import annotations

import dataclasses  # _Doc 을 "값만 담는 고정된 상자"로 만들기 위해 쓴다
import json         # 도구는 전부 JSON 문자열을 돌려준다
import math         # 낱말 가중치(idf)에 로그를 쓴다
import pathlib      # 파일 경로. os.path 대신 이쪽을 쓴다
import re           # 낱말 쪼개기와 머리말 패턴에 쓴다
from typing import Any

import yaml         # 머리말(frontmatter)이 YAML 이다

#: PyYAML 이 "이건 날짜다" 라고 붙이는 꼬리표 이름. 아래에서 이 꼬리표를 다는
#: 규칙만 골라 떼어 낸다.
_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


def disable_yaml_timestamps() -> int:
    """Stop `yaml.safe_load` from turning ISO dates into datetimes. Returns the count.

    ↑ 요약: YAML 을 읽을 때 따옴표 없는 날짜(`2026-08-10T00:00:00Z`)를 파이썬
      `datetime` 으로 바꾸지 말고 **적힌 그대로 문자열로** 두게 만든다. 떼어 낸
      규칙의 개수를 돌려준다(보통 2 — 날짜 시작 글자가 여러 가지라 여러 칸에
      등록돼 있다).

      PyYAML 은 "첫 글자 → 그 글자로 시작할 수 있는 타입 규칙 목록" 이라는 표를
      들고 있다. 그 표를 한 칸씩 돌면서 날짜 규칙만 빼고 새 목록으로 갈아 끼운다.
      원본 목록을 그 자리에서 고치지 않고 새로 만들어 넣는 것은, 도는 도중에
      들여다보는 대상을 바꾸지 않기 위해서다.
    """
    removed = 0
    # list(...) 로 한 번 떠 놓는다 — 도는 중에 원래 표를 고치기 때문이다.
    for first_char, resolvers in list(yaml.SafeLoader.yaml_implicit_resolvers.items()):
        # 날짜 꼬리표가 아닌 규칙만 남긴다.
        kept = [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP_TAG]
        removed += len(resolvers) - len(kept)  # 몇 개 뺐는지 센다
        yaml.SafeLoader.yaml_implicit_resolvers[first_char] = kept
    return removed


# 자식 프로세스라 부모 디버거가 안 닿는다. MEMSTARA_DEBUGPY 에 "okf" 가 들어 있을
# 때만 디버거를 기다린다 — 없으면 아무 일도 하지 않는다. debug_hook.py 참고.
from debug_hook import quiet_child, wait_for_debugger

quiet_child()          # 자식이 켜질 때 찍는 잡음 세 가지를 끈다
wait_for_debugger("okf")

# Before importing core's server: it parses nothing at import time, but ordering this
# way means the resolver is already gone no matter when the first parse happens.
#
# ↑ core 서버를 불러오기 **전에** 껐다. core 는 불러오는 시점에 YAML 을 읽지는
#   않지만, 순서를 이렇게 두면 "첫 읽기가 언제 일어나든" 이미 꺼져 있는 것이
#   보장된다. 순서에 기대는 대신 순서를 없애 버리는 셈이다.
disable_yaml_timestamps()

# Core's own helpers are imported rather than copied. `_bundle_root` reads the same
# environment variable with the same error message, and `_parse_concept_file` uses the
# same frontmatter regex — reimplementing either would let the two drift apart while
# both claim to serve "the bundle".
#
# ↑ core 의 도우미 함수를 **베끼지 않고 가져다 쓴다.** `_bundle_root` 는 번들 위치를
#   알려 주고(같은 환경변수, 같은 오류 문구), `_parse_concept_file` 은 한 파일을
#   머리말과 본문으로 가른다. 이걸 여기서 다시 구현하면 언젠가 두 벌이 서로 어긋나면서
#   양쪽 다 "같은 번들을 읽는다"고 주장하게 된다.
#   `mcp` 는 core 가 이미 도구들을 등록해 둔 서버 객체다. 아래에서 여기에 세 개를
#   더 붙인다 — 그래서 core 의 도구도 우리 도구도 한 서버에서 같이 나온다.
from agentic_core.mcp_servers.okf import (  # noqa: E402
    OKFError,
    _bundle_root,
    _parse_concept_file,
    mcp,
)

# --------------------------------------------------------------------------- #
#  The reading surface
# --------------------------------------------------------------------------- #
#
# Core's read tools were written against bundles core itself writes. Measured against
# `shared/hiv-suppression/okf` — 142 papers in 8 domain folders, produced by OKF
# Loremaster — three of them do the wrong thing:
#
#   * `list_concepts` enumerates with `root.rglob("*.md")`, so it reports 152 documents.
#     The extra ten are structure: eight per-domain `index.md`, plus `predictors.md` and
#     `search.md` at the root. The agent reads a shelf label as if it were evidence.
#   * `search_concepts` matches a substring against title + description + **body**. On
#     this bundle `"art"` matches 132 of 142 papers, because of `heart`, `start` and
#     `particular`. `"ai"` and `"n"` match all 142. A search that returns everything has
#     not searched.
#   * `get_concept` returns the whole body. Median body here is 6,678 characters and the
#     longest is 37,933; the 142 bodies together are roughly 271,000 tokens. Opening a
#     handful fills the window with paper text when what was wanted was a conclusion.
#
# The three tools below are the same three afc-forge binds for its `basic` agency
# profile. That set is adopted rather than invented: it is already the minimum that
# works, and matching it means a bundle behaves the same on both sides.
#
# afc-forge is deliberately NOT imported. Its own reader says why, about its own
# situation: the bundle is a contract between two programs that must be able to change
# independently, and borrowing the other side's parser can only ever prove that the
# bundle agrees with itself. The approach is taken; the code is written here.
#
# ↑ 왜 도구를 더 만들었는가 — core 의 읽기 도구 셋은 core 가 스스로 만든 번들을
#   전제로 쓰였다. reviewer 의 hiv-suppression 번들(8개 도메인 폴더, 논문 142장)에
#   대 보면 세 가지 다 어긋난다.
#
#     * `list_concepts` 는 루트에서 통째로 훑어 152장이라고 답한다. 더 나온 열 장은
#       도메인별 `index.md` 여덟 개와 루트의 `predictors.md`·`search.md` 다. 전부
#       선반 이름표이지 근거가 아닌데, 에이전트는 그걸 논문으로 읽는다.
#     * `search_concepts` 는 제목·설명에 **본문까지** 더해 부분 문자열로 맞춰 본다.
#       그래서 `"art"` 가 142장 중 132장에 걸린다 — heart, start, particular 때문이다.
#       `"ai"` 나 `"n"` 은 142장 전부에 걸린다. 전부를 돌려주는 검색은 검색이 아니다.
#     * `get_concept` 은 본문을 통째로 준다. 이 번들의 본문 길이는 중앙값 6,678자,
#       가장 긴 것이 37,933자다. 142장을 다 합치면 대략 27만 토큰이다. 몇 편만 열어도
#       맥락 창이 논문 원문으로 가득 찬다 — 정작 필요했던 건 결론 한 줄인데.
#
#   아래 세 도구는 afc-forge 가 `basic` 프로필에 붙여 두는 바로 그 셋이다. 새로
#   지어낸 게 아니라 **이미 최소한으로 동작하는 조합**을 그대로 따랐다. 그래야 같은
#   번들이 양쪽에서 똑같이 보인다.
#
#   다만 afc-forge 코드를 **가져다 쓰지는 않는다.** 번들은 서로 따로 변해도 되는 두
#   프로그램 사이의 약속이다. 상대편 해석기를 빌려 쓰면 "번들이 자기 자신과 일치한다"는
#   것밖에 확인하지 못한다. 방식만 따르고 코드는 여기에 새로 썼다.

#: 도메인 폴더 안에서 문서로 세지 않을 파일 이름. 그 폴더가 무엇을 담는지 적어 둔
#: 표지 파일이지 근거 문서가 아니다.
_DOMAIN_INDEX = "index.md"

#: 평평한 번들의 루트에서 문서로 세지 않을 이름(확장자 제외).
#:
#: 구조이지 근거가 아니다. Loremaster 가 만든 번들의 관례를 따르고, 사람이 손으로
#: 만든 번들에 흔한 README 도 넣는다.
_ROOT_RESERVED = frozenset({"index", "log", "predictors", "search", "README", "readme"})

#: The curated fields a query is matched against, and what each is worth. These are the
#: fields an author filled in on purpose, so a hit means the bundle says this paper is
#: about that — not that the word appeared once in an abstract. A title match is a
#: stronger statement of aboutness than a journal match, on any bundle.
#:
#: ↑ 검색이 들여다보는 칸과 각 칸의 값어치. **본문은 여기 없다.** 이 네 칸은 저자가
#:   일부러 채워 넣은 칸이라, 걸렸다는 건 "번들이 이 논문은 그것에 관한 것이라고
#:   말한다" 는 뜻이다. 초록 어딘가에 그 단어가 한 번 스쳤다는 뜻이 아니다.
#:   제목에 걸린 것이 저널 이름에 걸린 것보다 강한 신호라서 3.0 대 1.0 이다.
_FIELD_WEIGHTS = {"title": 3.0, "tags": 2.0, "description": 1.0, "journal": 1.0}

#: What a search returns unasked, and the ceiling it may be raised to. A request above
#: the ceiling is clamped and says so, so breadth can be taken without asking anybody.
#:
#: ↑ 안 물어보면 8개를 준다. 더 달라고 하면 20개까지 준다. 20 을 넘겨 달라고 하면
#:   20 으로 깎되 **깎았다고 응답에 적어 준다** — 조용히 줄이면 받은 쪽이 그게
#:   전부인 줄 안다.
_DEFAULT_K = 8
_MAX_K = 20

#: Words, not substrings. This is the whole reason `"art"` stops matching `"heart"`.
#:
#: ↑ 영문자와 숫자가 이어진 덩어리를 하나의 낱말로 본다. 부분 문자열이 아니라
#:   **낱말** 단위로 맞추기 때문에 `"art"` 가 `"heart"` 에 걸리지 않는다.
_TOKEN = re.compile(r"[a-z0-9]+")

#: Small and closed on purpose. A long stopword list starts deciding what is a concept.
#:
#: ↑ 검색에서 뺄 흔한 낱말(the, of, is …). 일부러 짧게, 그리고 더 늘리지 않는다.
#:   불용어 목록이 길어지면 그 목록이 "무엇이 개념인가"를 대신 정하기 시작한다.
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the their "
    "there these this to was were what when which who will with".split()
)

#: A single-hash heading opens a body section. A `##` inside one belongs to it, which is
#: what lets a section carry sub-structure. Every paper in the HIV bundle carries the
#: same five: Bottom line / Predictors reported / Null or non-significant findings /
#: Vocabulary hints / Caveats.
#:
#: ↑ 본문에서 `# ` 로 시작하는 줄이 새 절(section)을 연다. 그 안의 `##` 은 절을
#:   새로 열지 않고 그 절에 딸린 소제목으로 남는다 — 그래야 한 절이 하위 구조를
#:   가질 수 있다. HIV 번들의 논문은 전부 같은 다섯 절을 갖는다:
#:   Bottom line / Predictors reported / Null or non-significant findings /
#:   Vocabulary hints / Caveats.
_HEADING = "# "


@dataclasses.dataclass(frozen=True)
class _Doc:
    """One evidence document: where it is, what it says about itself, and its body.

    ↑ 논문 한 편을 담는 상자. `frozen=True` 라 만든 뒤에는 값을 바꿀 수 없다 —
      캐시에 넣어 두고 여러 번 꺼내 쓰기 때문에, 어디선가 슬쩍 고쳐지는 일이
      없도록 막아 둔 것이다.

      필드 뜻:
        path         파일의 실제 위치
        domain       이 문서가 속한 주제 폴더 이름
        address      이 도구들이 밖에 내주는 id. 폴더가 있으면 "도메인/파일이름",
                     평평한 번들이면 "파일이름"
        fields       머리말(YAML)에 적힌 것 전부 — 제목·태그·저널·PMID 등
        body         머리말 아래 본문 전체
        field_tokens 검색용으로 미리 쪼개 둔 낱말 묶음. 검색할 때마다 다시
                     쪼개면 문서 수만큼 되풀이되므로 읽을 때 한 번만 한다
    """

    path: pathlib.Path
    domain: str
    address: str  # "domain/stem" — the id this surface hands out
    fields: dict[str, Any]
    body: str
    field_tokens: dict[str, frozenset[str]]

    @property
    def summary(self) -> dict[str, Any]:
        """The catalogue row. Scanned many at a time, so it carries no body.

        ↑ 목록·검색 결과에 실리는 "도서 카드" 한 줄. 한 번에 수십 개가 오가므로
          **본문은 일부러 넣지 않는다.** 본문이 필요하면 okf_read 로 따로 연다.
        """
        f = self.fields
        return {
            "id": self.address,
            "title": _text(f.get("title")),
            "domain": self.domain,
            "tags": _tag_list(f.get("tags")),
            "journal": _text(f.get("journal")),
            "published": _text(f.get("published")),
            "strength": _text(f.get("strength")),
            "n": _text(f.get("n")),
            "pmid": _text(f.get("pmid")),
        }


def _text(value: Any) -> str:
    """A frontmatter value as a string, never a bool and never None.

    Values arrive as whatever YAML made of them. Returning the raw object would put a
    `None` or a `dict` into JSON where callers expect a string, and `str(None)` would
    put the word "None" on screen as if it were data.

    ↑ 요약: 머리말에서 꺼낸 값을 **언제나 문자열로** 만들어 준다.

      머리말은 사람이 손으로 쓴 것이라 값이 무엇으로 읽힐지 알 수 없다 — 비어 있을
      수도, 목록일 수도, 표일 수도 있다. 날것 그대로 내보내면 문자열을 기대하던
      쪽에 `None` 이나 표가 가고, 그렇다고 `str(None)` 을 쓰면 화면에 "None" 이라는
      **글자**가 데이터인 척 찍힌다. 그래서 없거나 모양이 안 맞으면 빈 문자열로 준다.
    """
    if value is None:
        return ""          # 값이 없다 → 빈 칸
    if isinstance(value, (list, dict)):
        return ""          # 목록·표는 이 자리에 올 것이 아니다 → 빈 칸
    return str(value).strip()


def _tag_list(value: Any) -> list[str]:
    """태그를 목록으로 만든다.

    머리말에 태그가 두 가지 모양으로 적힌다 — YAML 목록으로 적히기도 하고
    `a, b, c` 처럼 한 줄로 적히기도 한다. 둘 다 받아서 같은 결과를 낸다.
    빈 조각은 버린다.
    """
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value or "").split(",") if p.strip()]


def _tokens(text: str) -> frozenset[str]:
    """글을 검색용 낱말 묶음으로 쪼갠다.

    소문자로 낮추고, 영문자·숫자 덩어리만 뽑고, 흔한 낱말(_STOP)과 한 글자짜리를
    버린다. 순서와 횟수는 버리고 **어떤 낱말이 있었는가**만 남긴다 — 검색에서
    필요한 건 그것뿐이고, 묶음끼리는 교집합 한 번으로 맞춰 볼 수 있다.
    """
    return frozenset(t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1)


def _sections(body: str) -> list[tuple[str, str]]:
    """`(heading, text)` for each `# ` section, in order. Preamble is not a section.

    ↑ 요약: 본문을 `# 제목` 단위로 잘라 (제목, 내용) 쌍의 목록으로 만든다. 파일에
      적힌 순서를 그대로 지킨다.

      첫 `#` 이 나오기 전의 머리 부분은 절로 세지 않는다 — 이름이 없으니 `section=`
      으로 지목할 방법도 없기 때문이다.
    """
    out: list[tuple[str, str]] = []
    heading, buf = "", []      # 지금 모으고 있는 절의 제목과 줄들
    for line in body.splitlines():
        if line.startswith(_HEADING):
            if heading:
                # 새 제목을 만났으니 직전까지 모은 절을 닫는다.
                out.append((heading, "\n".join(buf).strip()))
            heading, buf = line[len(_HEADING) :].strip(), []
        else:
            buf.append(line)
    if heading:
        out.append((heading, "\n".join(buf).strip()))  # 마지막 절 닫기
    return out


def _signature(root: pathlib.Path) -> tuple[tuple[str, int], ...]:
    """A cheap stamp of the bundle's current state — stat only, no reads.

    The bundle is re-read on every tool call otherwise, which on this bundle is a
    megabyte of markdown per call. Caching on the path alone would be wrong: core's
    `create_concept` and `update_concept` are still registered on this same server, so
    a bundle CAN change under us mid-run.

    ↑ 요약: 번들의 "지금 상태"를 싸게 찍은 도장. 파일을 **열지 않고** 이름과 마지막
      수정 시각만 본다. 도장이 지난번과 같으면 다시 읽지 않고 캐시를 쓴다.

      왜 필요한가 — 이게 없으면 도구를 부를 때마다 번들 전체를 다시 읽는다. 이
      번들은 마크다운만 1메가바이트쯤 되므로 한 번 부를 때마다 그만큼을 읽는 셈이다.

      왜 경로만으로 캐시하면 안 되는가 — core 의 `create_concept`·`update_concept`
      가 이 서버에 그대로 등록돼 있다. 즉 실행 도중에 번들이 **바뀔 수 있다.**
      경로만 보면 바뀐 줄 모르고 옛날 내용을 계속 내주게 된다.
    """
    stamps = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith((".", "_")):
            continue   # 숨김 폴더와 `_` 로 시작하는 작업용 폴더는 건너뛴다
        for md in sorted(folder.glob("*.md")):
            # st_mtime_ns 는 나노초 단위 수정 시각. 초 단위보다 촘촘해서 같은 초
            # 안에 두 번 고쳐도 구분된다.
            stamps.append((str(md), md.stat().st_mtime_ns))
    return tuple(stamps)


#: 번들 경로 → (도장, 문서 목록, 건너뛴 파일 목록). 도장이 달라지면 버리고 다시 읽는다.
_CACHE: dict[str, Any] = {}


def _load(root: pathlib.Path) -> tuple[list[_Doc], list[dict[str, str]]]:
    """Every evidence document in the bundle, and every file passed over, by name.

    Enumeration is one level of domain folders — never a glob from the root. A producer
    that drops a root-level sidecar (`predictors.md`, `search.md`) would otherwise be
    read as a document with no domain, and a bundle that is entirely correct would come
    back ten documents too large.

    What was NOT read is returned alongside what was. Silently skipping a malformed file
    is how a bundle comes back short while looking healthy — the caller sees fewer
    documents and no reason to doubt the number.

    ↑ 요약: 번들을 한 번 다 읽어서 (문서 목록, 건너뛴 파일 목록) 두 가지를 낸다.

      **세는 범위** — 도메인 폴더 한 겹 안만 본다. 루트에서 통째로 glob 하지 않는다.
      만드는 쪽이 루트에 곁다리 파일(`predictors.md`, `search.md`)을 떨궈 놓으면,
      통째로 훑을 경우 그게 "도메인 없는 문서"로 잡혀서 멀쩡한 번들이 열 장쯤
      부풀어 보인다.

      **읽지 못한 것도 같이 낸다** — 모양이 깨진 파일을 말없이 건너뛰면, 번들이
      모자란 채로 멀쩡해 보인다. 받는 쪽은 그냥 문서가 적구나 하고 넘어가고,
      숫자를 의심할 이유를 얻지 못한다. 그래서 무엇을 왜 건너뛰었는지 이름까지
      붙여서 돌려준다.

    두 가지 배치를 다 읽는다
    ------------------------
    도메인 폴더가 있는 번들(reviewer 의 `hiv-suppression` 같은)은 위 규칙 그대로 읽는다.

    그런데 **이 프로젝트가 만든 번들은 평평하다** — 도메인 폴더 없이 루트에 `.md` 가
    늘어서 있고, `domain` 필드도 없다. 합성(31장)과 NHANES(21장) 둘 다 그렇다.
    폴더만 보는 규칙으로는 그 번들이 **0장**으로 나오고, 그것도 조용히 나온다.
    실제로 그렇게 만들어 놓고 한동안 몰랐다.

    그래서 폴더에서 아무것도 못 찾으면 **루트를 하나의 도메인으로** 읽는다. 이때만
    `domain` 을 필수에서 뺀다 — 폴더가 없으니 맞춰 볼 이름 자체가 없기 때문이다.
    `title` 은 여전히 필수다. 그것이 검색 표면의 대부분이다.
    """
    key = str(root)
    sig = _signature(root)
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == sig:
        return cached[1], cached[2]   # 도장이 같다 → 파일 하나도 안 건드리고 끝

    docs: list[_Doc] = []                  # 근거로 인정한 문서들
    skipped: list[dict[str, str]] = []     # 읽지 못했거나 규칙에 안 맞은 파일들

    # --- 갈래 1: 도메인 폴더가 있는 번들 (reviewer 의 hiv-suppression 같은) ---
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith((".", "_")):
            continue
        for md in sorted(folder.rglob("*.md")):  # rglob: 하위 폴더도 재귀 탐색
            rel = md.relative_to(root).as_posix()   # 오류 메시지에 쓸 짧은 경로
            if md.name == _DOMAIN_INDEX:
                continue  # the shelf label, not evidence
                          # ↑ 선반 이름표이지 근거가 아니다
            try:
                # core 의 해석기. 파일을 머리말(딕셔너리)과 본문(문자열)로 가른다.
                fields, body = _parse_concept_file(md)
            except (OKFError, OSError, UnicodeDecodeError) as exc:
                # 깨진 파일 하나 때문에 번들 전체가 멈추지는 않게 한다. 대신
                # 무엇을 왜 못 읽었는지 반드시 남긴다.
                skipped.append({"path": rel, "why": str(exc)})
                continue
            title = _text(fields.get("title"))
            # domain: 필드가 없으면 최상위 폴더명을 domain으로 사용
            # (shared의 OKF는 domain: 필드 대신 mechanism_family: 를 씀)
            domain = folder.name
            if not title:
                skipped.append({"path": rel, "why": "no `title` — required field"})
                continue
            docs.append(
                _Doc(
                    path=md,
                    domain=domain,
                    address=md.relative_to(root).with_suffix("").as_posix(),  # 전체 상대경로
                    fields=fields,
                    body=body,
                    # 검색용 낱말은 지금 한 번만 쪼갠다. 검색할 때마다 하면 문서
                    # 수만큼 되풀이된다.
                    field_tokens={
                        "title": _tokens(title),
                        "tags": _tokens(" ".join(_tag_list(fields.get("tags")))),
                        "description": _tokens(_text(fields.get("description"))),
                        "journal": _tokens(_text(fields.get("journal"))),
                    },
                )
            )

    # --- 갈래 2: 평평한 번들 — 도메인 폴더에서 한 장도 못 찾았을 때만. ---
    #
    # 폴더가 있는 번들에서 이 갈래로 오는 일은 없다. 그래서 hiv-suppression 의 142장은
    # 위에서 그대로 나오고, 루트의 predictors.md · search.md 는 계속 제외된다.
    #
    # 조건이 "폴더가 없으면" 이 아니라 "위에서 한 장도 못 건졌으면" 인 점이 중요하다.
    # 폴더가 있는데 그 안이 전부 깨진 경우에도 여기로 오지만, 그때는 skipped 에 이유가
    # 이미 쌓여 있어서 왜 그랬는지 응답만 봐도 드러난다.
    if not docs:
        for md in sorted(root.glob("*.md")):
            if md.stem in _ROOT_RESERVED:
                continue   # 구조 파일이지 근거가 아니다
            rel = md.name
            try:
                fields, body = _parse_concept_file(md)
            except (OKFError, OSError, UnicodeDecodeError) as exc:
                skipped.append({"path": rel, "why": str(exc)})
                continue
            title = _text(fields.get("title"))
            if not title:
                skipped.append({"path": rel, "why": "no `title` — the one required field"})
                continue
            # 평평한 번들에는 맞춰 볼 폴더 이름이 없다. `domain` 이 적혀 있으면 쓰고,
            # 없으면 번들 이름을 쓴다 — 목록에 빈 칸이 뜨지 않게.
            domain = _text(fields.get("domain")) or root.name
            docs.append(
                _Doc(
                    path=md,
                    domain=domain,
                    address=md.stem,        # 평평하므로 `도메인/이름` 이 아니라 이름 그대로
                    fields=fields,
                    body=body,
                    field_tokens={
                        "title": _tokens(title),
                        "tags": _tokens(" ".join(_tag_list(fields.get("tags")))),
                        "description": _tokens(_text(fields.get("description"))),
                        "journal": _tokens(_text(fields.get("journal"))),
                    },
                )
            )

    # 도장과 함께 넣어 둔다. 다음 호출은 도장만 비교하고 끝난다.
    _CACHE[key] = (sig, docs, skipped)
    return docs, skipped


def _idf(docs: list[_Doc]) -> dict[str, float]:
    """How much each word is worth. A word in every paper distinguishes nothing.

    ↑ 요약: 낱말마다 "이 낱말이 걸리면 얼마나 의미 있는가"를 매긴다.

      원리는 간단하다. 몇 편에 나오는가를 세고, **적게 나오는 낱말일수록 높은 값**을
      준다. 예컨대 HIV 번들에서 'hiv' 는 거의 모든 논문에 있으니 그게 걸려도 골라낸
      것이 없다 — 값이 낮다. 반대로 'tenofovir' 는 몇 편에만 있으니 걸리면 그 몇 편을
      진짜로 지목한 것이다 — 값이 높다.

      정보검색에서 idf(inverse document frequency)라 부르는 흔한 방법이다.
    """
    n = len(docs) or 1          # 0으로 나누지 않도록 최소 1
    df: dict[str, int] = {}     # 낱말 → 그 낱말이 나온 문서 수
    for doc in docs:
        # 네 칸(제목·태그·설명·저널)의 낱말을 다 합친 뒤 센다. 한 문서 안에서
        # 여러 칸에 나와도 "한 문서"로만 센다.
        for token in frozenset().union(*doc.field_tokens.values()):
            df[token] = df.get(token, 0) + 1
    # 로그를 씌워 값 차이가 지나치게 벌어지지 않게 누른다.
    return {t: math.log(1.0 + n / c) for t, c in df.items()}


def _index(docs: list[_Doc]) -> dict[str, list[_Doc]]:
    """Every name a document answers to, lowercased.

    A paper is referred to by its PMID in one breath and its filename in the next. One
    id would be tidier and would send the agent back to look it up again.

    ↑ 요약: 한 문서를 부르는 **모든 이름**을 모아 둔 전화번호부. 주소, 파일 이름,
      확장자 뺀 파일 이름, 머리말의 `id`, 그리고 PMID 까지 전부 통한다.

      id 를 하나로 정해 두면 코드는 깔끔하다. 대신 방금 검색 결과에서 PMID 를 본
      에이전트가 그걸로 열려다 실패해서 다시 찾아보러 가야 한다. 부르는 쪽을
      편하게 하는 편을 택했다.

      값이 목록인 이유는 같은 이름에 두 문서가 걸릴 수 있기 때문이다. 그런 경우
      okf_read 는 아무거나 고르지 않고 "모호하다"고 후보를 알려 준다.
    """
    by_ref: dict[str, list[_Doc]] = {}
    for doc in docs:
        # 집합으로 감싸서 같은 이름이 겹치면 한 번만 등록되게 한다
        # (예: 평평한 번들에서는 address 와 stem 이 같다).
        for key in {
            doc.address.lower(),
            doc.path.name.lower(),
            doc.path.stem.lower(),
            _text(doc.fields.get("id")).lower(),
            _text(doc.fields.get("pmid")).lower(),
        }:
            if key:   # 머리말에 id 나 pmid 가 없으면 빈 문자열이므로 거른다
                by_ref.setdefault(key, []).append(doc)
    return by_ref


def _split(raw: str) -> list[str]:
    """Split on commas, trim each piece, drop the empties.

    Used for okf queries, tags and document references — none of which contain a
    comma, which is the only reason splitting on one is safe here.

    This used to say it was deliberately aligned with `slice_columns`, so that
    both tools took input the same way. It is not aligned any more, on purpose:
    158 of the cohort's 1,393 column names carry a comma *inside* the name
    (`LAB__HDL CHOLESTEROL, DIRECT`), so `slice_columns` now takes a JSON list
    and splits nothing. Do not "make these consistent" again — the two tools
    differ because their values differ.
    """
    return [p.strip() for p in raw.split(",") if p.strip()]


# --------------------------------------------------------------------------- #
#  Tools — reading
# --------------------------------------------------------------------------- #


@mcp.tool()
def okf_list_domains() -> str:
    """List the bundle's domains and how many documents each holds.

    Call this first. It is the cheapest possible picture of what the knowledge source
    covers, before a single search is spent finding out.

    Returns:
        JSON with domains (slug, title, documents), total, and — if any file was passed
        over — skipped, naming each one and why. A non-empty skipped list means the
        bundle holds files this surface did not read; report it rather than assuming the
        total is the whole bundle.

    ↑ 요약: 지식원의 목차. 도메인 이름과 각 도메인에 논문이 몇 편 있는지, 그리고
      전체 몇 편인지를 준다. **가장 먼저 부를 도구다** — 검색을 한 번도 쓰지 않고
      이 지식원이 무엇을 다루는지 볼 수 있는 가장 싼 방법이다.

      `skipped` 가 비어 있지 않으면 **읽지 못한 파일이 있다는 뜻**이다. 그럴 때는
      `total` 을 번들 전체라고 여기지 말고 그대로 보고할 것.
    """
    try:
        root = _bundle_root()          # 환경변수가 가리키는 번들 위치
        docs, skipped = _load(root)
    except OKFError as e:
        # 번들이 설정돼 있지 않은 경우 등. 예외로 죽지 않고 JSON 으로 알린다.
        return json.dumps({"error": str(e)})

    # 도메인별 편 수를 센다.
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc.domain] = counts.get(doc.domain, 0) + 1

    domains = []
    for slug in sorted(counts):
        # 도메인 폴더의 index.md 에 사람이 읽을 제목이 적혀 있으면 가져온다.
        # 평평한 번들에는 그런 파일이 없으므로 그냥 폴더 이름(slug)을 쓴다.
        title = ""
        index = root / slug / _DOMAIN_INDEX
        if index.is_file():
            try:
                fields, _ = _parse_concept_file(index)
                title = _text(fields.get("domain_title")) or _text(fields.get("title"))
            except (OKFError, OSError, UnicodeDecodeError):
                title = ""   # 표지를 못 읽어도 목록 자체는 내준다
        domains.append({"slug": slug, "title": title or slug, "documents": counts[slug]})

    out: dict[str, Any] = {"domains": domains, "total": len(docs)}
    if skipped:
        out["skipped"] = skipped   # 건너뛴 게 있을 때만 넣는다
    return json.dumps(out)


@mcp.tool()
def okf_search(queries: str, k: int = _DEFAULT_K, domain: str = "", tags: str = "") -> str:
    """Search the bundle by what its authors said each document is about.

    Titles, tags, descriptions and journals are searched. **Bodies are not.** A hit
    therefore means the bundle says this document is about your query — not that the
    word appears somewhere inside it. Search by idea, not by column name.

    Args:
        queries: comma-separated; each is searched separately and results are merged.
            e.g. "adherence to therapy, viral load monitoring"
        k: results per query. Default 8, raised to at most 20.
        domain: restrict to one domain slug; "" = all. See okf_list_domains.
        tags: comma-separated; keep only documents carrying ANY of these tags.

    Returns:
        JSON with one entry per query: its hits as catalogue rows (id, title, domain,
        tags, journal, published, strength, n, pmid) with a score, ordered best first.
        Open the promising ones with okf_read.

    ↑ 요약: 저자가 채워 넣은 칸(제목·태그·설명·저널)만 보고 찾는다. **본문은 보지
      않는다.** 그래서 걸렸다는 것은 "번들이 이 논문은 그 주제에 관한 것이라고
      말한다" 는 뜻이지, 본문 어딘가에 그 단어가 나온다는 뜻이 아니다.

      찾을 때는 **생각(개념)으로** 찾을 것. 데이터의 열 이름으로 찾으면 안 된다 —
      열 이름은 본문이나 데이터에나 있지 논문 제목에는 없다.

      점수는 (칸의 가중치) × (걸린 낱말의 값어치)를 다 더한 값이다. 절대적인
      의미는 없고 **같은 검색 안에서 순서를 매기는 데만** 쓴다.

      입력:
        queries  쉼표로 여러 개. 각각 따로 검색해서 나란히 돌려준다.
                 예: "adherence to therapy, viral load monitoring"
        k        검색어 하나당 결과 개수. 기본 8, 최대 20.
        domain   특정 도메인으로 좁힌다. ""이면 전체.
        tags     쉼표로 여러 개. 그중 **하나라도** 달고 있는 문서만 남긴다.

      쓸 만해 보이는 것을 okf_read 로 열어 본다.
    """
    try:
        root = _bundle_root()
        docs, _ = _load(root)
    except OKFError as e:
        return json.dumps({"error": str(e)})

    wanted = _split(queries)
    if not wanted:
        return json.dumps({"error": "queries must not be empty"})

    # 1 미만은 1로, 20 초과는 20으로 눌러 둔다.
    limit = max(1, min(int(k), _MAX_K))
    notes = []
    if int(k) > _MAX_K:
        # 조용히 깎지 않는다. 깎았다고 응답에 적어야 받는 쪽이 그게 전부가
        # 아님을 안다.
        notes.append(f"k={k} was clamped to the ceiling {_MAX_K}.")

    # 검색 대상 추리기 — 도메인, 그리고 태그.
    pool = docs
    if domain:
        pool = [d for d in pool if d.domain == domain]
        if not pool:
            # 오타로 도메인 이름이 틀렸을 때, 실제 이름 목록을 같이 준다.
            return json.dumps(
                {"error": f"no domain {domain!r}", "domains": sorted({d.domain for d in docs})}
            )
    keep_tags = {t.lower() for t in _split(tags)}
    if keep_tags:
        # 교집합이 비어 있지 않으면 남긴다 = 태그 중 하나라도 겹치면 통과(AND 아님).
        pool = [d for d in pool if keep_tags & {t.lower() for t in _tag_list(d.fields.get("tags"))}]

    idf = _idf(docs)  # weights come from the whole bundle, not the filtered slice
                      # ↑ 낱말 값어치는 **번들 전체**에서 구한다. 걸러낸 조각에서
                      #   구하면, 좁힐 때마다 같은 낱말의 값이 달라져서 두 검색의
                      #   점수를 견줄 수 없게 된다.
    results = []
    for query in wanted:
        q = _tokens(query)   # 검색어도 문서와 똑같은 방식으로 낱말로 쪼갠다
        scored = []
        for doc in pool:
            score = 0.0
            for field, weight in _FIELD_WEIGHTS.items():
                hits = q & doc.field_tokens[field]   # 겹치는 낱말
                if hits:
                    score += weight * sum(idf.get(t, 0.0) for t in hits)
            if score > 0.0:
                scored.append((score, doc))
        # 점수 높은 순. 점수가 같으면 주소 순 — 같은 입력이면 늘 같은 순서가
        # 나오도록(재현 가능하도록) 두 번째 기준을 둔다.
        scored.sort(key=lambda pair: (-pair[0], pair[1].address))
        results.append(
            {
                "query": query,
                # 몇 편이 걸렸는지(matched)와 실제로 보여 주는 개수(hits)는 다르다.
                # matched 가 크면 검색어가 너무 넓다는 신호다.
                "matched": len(scored),
                "hits": [{**doc.summary, "score": round(score, 3)} for score, doc in scored[:limit]],
            }
        )

    # searched = 이번에 실제로 훑어본 문서 수(도메인·태그로 좁힌 뒤의 수).
    out: dict[str, Any] = {"results": results, "searched": len(pool)}
    if notes:
        out["notes"] = notes
    return json.dumps(out)


@mcp.tool()
def okf_read(refs: str, section: str = "", max_chars: int = 0) -> str:
    """Open one or several documents — whole, or one section of each.

    Every document in a Loremaster bundle is written in the same sections. Ask for the
    one you need instead of the whole paper: `section="Bottom line"` is usually what a
    hypothesis is built from, and a full body here runs to several thousand characters.

    Args:
        refs: comma-separated. A document answers to its id, its PMID, its filename and
            its filename without the suffix — whichever you have.
        section: exact section heading; "" = the whole body. Each result lists the
            headings that document actually has, so a wrong guess is recoverable in one
            call rather than a search.
        max_chars: truncate the returned text; 0 = no limit. Truncation is reported.

    Returns:
        JSON with one entry per ref: its frontmatter fields, the text asked for, the
        available section headings, and export_safe as the STRING the bundle wrote.

    ↑ 요약: 문서를 연다. 여러 편을 한 번에 열 수도 있고, 각 문서에서 **절 하나만**
      뽑아 올 수도 있다.

      Loremaster 가 만든 번들의 논문은 전부 같은 절 구성을 갖는다. 통째로 읽지 말고
      필요한 절을 지목하는 편이 낫다 — 가설을 세울 때 필요한 것은 보통
      `section="Bottom line"` 하나이고, 본문 전체는 수천 자에 이른다.

      입력:
        refs       쉼표로 여러 개. 문서는 id·PMID·파일 이름·확장자 뺀 이름 중
                   무엇으로 불러도 응답한다.
        section    절 제목을 정확히 적는다. ""이면 본문 전체.
        max_chars  돌려줄 글자 수 제한. 0이면 제한 없음. 잘랐으면 잘랐다고 알린다.

      절 이름을 틀려도 응답에 **그 문서가 실제로 가진 절 목록**이 함께 오므로,
      검색을 다시 하지 않고 한 번 더 부르는 것으로 회복된다.
    """
    try:
        root = _bundle_root()
        docs, _ = _load(root)
    except OKFError as e:
        return json.dumps({"error": str(e)})

    by_ref = _index(docs)      # 이름표 전화번호부
    wanted = _split(refs)
    if not wanted:
        return json.dumps({"error": "refs must not be empty"})

    out = []
    for ref in wanted:
        # 한 편이 실패해도 나머지는 계속 연다. 실패한 것만 그 자리에 사유를 적는다.
        found = by_ref.get(ref.strip().lower(), [])
        if not found:
            out.append({"ref": ref, "error": "no document answers to that reference"})
            continue
        if len(found) > 1:
            # 같은 이름에 두 편 이상이 걸렸다. 아무거나 고르지 않고 후보를 보여 준다.
            out.append(
                {"ref": ref, "error": "ambiguous", "candidates": [d.address for d in found]}
            )
            continue
        doc = found[0]
        sections = _sections(doc.body)
        headings = [name for name, _ in sections]   # 이 문서가 실제로 가진 절 이름들

        if section:
            # 절 제목이 정확히 같은 것을 찾는다. 없으면 None.
            text = next((body for name, body in sections if name == section), None)
            if text is None:
                out.append(
                    {
                        "ref": ref,
                        "id": doc.address,
                        "error": f"no section {section!r}",
                        "sections": headings,
                    }
                )
                continue
        else:
            text = doc.body          # 절을 지목하지 않았으면 본문 전체

        truncated = False
        if max_chars and len(text) > max_chars:
            text, truncated = text[:max_chars], True

        entry = {
            **doc.summary,           # 카탈로그 정보(제목·태그·저널·PMID …)를 그대로 얹는다
            "ref": ref,              # 부른 쪽이 쓴 이름 그대로 — 어느 요청의 답인지 짝짓기 쉽게
            "section": section or None,
            "text": text,
            "sections": headings,
            # As a STRING, on purpose. The bundle writes `export_safe: "false"` quoted,
            # and a non-empty string is truthy in Python — anything that tests this
            # value for truth redistributes every document while reporting it filtered.
            # 102 of this bundle's 142 papers say "false".
            #
            # ↑ 일부러 **문자열 그대로** 내보낸다. 번들에는 `export_safe: "false"` 가
            #   따옴표까지 붙어 적혀 있다. 파이썬에서 비어 있지 않은 문자열은 참이므로
            #   `if export_safe:` 는 "false" 에도 통과한다. 그런 코드는 모든 문서를
            #   내보내면서 화면에는 "걸렀다"고 보고한다.
            #   이 번들 142편 중 102편이 "false" 다. 판단은 여기서 하지 않고, 값을
            #   있는 그대로 넘겨 쓰는 쪽이 문자열로 비교하게 둔다.
            "export_safe": _text(doc.fields.get("export_safe")),
        }
        if truncated:
            entry["truncated"] = True   # 잘랐으면 잘랐다고 반드시 알린다
        out.append(entry)

    # default=str 는 마지막 안전망이다. 머리말에 JSON 이 모르는 값이 섞여 있어도
    # 통째로 터지는 대신 글자로 바꿔 내보낸다.
    return json.dumps({"documents": out}, default=str)


if __name__ == "__main__":
    # 이 파일을 직접 실행하면 MCP 서버로 뜬다. core 의 도구와 위 세 도구가
    # 한 서버에서 같이 나온다.
    mcp.run()
