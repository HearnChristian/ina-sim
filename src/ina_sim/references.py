"""Bibliography access.

Every empirical number in INA-sim names a key in library/references.yaml.
tests/test_references.py enforces that: an unreferenced coefficient is a build
failure, not a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml


@dataclass(frozen=True)
class Reference:
    key: str
    authors: str
    year: int
    title: str
    access: str
    short_label: str | None = None
    doi: str | None = None
    url: str | None = None
    journal: str | None = None
    volume: str | None = None
    pages: str | None = None
    publisher: str | None = None
    open_access: bool = False
    note: str | None = None

    def citation(self) -> str:
        """Compact one-line citation."""
        head = f"{self.authors} ({self.year}). {self.title}."
        if self.journal:
            where = f" {self.journal}"
            if self.volume:
                where += f" {self.volume}"
            if self.pages:
                where += f", {self.pages}"
            head += where + "."
        elif self.publisher:
            head += f" {self.publisher}."
        if self.doi:
            head += f" doi:{self.doi}"
        return head

    def short(self) -> str:
        """'Harrison et al. (2019)' style label.

        Taken from the `short` field rather than guessed from the author
        string: initials make author counting unreliable, and a citation that
        silently says "et al." for a two-author paper is a small lie.
        """
        if self.short_label:
            return self.short_label
        first = self.authors.split(",")[0].strip()
        return f"{first} ({self.year})"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "short": self.short(),
            "citation": self.citation(),
            "doi": self.doi,
            "url": self.url,
            "open_access": self.open_access,
            "access": self.access,
        }


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    ref = resources.files("ina_sim.library").joinpath("references.yaml")
    with ref.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def load_references() -> dict[str, Reference]:
    raw = _load_raw().get("references") or {}
    out: dict[str, Reference] = {}
    for key, body in raw.items():
        out[key] = Reference(
            key=key,
            authors=str(body.get("authors", "")),
            year=int(body.get("year", 0)),
            title=str(body.get("title", "")),
            access=str(body.get("access", "unknown")),
            short_label=body.get("short"),
            doi=body.get("doi"),
            url=body.get("url"),
            journal=body.get("journal"),
            volume=str(body["volume"]) if body.get("volume") is not None else None,
            pages=body.get("pages"),
            publisher=body.get("publisher"),
            open_access=bool(body.get("open_access", False)),
            note=body.get("note"),
        )
    return out


def get_reference(key: str) -> Reference:
    refs = load_references()
    if key not in refs:
        raise KeyError(
            f"unknown reference key {key!r}; add it to library/references.yaml "
            "before shipping a number that depends on it"
        )
    return refs[key]


def cite(key: str) -> str:
    """Short label, or the raw key if the reference is missing."""
    try:
        return get_reference(key).short()
    except KeyError:
        return key
