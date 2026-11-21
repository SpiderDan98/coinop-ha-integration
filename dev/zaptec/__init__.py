"""Dev container only: a static stand-in for Zaptec (custom-components/zaptec)."""

from ..coinop_dev.stand_in import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
