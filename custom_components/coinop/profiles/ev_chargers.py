"""Integration Profiles of EV charger integrations."""

from custom_components.coinop.const import DEVICE_TYPE_EV_CHARGER

from .base import always

DEVICE_TYPES = (DEVICE_TYPE_EV_CHARGER,)
KIND = always(DEVICE_TYPE_EV_CHARGER)
