from __future__ import annotations

import logging
from typing import NoReturn

log = logging.getLogger(__name__)


class IngestionError(Exception):
    pass


class BadConfigError(IngestionError):
    pass


class IngestionFailError(IngestionError):
    pass


def fail(reason: str) -> NoReturn:
    log.error(reason)
    raise IngestionFailError(reason)
