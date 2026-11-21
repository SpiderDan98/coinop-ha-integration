"""Dev container only: a static stand-in for Home Assistant's Home Connect."""

from ..coinop_dev.stand_in import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
