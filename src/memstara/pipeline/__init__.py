"""The three pipelines, in the order they were built and in the order to read them.

    hello.py    one agent, one question, no tools. The smallest thing that runs.
    mvp.py      the supervised pipeline: a fixed sequence of stages, one trial at a
                time, driven from Python.
    board.py    the board pipeline: agents take work off a shared blackboard and put
                results back, and the sequence is not fixed in advance.

They were `src/memstara/pipeline/hello.py`, `src/memstara/pipeline/mvp.py` and `src/memstara/pipeline/board.py`. The
numbers said "read these in this order", which was worth having and is why this
docstring exists — a module cannot be called `01_hello_agent` and be imported.

`core.py` is what mvp and board share.

Run one with `-m`, from anywhere:

    python -m memstara.pipeline.board --trials 3 --trace
"""
