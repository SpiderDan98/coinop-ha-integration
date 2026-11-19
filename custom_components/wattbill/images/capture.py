"""A Device's automatic Run images: the Thumbnail while a Run is open, the Snapshot at its end."""

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
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from custom_components.wattbill.device_config import DeviceConfig
from custom_components.wattbill.models import ImageKind, Run
from custom_components.wattbill.run_book import RunBook

from .encode import InvalidImage
from .library import ImageLibrary

_LOGGER = logging.getLogger(__name__)

SNAPSHOT_ATTEMPTS = 3
SNAPSHOT_RETRY = timedelta(seconds=10)
SNAPSHOT_TIMEOUT = 10
# A later end than this would show the Device after the Run, e.g. emptied.
SNAPSHOT_LATEST = timedelta(minutes=2)


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
        self._stopped = False
        # Thumbnails are stored in the order they were shown.
        self._thumbnail_lock = asyncio.Lock()

    @callback
    def async_start(self) -> None:
        if entity_id := self._config.thumbnail_entity_id:
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

    @callback
    def async_copy_thumbnail(self, run: Run) -> None:
        """Copy what the Thumbnail input shows now to the open Run."""
        entity_id = self._config.thumbnail_entity_id
        if entity_id and _has_image(self._hass.states.get(entity_id)):
            self._hass.async_create_task(self._async_copy_thumbnail(run, entity_id))

    @callback
    def async_run_ended(self, run: Run) -> None:
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
            try:
                content = (await image.async_get_image(self._hass, entity_id)).content
                await self._library.async_add(run, ImageKind.THUMBNAIL, content)
            except (HomeAssistantError, InvalidImage) as err:
                _LOGGER.debug("No Thumbnail from %s: %s", entity_id, err)

    async def _async_snapshot(self, run: Run, entity_id: str, attempt: int) -> None:
        # Imported only with a camera set: the camera integration's requirements
        # are installed only when it is set up.
        from homeassistant.components import camera

        try:
            snapshot = await camera.async_get_image(
                self._hass, entity_id, timeout=SNAPSHOT_TIMEOUT
            )
            await self._library.async_add(run, ImageKind.SNAPSHOT, snapshot.content)
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
