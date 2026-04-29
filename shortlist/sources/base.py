"""Source base class — every fetcher implements this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import ClassVar

from shortlist.models import RawJob


class Source(ABC):
    """A pull-mode job source.

    Implementations set `name` to a short identifier matching the
    `sources.<name>` key in `config.yaml` and implement `fetch()`.
    """

    name: ClassVar[str]

    @abstractmethod
    def fetch(self, since: datetime | None) -> Iterator[RawJob]:
        """Yield jobs posted/updated at-or-after `since`. Iterator, not list,
        so callers can persist as they go."""
