from urllib.parse import urlsplit

from flask import session


def renew_session() -> None:
    session.clear()
    session.permanent = True


def is_safe_next_url(target: str | None) -> bool:
    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    parsed = urlsplit(target)
    return not parsed.scheme and not parsed.netloc and parsed.path.startswith("/")
