"""Tags: names unique ignoring case, kept in the catalogue, copied onto Runs by name.

A rename or delete rewrites every Run and Device carrying the Tag (`retag`), so
stored Runs, events and sensors always show the current names.
"""

from collections.abc import Iterable

from .schema import vol

TAGS = "tags"
MAX_LENGTH = 40

tag_name = vol.All(str, vol.Strip, vol.Length(min=1, max=MAX_LENGTH))


def sort_tags(tags: Iterable[str]) -> list[str]:
    """Alphabetically, ignoring case."""
    return sorted(set(tags), key=lambda tag: (tag.casefold(), tag))


def retag(tags: list[str], old: str, new: str | None) -> list[str]:
    """`tags` with `old` replaced by `new` (or removed when None), without duplicates."""
    if old not in tags:
        return tags
    kept = [tag for tag in tags if tag != old]
    return sort_tags(kept if new is None else [*kept, new])
