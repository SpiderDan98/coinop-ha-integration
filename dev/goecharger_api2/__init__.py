"""Dev container only: a static stand-in for go-e Charger API v2 (marq24/ha-goecharger-api2)."""

from ..coinop_dev.stand_in import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
