"""Dev container only: a static stand-in for go-e Charger MQTT (syssi/goecharger-mqtt)."""

from ..coinop_dev.static import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
