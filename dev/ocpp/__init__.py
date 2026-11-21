"""Dev container only: a static stand-in for OCPP (lbbrhzn/ocpp)."""

from ..coinop_dev.static import async_setup_entry, async_unload_entry

__all__ = ["async_setup_entry", "async_unload_entry"]
