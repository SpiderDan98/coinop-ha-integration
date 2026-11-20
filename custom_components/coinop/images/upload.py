"""The panel's photo upload: multipart, as the websocket caps message size."""

from http import HTTPStatus

from aiohttp import BodyPartReader, web
from homeassistant.components.http import HomeAssistantView, require_admin

from custom_components.coinop.const import DOMAIN

from .encode import InvalidImage
from .library import MAX_FILE_BYTES, UPLOAD_LIMIT, UploadLimit
from .view import image_info, loaded_coinop


class _BadRequest(Exception):
    pass


class _TooLarge(Exception):
    pass


async def _read_files(request: web.Request, room: int) -> list[bytes]:
    """Every `file` part, read in chunks so an oversized one is refused early."""
    try:
        reader = await request.multipart()
    except (KeyError, ValueError, AssertionError) as err:
        raise _BadRequest from err
    files: list[bytes] = []
    while (part := await reader.next()) is not None:
        if not isinstance(part, BodyPartReader) or part.name != "file":
            continue
        if len(files) == room:
            raise UploadLimit
        data = bytearray()
        while chunk := await part.read_chunk():
            data += chunk
            if len(data) > MAX_FILE_BYTES:
                raise _TooLarge
        files.append(bytes(data))
    return files


class RunUploadView(HomeAssistantView):
    """POST `file` parts (JPEG, PNG, WebP); answers `{"images": [...]}` or an error code."""

    url = f"/api/{DOMAIN}/runs/{{run_id}}/images"
    name = f"api:{DOMAIN}:run_image_upload"

    @require_admin
    async def post(self, request: web.Request, run_id: str) -> web.Response:
        coinop = loaded_coinop(request)
        run = coinop.book.run(run_id) if coinop else None
        try:
            if coinop is None or run is None:
                raise LookupError
            files = await _read_files(request, coinop.images.upload_room(run))
            if (images := await coinop.images.async_upload(run, files)) is None:
                raise LookupError
        except LookupError:
            message = ("No Run with this id", HTTPStatus.NOT_FOUND, "not_found")
        except UploadLimit:
            message = (
                f"A Run keeps up to {UPLOAD_LIMIT} uploads",
                HTTPStatus.CONFLICT,
                "too_many",
            )
        except _TooLarge:
            message = (
                f"A photo may have up to {MAX_FILE_BYTES} bytes",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "too_large",
            )
        except InvalidImage:
            message = (
                "Only JPEG, PNG and WebP photos",
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "invalid_format",
            )
        except _BadRequest:
            message = (
                "Expected multipart form data",
                HTTPStatus.BAD_REQUEST,
                "invalid_format",
            )
        else:
            return self.json({"images": [image_info(run, image) for image in images]})
        return self.json_message(*message)
