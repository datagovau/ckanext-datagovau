from __future__ import annotations
from typing import Any

from typing_extensions import TypedDict

class DdgStatistics(TypedDict):
    dataset_count: int
    unpub_data_count: int
    open_count: int
    api_count: int


class SchemingChoice(TypedDict):
    value: Any
    label: Any

SchemingChoices = list[SchemingChoice]
