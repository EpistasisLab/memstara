#!/usr/bin/env python3
"""Render what an agent actually did, from what core persisted.

This is the richer half of observability. Live logs are transient and only exist if you
were watching; core, by contrast, writes a `RunStep` for every phase of every run and
keeps it. That record holds the phase input and output, the LLM call (model, tokens,
latency, cost) and every tool call with its arguments and its result.

So any run can be reconstructed after the fact — including runs from before this script
existed, because none of this is new instrumentation. It is all already in the database.

Usage::

    python sandbox/trace_run.py --trial 0
    python sandbox/trace_run.py --trial 0 --stage hypothesis
    python sandbox/trace_run.py --trial 0 --summary
    python sandbox/trace_run.py --run-id 30b49492-d4bd-411c-bbad-999b41286bff
    python sandbox/trace_run.py --trial 0 --full     # do not truncate payloads
    python sandbox/trace_run.py --from outputs/runs/<run> --trial 0

02_mvp_pipeline.py calls :func:`dump_all` at the end of every run, so a run directory
already contains these traces as files; the CLI is for going back further.


==============================================================================
 이 파일을 읽는 법
==============================================================================

 core 가 데이터베이스에 남긴 것에서 **"에이전트가 실제로 무엇을 했나"** 를 되살려
 글로 찍어 준다. 화면에 흘러간 로그는 그때 보고 있어야만 볼 수 있고 곧 사라지지만,
 core 는 실행의 모든 단계마다 한 줄(RunStep)을 써서 **보관한다.**

 그 줄에는 단계의 입력과 출력, 모델 호출(모델명·토큰·걸린 시간·비용), 그리고
 **도구 호출의 인자와 결과가 통째로** 들어 있다. 브레이크포인트로는 볼 수 없는
 것이다 — 도구는 별도 프로세스에서 돌고, 거기 멈춰 서 봐야 그 한 번밖에 못 본다.

 함수는 다섯이다.

   _clip(text, limit, full)   너무 긴 글을 잘라 준다(--full 이면 안 자른다)
   _load_rows(...)            todo_rows.json 을 읽는다
   _resolve(trial, stage)     "시행 3번" 을 실제 실행 id 들로 바꾼다
   render(...)                **핵심 함수.** 실행 하나를 사람이 읽을 글로 찍는다
   dump_all(rows_file, out)   시행마다 한 파일씩, 자르지 않고 전부 써 낸다

 놓치기 쉬운 것:

   · 이 스크립트가 생기기 **전에 돌린 실행도 그대로 볼 수 있다.** 새로 계측한 것이
     하나도 없기 때문이다. 필요한 것은 이미 전부 데이터베이스에 있었고, 없던 것은
     그것을 **읽어 주는 쪽**이었다.
   · 기본값은 글을 잘라서 보여 준다. 도구에 무엇이 들어갔는지 전부 봐야 할 때는
     반드시 `--full` 을 붙인다.
   · 02_mvp_pipeline.py 가 실행이 끝날 때마다 dump_all 을 부르므로, 실행 폴더에는
     이미 trace/ 파일들이 들어 있다. 명령줄로 부르는 것은 **그보다 더 옛날 것**을
     보러 갈 때다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from settings import Settings

from agentic_core import configure
from agentic_core.runner import get_run, get_run_steps
from agentic_core.schemas.llm import flatten_tool_call_records

HERE = Path(__file__).parent
# 가장 최근 실행이 남긴 시행 목록. "시행 3번" 을 실행 id 로 바꾸는 열쇠다.
ROWS_FILE = HERE / "outputs" / "todo_rows.json"

# 한 시행이 밟는 네 단계. 찍는 순서도 이 순서다.
STAGES = ("hypothesis", "data", "ml", "interpreter")


def _clip(text: str, limit: int, full: bool) -> str:
    """긴 글을 limit 글자에서 자르고, 몇 글자를 잘랐는지 덧붙인다.

    먼저 줄바꿈과 연속 공백을 공백 하나로 눌러 한 줄로 만든다. 여러 줄짜리
    도구 결과가 화면을 뒤덮는 것을 막기 위해서다.

    full 이 참이면(--full) 아무것도 자르지 않는다. **무엇이 오갔는지 전부 봐야 할
    때는 반드시 이쪽을 쓴다.** 잘린 글만 보고 판단하면 잘린 뒤쪽에 있던 것이
    원인일 때 영영 못 찾는다.
    """
    text = " ".join(str(text).split())
    if full or len(text) <= limit:
        return text
    return f"{text[:limit]}... (+{len(text) - limit} chars)"


#: `readable` 모드에서 **이미 다른 줄이 말해 준** 칸들.
#:
#: 왜 목록으로 두나 — 그냥 "OUT 을 안 찍는다" 로 하면 언젠가 core 가 새 칸을 넣었을 때
#: 그것이 **조용히 사라진다.** 아는 것만 빼고, 모르는 것은 남기려는 것이다.
#: (`_dump_leftovers` 가 나머지를 찍는다)
_SEEN_ELSEWHERE = {
    # sense: 시스템 프롬프트·도구 명세·대화 이력은 통째로 모델에 보낸 요청 안에 있다.
    #        그 원문은 같은 폴더의 `NN_단계.llm.txt` 에 있으므로 여기서는 크기만 말한다.
    "sense": {"user_input", "agent_goal", "system_prompt", "conversation_history",
              "available_tools", "memories"},
    # reason: thought 와 final_answer 는 아래에서 전문으로 찍는다. tool_calls 는
    #         **바로 다음 act 단계의 TOOL 줄**이 인자까지 보여 준다.
    # `pattern` 과 `step` 은 내용이 아니라 장부다 — 몇 번째 단계인지는 `[ 3]` 머리가,
    # 어떤 방식인지는 실행 내내 같은 값이라 머리말이 이미 말한다.
    "reason": {"thought", "action", "tool_calls", "final_answer", "pattern", "step"},
    # act: results 는 위 TOOL 줄의 `->` 와 같은 내용이다. 이 중복이 파일 용량의
    #      대부분이었다(한 실행에서 209KB).
    "act": {"results", "final_response", "should_continue", "steps",
            "is_complete", "completion_reason", "action", "pattern"},
}


def _lines(value: Any, indent: str) -> list[str]:
    """dict 를 `키: 값` 여러 줄로 편다. dict 가 아니면 한 덩어리로 둔다.

    한 줄에 300자짜리 JSON 을 그대로 두면 읽을 수가 없어서, 칸마다 줄을 나눈다.
    **자르지는 않는다** — 자른 뒤쪽에 원인이 있으면 영영 못 찾는다.
    """
    if not isinstance(value, dict) or not value:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return [indent + line for line in str(text).splitlines()] or [indent]
    out = []
    for k, v in value.items():
        body = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        rows = str(body).splitlines() or [""]
        out.append(f"{indent}{k}: {rows[0]}")
        pad = indent + " " * (len(k) + 2)
        out.extend(pad + r for r in rows[1:])
    return out


def _dump_leftovers(emit: Any, data: Any, phase: str, tag: str) -> None:
    """아는 칸을 뺀 **나머지**를 찍는다. 비어 있으면 아무것도 안 찍는다.

    이것이 있어야 core 가 새 칸을 추가해도 조용히 묻히지 않는다.
    """
    if not isinstance(data, dict):
        if data:
            for line in _lines(data, "       "):
                emit(line)
        return
    rest = {k: v for k, v in data.items()
            if k not in _SEEN_ELSEWHERE.get(phase, ()) and v not in (None, "", [], {})}
    if rest:
        emit(f"     {tag}")
        for line in _lines(rest, "       "):
            emit(line)


def _load_rows(rows_file: Path = ROWS_FILE) -> list[dict[str, Any]]:
    """시행 목록 파일을 읽는다. 없으면 무엇을 먼저 해야 하는지 알려 주고 멈춘다."""
    if not rows_file.is_file():
        print(f"!! {rows_file} not found — run 02_mvp_pipeline.py first", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(rows_file.read_text(encoding="utf-8"))


def _resolve(trial: int, stage: str | None, rows_file: Path = ROWS_FILE) -> list[tuple[str, uuid.UUID]]:
    """Map a trial number to its stage run ids, via todo_rows.json.

    ↑ **시행 번호를 실행 id 들로 바꾼다.** 사람은 "3번 시행" 이라고 말하지만 core 는
      뜻 없는 UUID 로만 실행을 안다. 그 둘을 이어 주는 것이 todo_rows.json 이고,
      그래서 시행 하나는 보통 네 개(단계별)의 실행 id 를 갖는다.

      --stage 를 주면 그 단계 하나만, 안 주면 **기록이 남아 있는 단계 전부**를
      돌려준다. 앞 단계에서 죽은 시행은 뒤쪽 id 가 아예 없어서, 그냥 건너뛴다.
    """
    rows = _load_rows(rows_file)
    match = next((r for r in rows if r.get("trial") == trial), None)
    if match is None:
        available = sorted(r.get("trial") for r in rows)
        print(f"!! trial {trial} not found. available: {available}", file=sys.stderr)
        raise SystemExit(1)

    run_ids = match.get("run_ids") or {}
    # --stage 를 줬으면 그것만. 아니면 실제로 id 가 남아 있는 단계만 순서대로.
    wanted = [stage] if stage else [s for s in STAGES if s in run_ids]
    out: list[tuple[str, uuid.UUID]] = []
    for s in wanted:
        rid = run_ids.get(s)
        if rid:
            out.append((s, uuid.UUID(rid)))
        elif stage:
            # 콕 집어 요청한 단계가 없다는 것은, 그 시행이 그 전에 죽었다는 뜻이다.
            # 조용히 아무것도 안 찍으면 "기록이 없다" 와 "실패했다" 가 구별되지 않는다.
            print(f"!! trial {trial} has no '{s}' run (it likely failed earlier)", file=sys.stderr)
            raise SystemExit(1)
    return out


async def render(
    label: str,
    run_id: uuid.UUID,
    *,
    full: bool,
    summary: bool,
    stream: Any = None,
    readable: bool = False,
) -> None:
    """Write one run's steps to *stream* (default: stdout).

    ↑ **이 파일의 핵심 함수.** 실행 하나를 사람이 읽을 수 있는 글로 찍는다.

      찍는 순서는 이렇다.

        머리말   상태 · 토큰 · 비용 · 단계 수 · 실행에 들어간 입력
        단계마다 [번호] 단계이름 걸린시간
                 LLM  어느 모델에 얼마를 썼나
                 TOOL 어떤 도구를 **어떤 인자로** 불렀고, **무엇이 돌아왔나**
                 IN/OUT  (--full 일 때만) 단계의 입력과 출력 전문

      TOOL 두 줄이 이 파일 전체의 이유다. 그 인자와 결과는 화면 로그에는 실린 적이
      없고, 별도 프로세스에서 도는 도구에 디버거를 붙여도 그때 한 번밖에 못 본다.

      stream 을 주면 그 파일에, 안 주면 화면에 찍는다. 같은 코드로 사람이 보는
      출력과 보관용 파일을 둘 다 만들기 위해 이렇게 해 두었다.

      readable=True 로 부르면 **사람이 읽으라고** 찍는다. 무엇이 달라지나:

        · IN/OUT 의 JSON 덩어리 대신 **알맹이만** — 생각은 전문으로, 앞 단계와
          겹치는 것은 뺀다. 실측으로 한 파일에서 209KB 가 그 중복이었다
        · 도구 인자와 결과를 `키: 값` 여러 줄로 편다. 한 줄에 300자씩 붙어 있으면
          읽을 수가 없다
        · **아무것도 자르지 않는다.** 뺀 것은 전부 다른 줄이 이미 말한 것뿐이고,
          모르는 칸은 `_dump_leftovers` 가 남긴다

      기본값이 False 인 이유 — `trace_run.py` 를 명령줄로 쓰는 기존 방식의 출력을
      바꾸지 않기 위해서다.
    """
    out = stream if stream is not None else sys.stdout

    def emit(text: str = "") -> None:
        print(text, file=out)

    run = await get_run(run_id)          # 실행 한 건의 요약 — 상태·토큰·비용
    steps = await get_run_steps(run_id)  # 그 실행이 밟은 단계들, 순서대로

    # ---- 머리말 ------------------------------------------------------
    header = f"{label}  run={run_id}"
    emit("\n" + "=" * 100)
    emit(header)
    if run is not None:
        tokens = run.token_usage or {}
        emit(
            f"status={run.status.value}  "
            f"tokens={tokens.get('prompt_tokens', 0)}/{tokens.get('completion_tokens', 0)}  "
            f"cost=${float(run.cost_estimate or 0):.6f}  steps={len(steps)}"
        )
        if run.error:
            emit(f"error: {run.error}")
        emit(f"input: {_clip(run.input, 160, full)}")
    emit("=" * 100)

    # --summary 는 여기서 끝낸다. 여러 실행을 훑어볼 때 머리말만 있으면 충분하다.
    if summary:
        return

    # ---- 단계별 ------------------------------------------------------
    for step in steps:
        dur = ""
        if step.started_at and step.completed_at:
            dur = f"{(step.completed_at - step.started_at).total_seconds():.2f}s"
        emit(f"\n[{step.sequence:>2}] {step.phase.value:<9} {dur}")

        # 이 단계에서 모델을 불렀다면, 무엇을 얼마에 썼는지.
        if step.llm_call:
            c = step.llm_call
            emit(
                f"     LLM  {c.get('model', '?')}  "
                f"{c.get('prompt_tokens', 0)}/{c.get('completion_tokens', 0)} tok  "
                f"{c.get('latency_ms', 0)}ms  ${c.get('cost_estimate', 0):.6f}"
            )
            if c.get("failure_reason"):
                emit(f"     LLM  failure_reason: {_clip(c['failure_reason'], 200, full)}")

        # flatten_tool_call_records handles both shapes core persists: a single call, or
        # {"calls": [...]} when one step invoked several.
        #
        # ↑ core 가 저장하는 모양이 **둘**이다. 도구를 한 번만 불렀으면 그 호출이
        #   그대로, 여러 번 불렀으면 {"calls": [...]} 로 묶여 들어간다. 이 함수가
        #   둘 다 받아 하나의 목록으로 펴 준다. 직접 풀려고 하면 한쪽 모양을
        #   빠뜨리게 되고, 그러면 어떤 실행에서는 도구 호출이 통째로 안 보인다.
        #
        #   아래 두 줄이 이 파일에서 가장 값나가는 부분이다 — 무엇을 넣었고(인자)
        #   무엇이 돌아왔는지(결과)가 여기 다 있다.
        for call in flatten_tool_call_records(step.tool_call):
            server = call.get("server") or ""
            tool = call.get("tool") or "?"
            args = json.dumps(call.get("arguments") or {}, ensure_ascii=False)
            ok = "" if call.get("success", True) else "  [FAILED]"
            if readable:
                emit(f"     도구  {server}.{tool}{ok}")
                emit("     인자")
                for line in _lines(call.get("arguments") or {}, "       "):
                    emit(line)
                emit("     결과")
                result = call.get("result") or ""
                try:
                    result = json.loads(result) if isinstance(result, str) else result
                except (json.JSONDecodeError, TypeError):
                    pass
                for line in _lines(result, "       "):
                    emit(line)
            else:
                emit(f"     TOOL {server}.{tool}({_clip(args, 110, full)}){ok}")
                emit(f"          -> {_clip(call.get('result') or '', 150, full)}")

        # 단계 자체의 입출력.
        #
        # readable 이면 **알맹이만** 찍는다. 그냥 JSON 을 통째로 찍으면 단계마다
        # 그때까지의 대화가 다시 들어가서 파일이 못 읽게 커진다(실측 209KB).
        if readable:
            phase = step.phase.value
            res = step.output if isinstance(step.output, dict) else {}

            if phase == "sense":
                # 사람에게 무엇을 시켰는지. 이 실행에서 딱 한 번 나온다.
                if res.get("user_input"):
                    emit("     입력  " + str(res["user_input"]))
                if res.get("agent_goal"):
                    emit("     목표  " + str(res["agent_goal"]))
                # 시스템 프롬프트·도구 명세·기억은 **모델에 보낸 요청 안에 그대로**
                # 들어간다. 그 원문은 옆의 `.llm.txt` 에 있으므로 여기서는 크기만.
                sp = len(str(res.get("system_prompt") or ""))
                tools_n = len(res.get("available_tools") or [])
                mem_n = len(res.get("memories") or [])
                emit(f"     장비  역할 설명서 {sp:,}자 · 쓸 수 있는 도구 {tools_n}개 · "
                     f"기억 {mem_n}건   (원문은 옆의 .llm.txt)")

            elif phase == "reason":
                if res.get("thought"):
                    emit("     생각")
                    for line in _lines(str(res["thought"]), "       "):
                        emit(line)
                if res.get("final_answer"):
                    emit("     답")
                    for line in _lines(str(res["final_answer"]), "       "):
                        emit(line)

            # act 단계는 위 「도구」 줄이 이미 전부 말했다. 그 IN/OUT 은 같은 내용을
            # 한 번 더 담고 있을 뿐이라 찍지 않는다.

            _dump_leftovers(emit, step.output, phase, "그밖(출력)")
            _dump_leftovers(emit, step.input, phase, "그밖(입력)")

        elif full:
            if step.input:
                emit(f"     IN   {_clip(json.dumps(step.input, ensure_ascii=False), 400, full)}")
            if step.output:
                emit(f"     OUT  {_clip(json.dumps(step.output, ensure_ascii=False), 400, full)}")


async def dump_all(rows_file: Path, out_dir: Path) -> list[Path]:
    """Write one untruncated trace file per trial. Returns the files written.

    This is what turns the database into an artifact. The step rows hold every tool
    call with its arguments and its result, but they only become something you can read
    later if someone goes and gets them — a live log never carried them at all.

    ↑ 시행마다 **자르지 않은** 기록 파일을 하나씩 쓴다. 쓴 파일 목록을 돌려준다.

      데이터베이스에 있는 것을 **남는 물건**으로 바꾸는 자리다. 단계 줄에는 모든
      도구 호출이 인자와 결과까지 들어 있지만, 누가 가서 꺼내 오지 않으면 나중에
      읽을 수 있는 것이 되지 못한다. 그리고 화면 로그는 애초에 그것을 실은 적이
      없다.

      02_mvp_pipeline.py 가 실행이 끝날 때마다 이 함수를 부른다. 그래서 실행 폴더는
      만들어질 때부터 trace/ 를 안고 있다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for row in _load_rows(rows_file):
        trial = row.get("trial")
        run_ids = row.get("run_ids") or {}
        if trial is None or not run_ids:
            # a trial that failed before its first run has nothing to show
            #
            # ↑ 첫 실행에 닿기도 전에 죽은 시행은 보여 줄 것이 없다. 빈 파일을
            #   만들어 두면 "기록이 없는 것" 과 "아무 일도 없었던 것" 이 섞인다.
            continue

        path = out_dir / f"trial{trial:02d}.txt"
        with path.open("w", encoding="utf-8") as fh:
            print(f"trial {trial}  perspective: {row.get('perspective', '')}", file=fh)
            if row.get("error"):
                print(f"ERROR: {row['error']}", file=fh)
            for stage in STAGES:
                rid = run_ids.get(stage)
                if rid:
                    await render(stage, uuid.UUID(rid), full=True, summary=False, stream=fh)
        written.append(path)

    return written


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--trial", type=int, help="trial number, resolved via outputs/todo_rows.json")
    src.add_argument("--run-id", help="a core run id directly")
    ap.add_argument("--stage", choices=STAGES, help="restrict to one stage of the trial")
    ap.add_argument("--summary", action="store_true", help="header only, no steps")
    ap.add_argument("--full", action="store_true", help="do not truncate arguments, results or payloads")
    ap.add_argument(
        "--from",
        dest="run_dir",
        default=None,
        help="read todo_rows.json from this run directory instead of outputs/",
    )
    args = ap.parse_args()

    # 데이터베이스에 닿으려면 설정이 먼저 들어가 있어야 한다.
    configure(Settings())

    # --from 을 주면 그 실행 폴더의 시행 목록을, 안 주면 가장 최근 것을 읽는다.
    rows_file = Path(args.run_dir) / "todo_rows.json" if args.run_dir else ROWS_FILE

    # --run-id 는 시행 목록을 거치지 않고 실행 id 를 곧장 받는 길이다. 시행 목록이
    # 없어진 옛날 실행도 id 만 알면 볼 수 있다.
    if args.run_id:
        targets = [("run", uuid.UUID(args.run_id))]
    else:
        targets = _resolve(args.trial, args.stage, rows_file)

    for label, rid in targets:
        await render(label, rid, full=args.full, summary=args.summary)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
