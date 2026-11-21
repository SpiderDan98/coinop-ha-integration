"""Fake Thumbnail image and camera entities, pictures to show on them, and reading images back."""

from io import BytesIO

from homeassistant.components.camera import Camera
from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from PIL import ExifTags, Image, ImageCms
from pytest_homeassistant_custom_component.common import MockPlatform, mock_platform

THUMBNAIL = "image.kobra_thumbnail"
CAMERA = "camera.kobra"
COLOURS = {"red": (220, 30, 30), "green": (30, 200, 30), "blue": (30, 30, 220)}


def picture(
    colour: str = "red",
    size: tuple[int, int] = (300, 200),
    *,
    image_format: str = "JPEG",
    orientation: int | None = None,
) -> bytes:
    """An image in one colour, carrying the metadata a phone or camera writes."""
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "Camera maker"
    exif[ExifTags.Base.ImageDescription] = "Workshop"
    exif[ExifTags.IFD.GPSInfo] = {
        ExifTags.GPS.GPSLatitudeRef: "N",
        ExifTags.GPS.GPSLatitude: (52.0, 31.0, 12.0),
    }
    if orientation is not None:
        exif[ExifTags.Base.Orientation] = orientation
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buffer = BytesIO()
    Image.new("RGB", size, COLOURS[colour]).save(
        buffer, image_format, exif=exif.tobytes(), icc_profile=icc
    )
    return buffer.getvalue()


def opened(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    return image


def colour(data: bytes) -> str:
    """The colour of a stored one-colour picture."""
    pixel = opened(data).convert("RGB").resize((1, 1)).getpixel((0, 0))
    assert isinstance(pixel, tuple)
    return min(
        COLOURS,
        key=lambda name: sum(
            abs(a - b) for a, b in zip(COLOURS[name], pixel, strict=True)
        ),
    )


class FakeThumbnail(ImageEntity):
    """The image entity of the Device's integration: `show` a new picture, or none."""

    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        super().__init__(hass)
        self.entity_id = entity_id
        self.content = b""

    async def async_image(self) -> bytes | None:
        return self.content

    def show(self, content: bytes, *, available: bool = True) -> None:
        self.content = content
        self._attr_available = available
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()


class FakeCamera(Camera):
    """A camera whose next answers are set by the test; it fails without one."""

    _attr_content_type = "image/jpeg"

    def __init__(self, entity_id: str) -> None:
        super().__init__()
        self.entity_id = entity_id
        self.answers: list[bytes] = []
        self.requests = 0

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        self.requests += 1
        if not self.answers:
            raise HomeAssistantError("Camera did not answer")
        return self.answers.pop(0)


async def add_thumbnail(
    hass: HomeAssistant,
    content: bytes = b"",
    *,
    entity_id: str = THUMBNAIL,
    fetched: bool = True,
) -> FakeThumbnail:
    """Unless `fetched`, its state stays unknown until something asks for its
    picture, as Creality's print preview and Elegoo's cover image do."""
    entity = FakeThumbnail(hass, entity_id)
    entity.content = content
    if content and fetched:
        entity._attr_image_last_updated = dt_util.utcnow()
    await _add(hass, "image", entity)
    return entity


async def add_camera(
    hass: HomeAssistant, *answers: bytes, entity_id: str = CAMERA
) -> FakeCamera:
    [entity] = await add_cameras(hass, entity_id)
    entity.answers = list(answers)
    return entity


async def add_cameras(hass: HomeAssistant, *entity_ids: str) -> list[FakeCamera]:
    """Several cameras at once, none with an answer yet."""
    entities = [FakeCamera(entity_id) for entity_id in entity_ids]
    await _add(hass, "camera", *entities)
    return entities


async def _add(
    hass: HomeAssistant, domain: str, *entities: ImageEntity | Camera
) -> None:
    async def setup_platform(
        hass: HomeAssistant, config: object, add_entities: object, info: object = None
    ) -> None:
        assert callable(add_entities)
        add_entities(list(entities))

    mock_platform(
        hass,
        f"printer_integration.{domain}",
        MockPlatform(async_setup_platform=setup_platform),
    )
    assert await async_setup_component(
        hass, domain, {domain: {"platform": "printer_integration"}}
    )
    await hass.async_block_till_done()
