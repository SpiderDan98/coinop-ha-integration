"""Coin-op's global catalogues (Materials, Tags, Line Item Templates) in memory and in the catalog Store.

Every change is saved at once and announced with the name of the catalogue that
changed, so open panels can refresh it.
"""

from collections.abc import Callable, Collection, Iterable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.util.ulid import ulid_now

from .materials import (
    DEFAULT_DIAMETER,
    USUAL_UNITS,
    Material,
    MaterialForm,
    PackUnit,
    SpoolmanPrice,
)
from .store import CoinOpStore
from .tags import TAGS, sort_tags
from .templates import TEMPLATES, LineItemTemplate

MATERIALS = "materials"


def _material(data: dict[str, Any]) -> Material:
    """A Material from its fields, with what follows from them filled in.

    Raises ValueError for a Material by weight or volume without a density.
    """
    form = MaterialForm(data["form"])
    price = data["price"]
    if price["source"] == "fixed":
        price = {"pack_unit": USUAL_UNITS.get(form, PackUnit.GRAM)} | price
    by_piece = price.get("pack_unit") == PackUnit.PIECE
    density = None if by_piece else data.get("density")
    if density is None and not by_piece:
        raise ValueError("A Material by weight or volume needs its density")
    filament = form is MaterialForm.FILAMENT and not by_piece
    colour = data.get("colour")
    return Material.from_dict(
        {
            "vendor": None,
            "default_for_type": False,
            "archived": False,
            **data,
            "density": density,
            "colour": colour and colour.lower(),
            "diameter": data.get("diameter") or DEFAULT_DIAMETER if filament else None,
            "price": price,
        }
    )


class Catalog:
    def __init__(
        self,
        store: CoinOpStore,
        data: dict[str, Any],
        material_in_use: Callable[[str], bool],
    ) -> None:
        self._store = store
        self._materials = {
            item["id"]: Material.from_dict(item) for item in data[MATERIALS]
        }
        self._tags: list[str] = sort_tags(data.get(TAGS, []))
        self._templates = {
            item["id"]: LineItemTemplate.from_dict(item)
            for item in data.get(TEMPLATES, [])
        }
        self._unknown = {
            key: value
            for key, value in data.items()
            if key not in (MATERIALS, TAGS, TEMPLATES)
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

    def templates(self) -> list[LineItemTemplate]:
        return list(self._templates.values())

    def template(self, template_id: str) -> LineItemTemplate | None:
        return self._templates.get(template_id)

    def find_templates(self, template_ids: Iterable[str]) -> list[LineItemTemplate]:
        """The templates with these ids, in this order; deleted ones are left out."""
        return [
            template
            for template_id in template_ids
            if (template := self.template(template_id)) is not None
        ]

    async def async_create_template(self, fields: dict[str, Any]) -> LineItemTemplate:
        template = LineItemTemplate.from_dict({**fields, "id": ulid_now()})
        self._templates[template.id] = template
        await self._save(TEMPLATES)
        return template

    async def async_update_template(
        self, template: LineItemTemplate, changes: dict[str, Any]
    ) -> LineItemTemplate:
        updated = LineItemTemplate.from_dict(template.as_dict() | changes)
        self._templates[template.id] = updated
        await self._save(TEMPLATES)
        return updated

    async def async_delete_template(self, template: LineItemTemplate) -> None:
        del self._templates[template.id]
        await self._save(TEMPLATES)

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

    async def async_sync_spoolman(
        self, read: dict[int, dict[str, Any]], waiting: Collection[int]
    ) -> None:
        """Bring the Materials in line with the Filaments Spoolman has, by Filament id.

        A linked Material takes what was read for its Filament (without a price in
        Spoolman its last price per gram stays) and is archived once its Filament
        is gone; each other Filament gets a linked Material, except those `waiting`
        for the user to merge them.
        """
        changed = False
        for material in self.materials():
            if not isinstance(price := material.price, SpoolmanPrice):
                continue
            if price.filament_id not in read:
                if not material.archived:
                    material.archived = changed = True
                    material.default_for_type = False
                continue
            fields = read[price.filament_id]
            if fields["price"]["per_gram"] is None:
                fields = fields | {
                    "price": fields["price"] | {"per_gram": price.last_read}
                }
            updated = _material(material.as_dict() | fields)
            if updated != material:
                self._materials[material.id] = updated
                changed = True
        linked = self.linked_filaments()
        for filament_id, fields in read.items():
            if filament_id in linked or filament_id in waiting:
                continue
            material = _material(
                fields
                | {"id": ulid_now(), "default_for_type": not self._has_default(fields)}
            )
            self._materials[material.id] = material
            changed = True
        if changed:
            await self._save_materials()

    async def async_link_spoolman(
        self, material: Material, fields: dict[str, Any]
    ) -> Material:
        """Link the Material to the Filament `fields` were read for, keeping its id
        and its default; without a price in Spoolman its price per gram stays."""
        if fields["price"]["per_gram"] is None:
            per_gram = material.price_per_gram
            fields = fields | {"price": fields["price"] | {"per_gram": per_gram}}
        updated = _material(material.as_dict() | fields)
        self._materials[material.id] = updated
        await self._save_materials()
        return updated

    def linked_filaments(self) -> set[int]:
        """The ids of the Filaments a Material links to, archived ones included."""
        return {
            m.price.filament_id
            for m in self.materials()
            if isinstance(m.price, SpoolmanPrice)
        }

    def _has_default(self, fields: dict[str, Any]) -> bool:
        return any(
            m.default_for_type
            and not m.archived
            and m.type.casefold() == fields["type"].casefold()
            for m in self.materials()
        )

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
                TEMPLATES: [template.as_dict() for template in self.templates()],
            }
        )
        for listener in list(self._listeners):
            listener(changed)
