"""The schema library Home Assistant validates flows with."""

try:
    import probatio as vol
except ImportError:  # Home Assistant releases before the switch to probatio
    import voluptuous as vol  # type: ignore[no-redef]

__all__ = ["vol"]
