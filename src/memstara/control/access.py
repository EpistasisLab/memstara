"""Explicit browser origins for local and network installations."""

from urllib.parse import urlsplit


def public_viewer(origin: str) -> tuple[str, str]:
    """Return an exact origin and host; never infer trust from request headers."""
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MEMSTARA_PUBLIC_ORIGIN must be a single HTTP(S) origin")
    _ = parsed.port  # Access validates the port and may raise ValueError.
    return f"{parsed.scheme}://{parsed.netloc}", parsed.hostname


def request_host(value: str) -> str:
    try:
        parsed = urlsplit("//" + value)
        _ = parsed.port
        if parsed.username is not None or parsed.password is not None or parsed.path:
            return ""
        return parsed.hostname or ""
    except ValueError:
        return ""
