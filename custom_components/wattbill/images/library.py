"""Run images on disk and on their Run, kept in step.

Files live in `<files_path>/images/<run id>/<image id>.webp` (and `.tile.webp`).
A Run's file folder goes when the Run is deleted; files no Run refers
to are removed at startup.
"""

from collections.abc import Iterable
from pathlib import Path
import shutil

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from custom_components.wattbill.models import ImageKind, Run, RunImage
from custom_components.wattbill.run_book import RunBook, RunChange
from custom_components.wattbill.store import files_path

from .encode import encode

VARIANTS = {"full": ".webp", "tile": ".tile.webp"}
# A Run has at most one of these; a new one replaces it.
SINGLE_KINDS = frozenset({ImageKind.THUMBNAIL, ImageKind.SNAPSHOT})


class ImageLibrary:
    def __init__(self, hass: HomeAssistant, book: RunBook) -> None:
        self._hass = hass
        self._book = book
        self._root = files_path(hass) / "images"
        self._closed = False

    def path(self, run: Run, image: RunImage, variant: str) -> Path:
        return self._root / run.id / f"{image.id}{VARIANTS[variant]}"

    async def async_add(
        self, run: Run, kind: ImageKind, data: bytes
    ) -> RunImage | None:
        """Store `data` as a new image of the Run; raises `InvalidImage`.

        None if the Run is gone or WattBill unloaded while the image was stored.
        """
        image = RunImage(ulid_now(), kind, dt_util.utcnow())
        await self._hass.async_add_executor_job(self._write, run, image, data)
        if self._closed or self._book.run(run.id) is not run:
            await self._hass.async_add_executor_job(self._delete, run, [image])
            return None
        replaced = [i for i in run.images if kind in SINGLE_KINDS and i.kind is kind]
        run.images = [i for i in run.images if i not in replaced] + [image]
        await self._book.async_correct(run)
        await self._hass.async_add_executor_job(self._delete, run, replaced)
        return image

    @callback
    def async_close(self) -> None:
        """Stop changing Runs: the hub entry unloads and its RunBook with it."""
        self._closed = True

    @callback
    def async_follow_deletions(self) -> CALLBACK_TYPE:
        """Delete a Run's files once it leaves the RunBook."""

        @callback
        def on_change(change: RunChange, run: Run) -> None:
            if change is RunChange.DELETED:
                self._hass.async_add_executor_job(
                    shutil.rmtree, self._root / run.id, True
                )

        return self._book.async_listen(on_change)

    async def async_remove_orphans(self) -> None:
        referenced = {
            run.id: {image.id for image in run.images} for run in self._book.runs()
        }
        await self._hass.async_add_executor_job(self._remove_orphans, referenced)

    def _write(self, run: Run, image: RunImage, data: bytes) -> None:
        full, tile = encode(data)
        folder = self._root / run.id
        folder.mkdir(parents=True, exist_ok=True)
        for variant, content in (("full", full), ("tile", tile)):
            self.path(run, image, variant).write_bytes(content)

    def _delete(self, run: Run, images: Iterable[RunImage]) -> None:
        for image in images:
            for variant in VARIANTS:
                self.path(run, image, variant).unlink(missing_ok=True)

    def _remove_orphans(self, referenced: dict[str, set[str]]) -> None:
        if not self._root.is_dir():
            return
        for folder in self._root.iterdir():
            if not folder.is_dir() or folder.name not in referenced:
                _remove(folder)
                continue
            for file in folder.iterdir():
                if file.name.split(".", 1)[0] not in referenced[folder.name]:
                    _remove(file)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
