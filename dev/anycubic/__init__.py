"""Dev container only: a static stand-in for Anycubic 3D Printer - Local Control (chrisfore/anycubic_ha_local)."""

from ..coinop_dev.stand_in import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
