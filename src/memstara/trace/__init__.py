"""Reading a finished run back: what the agents were asked, and what they answered.

    run.py     one run, step by step — the prompts, the tool calls, the replies
    board.py   the blackboard's own rows for a run tag
    report.py  a run turned into something a person can read

These were `trace_run.py`, `trace_board.py` and `run_report.py`. Nothing here writes
to the board or calls a model; they only read.
"""
