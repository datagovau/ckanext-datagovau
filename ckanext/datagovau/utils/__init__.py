from __future__ import annotations

import contextlib
import logging
import shutil
import tempfile
from typing import Container, Iterable, TypeVar

import requests

T = TypeVar("T")
log = logging.getLogger(__name__)


@contextlib.contextmanager
def temp_dir(suffix: str, dir: str):
    path = tempfile.mkdtemp(suffix=suffix, dir=dir)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def download(url: str, name: str, **kwargs) -> requests.Response:
    kwargs.setdefault("stream", True)
    req = requests.get(url, **kwargs)
    with open(name, "wb") as dest:
        for chunk in req.iter_content(1024 * 1024):
            dest.write(chunk)

    log.debug("Downloaded %s from %s", name, url)
    return req


def contains(value: Container[T], parts: Iterable[T]) -> bool:
    return any(part in value for part in parts)
