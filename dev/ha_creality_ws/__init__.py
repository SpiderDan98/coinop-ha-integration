"""Dev container only: a static stand-in for Creality (3dg1luk43/ha_creality_ws)."""

from ..coinop_dev.stand_in import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
