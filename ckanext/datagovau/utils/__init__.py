from __future__ import annotations

import contextlib
import logging
import re
import shutil
import tempfile
from collections.abc import Container, Iterable
from typing import Any, TypeVar

import requests

from ckan import model

T = TypeVar("T")
log = logging.getLogger(__name__)


@contextlib.contextmanager
def temp_dir(suffix: str, dir: str):
    """Context-manager that cleans directory tree upon exit."""
    path = tempfile.mkdtemp(suffix=suffix, dir=dir)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def download(url: str, name: str, **kwargs: Any) -> requests.Response:
    """Memory-safe downloads of remote content.

    Args:
        url: URL of remote content
        name: content destination inside local FS
        **kwargs: extra arguments for `requests.get`

    Returns:
        Response after copying its content into the file.
    """
    kwargs.setdefault("stream", True)
    req = requests.get(url, **kwargs)
    with open(name, "wb") as dest:
        for chunk in req.iter_content(1024 * 1024):
            dest.write(chunk)

    log.debug("Downloaded %s from %s", name, url)
    return req


def contains(value: Container[T], parts: Iterable[T], separate: bool = False) -> bool:
    """Check if any part is included into value.

    Enabling `separate` flag enforces string search with additional check for
    word boundaries. I.e, `hey` matches `hey-you` or `hey, you!`, but does not
    match `haystack`.

    Examples:
        ```python
        # containers are checked using `in` operator
        assert contains([1, 2, 3], [2, 10])
        assert not contains({"a": "b"}, ["b"])

        # strings are checked as normal containers
        assert contains("hello world", ["llo"])
        assert contains("hello world", ["world"])

        # when `separate` enabled, only separate words match the search
        assert not contains("hello world", ["llo"], True)
        assert contains("hello world", ["world"], True)
        ```

    Returns:
        `True` if any `part` is found inside `value`. `False` otherwise.
    """
    if separate and isinstance(value, str):
        return any(re.search(f"\\b{part}\\b", value) for part in parts)
    return any(part in value for part in parts)


def get_sysadmins_emails() -> list[str]:
    """Get emails of all sysadmins.

    Returns:
        List of emails.
    """
    q = model.Session.query(model.User).filter(
        model.User.sysadmin.is_(True),
        model.User.state == "active",
    )

    return [user.email for user in q.all() if user.email]
