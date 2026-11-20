"""What the user chose in the export dialog, and the exports waiting for their download.

The PDF is never stored: an export keeps only which Runs and options it was
for, briefly, and the download renders it from the Runs' current values.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
import secrets

CONF_MARKUP = "markup"
LANGUAGES = ("en", "de")
# Long enough for a phone's download manager to fetch it after a delay.
EXPIRES = timedelta(minutes=5)


class Detail(StrEnum):
    DETAILED = "detailed"
    COMPACT = "compact"


def language_for(language: str) -> str:
    """The statement language closest to a Home Assistant language."""
    return next((lang for lang in LANGUAGES if language.startswith(lang)), "en")


@dataclass(frozen=True)
class Options:
    """`title` None means the default title in `language`; `markup` is a percentage.

    `images`: each Run's Cover Image in its Detailed section.
    """

    language: str
    markup: float
    title: str | None = None
    note: str | None = None
    detail: Detail = Detail.DETAILED
    images: bool = True


@dataclass(frozen=True)
class Export:
    run_ids: list[str]
    options: Options
    expires: datetime


@dataclass
class CostStatements:
    """`markup` is the hub option's default Markup."""

    markup: float = 0.0
    _exports: dict[str, Export] = field(default_factory=dict)

    def add(self, run_ids: list[str], options: Options, now: datetime) -> str:
        self._exports = {
            token: export
            for token, export in self._exports.items()
            if export.expires > now
        }
        token = secrets.token_urlsafe(16)
        self._exports[token] = Export(run_ids, options, now + EXPIRES)
        return token

    def get(self, token: str, now: datetime) -> Export | None:
        export = self._exports.get(token)
        return export if export and export.expires > now else None
