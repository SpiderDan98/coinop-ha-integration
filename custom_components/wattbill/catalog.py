"""WattBill's global catalogues (Materials, Tags) in memory and in the catalog Store.

Every change is saved at once and announced with the name of the catalogue that
changed, so open panels can refresh it.
"""

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.util.ulid import ulid_now

from .materials import DEFAULT_DIAMETER, Material, MaterialForm, PackUnit
from .store import WattBillStore
from .tags import TAGS, sort_tags

MATERIALS = "materials"


def _material(data: dict[str, Any]) -> Material:
    """A Material from its fields, with what follows from them filled in."""
    resin = MaterialForm(data["form"]) is MaterialForm.RESIN
    pack_unit = PackUnit.MILLILITRE if resin else PackUnit.GRAM
    diameter = None if resin else data.get("diameter") or DEFAULT_DIAMETER
    colour = data.get("colour")
    return Material.from_dict(
        {
            "vendor": None,
            "default_for_type": False,
            "archived": False,
            **data,
            "colour": colour and colour.lower(),
            "diameter": diameter,
            "price": {"pack_unit": pack_unit} | data["price"],
        }
    )


class Catalog:
    def __init__(
        self,
        store: WattBillStore,
        data: dict[str, Any],
        material_in_use: Callable[[str], bool],
    ) -> None:
        self._store = store
        self._materials = {
            item["id"]: Material.from_dict(item) for item in data[MATERIALS]
        }
        self._tags: list[str] = sort_tags(data.get(TAGS, []))
        self._unknown = {
            key: value for key, value in data.items() if key not in (MATERIALS, TAGS)
        }
        self._material_in_use = material_in_use
        self._listeners: list[Callable[[str], None]] = []

    def materials(self) -> list[Material]:
        return list(self._materials.values())

    def material(self, material_id: str) -> Material | None:
        return self._materials.get(material_id)

    def tags(self) -> list[str]:
        return list(self._tags)

    def tag(self, name: str) -> str | None:
        """The Tag called `name`, ignoring case."""
        return next(
            (tag for tag in self._tags if tag.casefold() == name.casefold()), None
        )

    async def async_add_tags(self, names: Iterable[str]) -> list[str]:
        """The Tags with these (trimmed) names, creating those that don't exist yet."""
        tags, created = [], False
        for name in names:
            if (tag := self.tag(name)) is None:
                self._tags = sort_tags([*self._tags, name])
                tag, created = name, True
            tags.append(tag)
        if created:
            await self._save(TAGS)
        return sort_tags(tags)

    async def async_rename_tag(self, tag: str, name: str) -> str:
        """Rename `tag`; a name another Tag has merges into it. Returns the new Tag."""
        existing = self.tag(name)
        new = name if existing in (None, tag) else existing
        self._tags = sort_tags([*(t for t in self._tags if t != tag), new])
        await self._save(TAGS)
        return new

    async def async_delete_tag(self, tag: str) -> None:
        self._tags.remove(tag)
        await self._save(TAGS)

    @callback
    def async_listen(self, listener: Callable[[str], None]) -> CALLBACK_TYPE:
        """`listener(catalogue)` after every change, e.g. `listener("materials")`."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def async_create_material(self, fields: dict[str, Any]) -> Material:
        material = _material({**fields, "id": ulid_now()})
        self._materials[material.id] = material
        await self._save_materials(material)
        return material

    async def async_update_material(
        self, material: Material, changes: dict[str, Any]
    ) -> Material:
        updated = _material(material.as_dict() | changes)
        self._materials[material.id] = updated
        await self._save_materials(updated)
        return updated

    async def async_archive_material(self, material: Material) -> None:
        material.archived = True
        material.default_for_type = False
        await self._save_materials()

    async def async_restore_material(self, material: Material) -> None:
        material.archived = False
        await self._save_materials()

    async def async_delete_material(self, material: Material) -> bool:
        """Delete a Material no Run uses; archive a used one. True if deleted."""
        if self._material_in_use(material.id):
            await self.async_archive_material(material)
            return False
        del self._materials[material.id]
        await self._save_materials()
        return True

    async def _save_materials(self, changed: Material | None = None) -> None:
        if changed is not None and changed.default_for_type:
            for other in self._materials.values():
                if (
                    other is not changed
                    and other.type.casefold() == changed.type.casefold()
                ):
                    other.default_for_type = False
        await self._save(MATERIALS)

    async def _save(self, changed: str) -> None:
        await self._store.async_save(
            self._unknown
            | {
                MATERIALS: [
                    material.as_dict() for material in self._materials.values()
                ],
                TAGS: self._tags,
            }
        )
        for listener in list(self._listeners):
            listener(changed)
