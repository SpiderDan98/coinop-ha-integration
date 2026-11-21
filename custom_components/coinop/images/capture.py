"""A Device's automatic Run images: the Thumbnail while a Run is open, the Snapshot at its end.

An image entity as Thumbnail is copied whenever it changes; a camera, whose state
doesn't change with its picture, is fetched when the Run starts, again until it
gave one and then less and less often while the Run is open, keeping the latest
(the first can be a placeholder), never after the Run ended. So is an image entity
whose state is unknown when the Run starts: some only get a state once something
fetched them.
"""

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.components import image
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
    split_entity_id,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from custom_components.coinop.device_config import DeviceConfig
from custom_components.coinop.models import ImageKind, Run
from custom_components.coinop.run_book import RunBook

from .encode import InvalidImage
from .library import ImageLibrary

_LOGGER = logging.getLogger(__name__)

SNAPSHOT_ATTEMPTS = 3
SNAPSHOT_RETRY = timedelta(seconds=10)
FETCH_TIMEOUT = 10
THUMBNAIL_RETRY = timedelta(minutes=1)
# Doubles after each fetch that gave a picture.
THUMBNAIL_REFRESH = timedelta(minutes=5)
# A later end than this would show the Device after the Run, e.g. emptied.
SNAPSHOT_LATEST = timedelta(minutes=2)


def _is_camera(entity_id: str) -> bool:
    return split_entity_id(entity_id)[0] == "camera"


def _has_image(state: State | None) -> bool:
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


class DeviceImages:
    def __init__(
        self,
        hass: HomeAssistant,
        book: RunBook,
        library: ImageLibrary,
        config: DeviceConfig,
    ) -> None:
        self._hass = hass
        self._book = book
        self._library = library
        self._config = config
        self._unsubscribe: list[CALLBACK_TYPE] = []
        self._retries: set[CALLBACK_TYPE] = set()
        self._thumbnail_retry: CALLBACK_TYPE | None = None
        self._stopped = False
        # Thumbnails are stored in the order they were shown.
        self._thumbnail_lock = asyncio.Lock()

    @callback
    def async_start(self) -> None:
        entity_id = self._config.thumbnail_entity_id
        if entity_id and not _is_camera(entity_id):
            self._unsubscribe.append(
                async_track_state_change_event(
                    self._hass, entity_id, self._on_thumbnail
                )
            )

    @callback
    def async_stop(self) -> None:
        self._stopped = True
        while self._unsubscribe:
            self._unsubscribe.pop()()
        while self._retries:
            self._retries.pop()()
        self._cancel_thumbnail_retry()

    @callback
    def async_copy_thumbnail(self, run: Run) -> None:
        """Copy what the Thumbnail input shows now to the open Run."""
        entity_id = self._config.thumbnail_entity_id
        if not entity_id:
            return
        state = self._hass.states.get(entity_id)
        if _is_camera(entity_id) or (
            state is not None and state.state == STATE_UNKNOWN
        ):
            self._hass.async_create_task(self._async_fetch_thumbnail(run, entity_id))
        elif _has_image(state):
            self._hass.async_create_task(self._async_copy_thumbnail(run, entity_id))

    @callback
    def async_run_ended(self, run: Run) -> None:
        self._cancel_thumbnail_retry()
        camera = self._config.camera_entity_id
        if not (self._config.snapshot and camera) or run.ended is None:
            return
        if run.end_reconstructed and dt_util.utcnow() - run.ended > SNAPSHOT_LATEST:
            return
        self._hass.async_create_task(self._async_snapshot(run, camera, 1))

    @callback
    def _on_thumbnail(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        # The state is the time the image changed; attribute updates (tokens) are not.
        if not _has_image(new) or (old is not None and new and old.state == new.state):
            return
        if run := self._book.open_run(self._config.device_id):
            self._hass.async_create_task(
                self._async_copy_thumbnail(run, event.data["entity_id"])
            )

    async def _async_copy_thumbnail(self, run: Run, entity_id: str) -> None:
        async with self._thumbnail_lock:
            await self._async_store_thumbnail(run, entity_id)

    async def _async_fetch_thumbnail(
        self, run: Run, entity_id: str, refresh: timedelta = THUMBNAIL_REFRESH
    ) -> None:
        async with self._thumbnail_lock:
            if self._stopped or self._book.open_run(self._config.device_id) is not run:
                return
            stored = await self._async_store_thumbnail(run, entity_id)
        if stored or any(i.kind is ImageKind.THUMBNAIL for i in run.images):
            self._fetch_thumbnail_later(run, entity_id, refresh, refresh * 2)
        else:
            self._fetch_thumbnail_later(run, entity_id, THUMBNAIL_RETRY, refresh)

    async def _async_store_thumbnail(self, run: Run, entity_id: str) -> bool:
        """Whether the entity's picture is now the Run's Thumbnail; the lock is held."""
        try:
            content = await self._async_get(entity_id)
            await self._library.async_add(run, ImageKind.THUMBNAIL, content)
        except (HomeAssistantError, InvalidImage) as err:
            _LOGGER.debug("No Thumbnail from %s: %s", entity_id, err)
            return False
        return True

    async def _async_get(self, entity_id: str) -> bytes:
        """The picture an image or camera entity shows now."""
        if not _is_camera(entity_id):
            fetched = await image.async_get_image(
                self._hass, entity_id, timeout=FETCH_TIMEOUT
            )
            return fetched.content
        # Imported only with a camera set: the camera integration's requirements
        # are installed only when it is set up.
        from homeassistant.components import camera

        picture = await camera.async_get_image(
            self._hass, entity_id, timeout=FETCH_TIMEOUT
        )
        return picture.content

    def _fetch_thumbnail_later(
        self, run: Run, entity_id: str, wait: timedelta, refresh: timedelta
    ) -> None:
        @callback
        def fetch(now: datetime) -> None:
            self._thumbnail_retry = None
            self._hass.async_create_task(
                self._async_fetch_thumbnail(run, entity_id, refresh)
            )

        self._cancel_thumbnail_retry()
        self._thumbnail_retry = async_call_later(self._hass, wait, fetch)

    def _cancel_thumbnail_retry(self) -> None:
        if self._thumbnail_retry:
            self._thumbnail_retry()
            self._thumbnail_retry = None

    async def _async_snapshot(self, run: Run, entity_id: str, attempt: int) -> None:
        try:
            snapshot = await self._async_get(entity_id)
            await self._library.async_add(run, ImageKind.SNAPSHOT, snapshot)
        except (HomeAssistantError, InvalidImage) as err:
            _LOGGER.debug(
                "Snapshot attempt %s from %s failed: %s", attempt, entity_id, err
            )
            if attempt < SNAPSHOT_ATTEMPTS and not self._stopped:
                self._retry(run, entity_id, attempt + 1)

    def _retry(self, run: Run, entity_id: str, attempt: int) -> None:
        @callback
        def retry(now: datetime) -> None:
            self._retries.discard(cancel)
            self._hass.async_create_task(self._async_snapshot(run, entity_id, attempt))

        cancel = async_call_later(self._hass, SNAPSHOT_RETRY, retry)
        self._retries.add(cancel)
