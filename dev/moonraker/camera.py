"""Moonraker's preview camera, which shows a picture only while printing, and a webcam
that shows the dev configuration's Workshop camera, under the description's unique
ids."""

from io import BytesIO

from homeassistant.components.camera import Camera, async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from PIL import Image, ImageDraw

from ..coinop_dev.scenarios import KINDS
from ..coinop_dev.stand_in import registrations

WORKSHOP_CAMERA = "camera.workshop_camera"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    [registration] = registrations(entry.domain, entry.data[KINDS])
    [shape] = registration.of_entry(entry.entry_id).devices
    device = DeviceInfo(identifiers=shape.fields["identifiers"])
    async_add_entities(
        [
            PreviewCamera(shape.entities["thumbnail"].unique_id, "Thumbnail", device),
            Webcam(shape.entities["Chamber_0"].unique_id, "Chamber", device),
        ]
    )


class StandInCamera(Camera):
    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(self, unique_id: str, name: str, device: DeviceInfo) -> None:
        super().__init__()
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device


class PreviewCamera(StandInCamera):
    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        state = self.hass.states.get("input_select.voron_status")
        if state is None or state.state != "printing":
            return None
        return await self.hass.async_add_executor_job(_preview)


class Webcam(StandInCamera):
    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            image = await async_get_image(self.hass, WORKSHOP_CAMERA)
        except HomeAssistantError:
            return None
        return image.content


def _preview() -> bytes:
    """A slicer-like preview of the part on the bed."""
    image = Image.new("RGB", (300, 300), "#263238")
    draw = ImageDraw.Draw(image)
    draw.polygon([(60, 230), (150, 270), (240, 230), (150, 190)], fill="#455a64")
    draw.rounded_rectangle((110, 90, 190, 220), 16, fill="#ff9800", outline="#e65100")
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()
