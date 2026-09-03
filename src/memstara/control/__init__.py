"""The one thing the viewer cannot do for itself: start a run.

    request.py   what a start request may contain, and nothing else. Standard
                 library only, so CI can test the rules without a bundle.
    service.py   the HTTP surface and the child process it owns.
    __main__.py  `python -m memstara.control`.

Why this is a second process instead of a route on the viewer's API
-------------------------------------------------------------------
The viewer runs in Docker (`viewer/docker-compose.yml`) and reaches both databases
over `host.docker.internal`. That container has no `.venv`, no `../motoro` and no
`.env`; it physically cannot launch a pipeline. Its API is also read-only in three
deliberate layers — the `memstara_viewer` role holds SELECT and nothing else,
`allow_methods=["GET"]` (`viewer/api/main.py:87`), and the README says so. **None of
those three change.** This is a different process, on the host, in this repository's
own environment, bound to the loopback interface.

So the screen gains a button without the observer gaining a write path to what it
observes.
"""
