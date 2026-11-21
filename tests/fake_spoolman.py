"""The dev container's Spoolman for the tests: its REST API over the mocked client
session, keeping what it is sent the way Spoolman 0.27 does."""

from http import HTTPStatus
from itertools import count
import re
from typing import Any

from aiohttp import ClientError
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL


class FakeSpoolman:
    def __init__(self, aioclient_mock: AiohttpClientMocker, url: str) -> None:
        self.records: dict[str, dict[int, dict[str, Any]]] = {
            "vendor": {},
            "filament": {},
            "spool": {},
        }
        self.down = False
        self._ids = count(1)
        api = re.compile(rf"^{re.escape(url)}/api/v1/")
        for method in ("get", "post", "delete"):
            aioclient_mock.request(method, api, side_effect=self._answer)

    def filaments(self) -> list[dict[str, Any]]:
        return [self._filament(f) for f in self.records["filament"].values()]

    def spools(self, *, archived: bool = False) -> list[dict[str, Any]]:
        return [
            self._spool(spool)
            for spool in self.records["spool"].values()
            if archived or not spool.get("archived")
        ]

    def _filament(self, record: dict[str, Any]) -> dict[str, Any]:
        fields = {k: v for k, v in record.items() if k != "vendor_id"}
        vendor_id = record.get("vendor_id")
        return fields | {"vendor": vendor_id and self.records["vendor"][vendor_id]}

    def _spool(self, record: dict[str, Any]) -> dict[str, Any]:
        fields = {k: v for k, v in record.items() if k != "filament_id"}
        filament = self.records["filament"][record["filament_id"]]
        return fields | {"filament": self._filament(filament)}

    async def _answer(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        if self.down:
            return AiohttpClientMockResponse(method, url, exc=ClientError())
        kind, _, id_ = url.path.removeprefix("/api/v1/").partition("/")
        match method.upper(), kind, id_:
            case "GET", "info", "":
                body: Any = {"version": "0.27.1"}
            case "GET", "vendor", "":
                body = list(self.records["vendor"].values())
            case "GET", "filament", "":
                body = self.filaments()
            case "GET", "spool", "":
                body = self.spools(archived=url.query.get("allow_archived") == "true")
            case "POST", _, "" if kind in self.records:
                body = {"id": next(self._ids), **data}
                self.records[kind][body["id"]] = body
            case "DELETE", "filament", _ if any(
                spool["filament_id"] == int(id_)
                for spool in self.records["spool"].values()
            ):
                return AiohttpClientMockResponse(
                    method, url, HTTPStatus.INTERNAL_SERVER_ERROR
                )
            case "DELETE", _, _ if int(id_) in self.records.get(kind, {}):
                del self.records[kind][int(id_)]
                if kind == "vendor":
                    for filament in self.records["filament"].values():
                        if filament.get("vendor_id") == int(id_):
                            filament["vendor_id"] = None
                body = {"message": "Success!"}
            case _:
                return AiohttpClientMockResponse(method, url, HTTPStatus.NOT_FOUND)
        return AiohttpClientMockResponse(method, url, json=body)
