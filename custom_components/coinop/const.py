"""Constants for Coin-op."""

DOMAIN = "coinop"
NAME = "Coin-op"

SUBENTRY_DEVICE = "device"

SUPPORTED_INTEGRATIONS_URL = (
    "https://github.com/SpiderDan98/coinop-ha-integration/blob/main/"
    "docs/supported-integrations.md"
)

# Stored in each Device's subentry data; the panel groups Devices by it.
DEVICE_TYPE_3D_PRINTER = "3d_printer"
DEVICE_TYPE_WASHING_MACHINE = "washing_machine"
DEVICE_TYPE_DISHWASHER = "dishwasher"
DEVICE_TYPE_TUMBLE_DRYER = "tumble_dryer"
DEVICE_TYPE_COFFEE_MACHINE = "coffee_machine"
DEVICE_TYPE_OVEN = "oven"
DEVICE_TYPE_EV_CHARGER = "ev_charger"
DEVICE_TYPE_ROBOTIC_MOWER = "robotic_mower"
# Its Devices store a Type Name and their own Capabilities (ADR 0009).
DEVICE_TYPE_OTHER = "other"
