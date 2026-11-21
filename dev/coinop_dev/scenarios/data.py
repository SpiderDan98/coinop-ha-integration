"""The test data the Pieces fill Coin-op with."""

from typing import NamedTuple

# Each Device's inputs are helpers from the dev configuration.yaml.
PRINTERS = {"prusa": 120.0, "bambu": 150.0}

# A Material's name is its vendor's followed by its Spoolman Filament's.
MATERIALS = [
    ("Prusament PLA Galaxy Black", "PLA", "#1d1d24", "Prusament", 29.99),
    ("Extrudr PETG White", "PETG", "#f3f3f3", "Extrudr", 24.90),
    ("Polymaker ASA Red", "ASA", "#c0262d", "Polymaker", 32.50),
    ("eSun PLA+ Blue", "PLA", "#1f5fbf", "eSun", 19.99),
    ("Bambu Lab PLA Matte Ivory", "PLA", "#e9e3d3", "Bambu Lab", 22.99),
    ("Prusament PETG Orange", "PETG", "#f26b1d", "Prusament", 29.99),
    ("Polymaker PC Grey", "PC", "#8a8d91", "Polymaker", 39.00),
    ("Sunlu TPU Clear", "TPU", "#d8e6ea", "Sunlu", 27.00),
]
DENSITY = {"PLA": 1.24, "PETG": 1.27, "ASA": 1.07, "PC": 1.20, "TPU": 1.21}
# Spoolman's Filaments besides the Materials', which only the Spoolman option makes
# Materials of: the rainbow has three colours, the natural PLA no price.
SPOOLMAN_ONLY = [
    ("Prusament PETG Jet Black", "PETG", "#16161a", "Prusament", 29.99),
    ("Polymaker PolyTerra PLA Forest Green", "PLA", "#2f6b3a", "Polymaker", 21.99),
    ("Eryone Silk PLA Rainbow", "PLA", "#e53935,#fdd835,#1e88e5", "Eryone", 26.99),
    ("PLA Natural", "PLA", "#f5f1e6", None, None),
]


class Spool(NamedTuple):
    remaining: float
    location: str
    # A Filament with a priced spool has no price of its own: Spoolman's is the spool's.
    price: float | None = None
    archived: bool = False


SPOOLS = {
    "Prusament PLA Galaxy Black": [Spool(640, "Dry box"), Spool(1000, "Shelf")],
    "Extrudr PETG White": [Spool(215, "Dry box")],
    "Polymaker ASA Red": [Spool(880, "Shelf")],
    "eSun PLA+ Blue": [
        Spool(90, "Dry box"),
        Spool(1000, "Shelf"),
        Spool(1000, "Shelf"),
    ],
    "Bambu Lab PLA Matte Ivory": [Spool(530, "AMS")],
    "Prusament PETG Orange": [Spool(760, "AMS")],
    "Polymaker PC Grey": [Spool(1000, "Shelf")],
    "Sunlu TPU Clear": [
        Spool(0, "Shelf", price=24.50, archived=True),
        Spool(905, "Dry box", price=27.00),
    ],
    "Prusament PETG Jet Black": [Spool(1000, "Shelf")],
    "Eryone Silk PLA Rainbow": [Spool(470, "Dry box")],
}

PARTS = [
    "Desk cable holder",
    "Sensor box enclosure",
    "Plant pot",
    "Camera mount",
    "Dishwasher spare part",
    "Headphone stand",
    "Drawer organiser",
    "Phone stand",
    "Raspberry Pi case",
    "Wall hook",
    "Lamp shade",
    "Gridfinity bins",
    "Filament clip",
    "Cookie cutter",
    "Keychain",
    "Spiral vase",
    "Spool holder",
    "Bike light mount",
    "Fan duct",
    "Board game insert",
]


class Product(NamedTuple):
    name: str
    type: str
    form: str
    density: float | None
    pack_unit: str
    pack_price: float
    pack_size: int


LAUNDRY = [
    Product("Liquid detergent Color", "Liquid detergent", "detergent", 1.04, "ml", 9.95, 1500),
    Product("Fabric softener Sensitive", "Fabric softener", "fabric_softener", 1.0, "ml", 2.49, 1000),
    Product("Oxygen whitener", "Whitener", "laundry_additive", 0.9, "g", 3.95, 750),
    Product("Colour catcher sheets", "Colour catcher sheets", "laundry_additive", None, "pcs", 3.49, 20),
]  # fmt: skip


class Load(NamedTuple):
    days_ago: int
    # None: never recognised.
    program: str | None
    # Minutes into the load until the program is recognised.
    recognised: int
    minutes: int
    kwh: float
    litres: float
    # Off the detergent scale.
    grams: int
    outcome: str


LOADS = [
    Load(26, "Cotton 60°", 0, 128, 1.12, 58.0, 78, "finished"),
    Load(23, "Eco 40-60", 0, 218, 0.71, 49.0, 72, "finished"),
    Load(20, "Wool", 0, 62, 0.38, 44.0, 41, "finished"),
    Load(17, None, 0, 95, 0.85, 52.0, 76, "finished"),
    Load(14, "Cotton 60°", 0, 125, 1.18, 56.5, 80, "finished"),
    Load(12, "Quick 30", 8, 31, 0.32, 38.0, 50, "finished"),
    Load(9, "Eco 40-60", 0, 40, 0.35, 30.5, 70, "cancelled"),
    Load(6, "Cotton 60°", 0, 131, 1.09, 57.0, 77, "finished"),
    Load(3, "Eco 40-60", 0, 221, 0.74, 48.0, 74, "finished"),
    Load(1, "Wool", 0, 60, 0.41, 46.0, 39, "finished"),
]
# The meters' readings before the first load.
WASHER_METERS = {
    "washer_energy": 412.5,
    "washer_water": 18250.0,
    "detergent_scale": 650.0,
}


class Watering(NamedTuple):
    days_ago: int
    hour: int
    minutes: int
    litres: float


WATERINGS = [
    Watering(12, 6, 20, 182.0),
    Watering(9, 6, 20, 176.5),
    Watering(6, 20, 35, 311.0),
    Watering(4, 6, 20, 180.5),
    Watering(2, 6, 25, 224.0),
    Watering(1, 20, 15, 133.5),
]
IRRIGATION_WATER = 48200.0

DISHWASHER_PRODUCTS = [
    Product("All-in-one tabs", "Dishwasher tabs", "dishwasher_product", None, "pcs", 8.99, 60),
    Product("Dishwasher salt", "Dishwasher salt", "dishwasher_product", 1.2, "g", 1.49, 2000),
    Product("Rinse aid Shine", "Rinse aid", "dishwasher_product", 1.02, "ml", 2.95, 750),
]  # fmt: skip


class Cycle(NamedTuple):
    days_ago: int
    hour: int
    # None: never recognised.
    program: str | None
    minutes: float
    outcome: str
    # What each of the Device's meters counts, in their order.
    counted: tuple[float, ...] = ()


DISHES = [
    Cycle(27, 20, "Eco 50°", 225, "finished", (0.78, 9.5)),
    Cycle(24, 21, "Auto 45-65°", 150, "finished", (1.05, 11.0)),
    Cycle(21, 20, "Eco 50°", 228, "finished", (0.8, 9.6)),
    Cycle(18, 13, "Quick 45°", 58, "finished", (0.82, 10.5)),
    Cycle(15, 20, "Intensive 70°", 170, "finished", (1.45, 14.5)),
    Cycle(12, 20, "Eco 50°", 224, "finished", (0.77, 9.4)),
    Cycle(9, 19, "Auto 45-65°", 40, "cancelled", (0.31, 4.0)),
    Cycle(6, 20, "Eco 50°", 226, "finished", (0.79, 9.5)),
    Cycle(3, 21, "Auto 45-65°", 148, "finished", (1.02, 10.8)),
    Cycle(1, 20, "Eco 50°", 225, "finished", (0.78, 9.5)),
]
DISHWASHER_METERS = {"dishwasher_energy": 286.4, "dishwasher_water": 3140.0}
DRYER_PRODUCTS = [
    Product("Dryer sheets Fresh", "Dryer sheets", "laundry_additive", None, "pcs", 3.99, 80),
    Product("Dryer fragrance Lavender", "Dryer fragrance", "laundry_additive", 1.0, "ml", 5.49, 250),
]  # fmt: skip
TUMBLES = [
    Cycle(25, 11, "Cotton cupboard dry", 165, "finished", (1.32,)),
    Cycle(22, 18, "Synthetics", 95, "finished", (0.61,)),
    Cycle(19, 11, "Cotton iron dry", 140, "finished", (1.08,)),
    Cycle(16, 10, "Cotton cupboard dry", 170, "finished", (1.38,)),
    Cycle(12, 19, "Wool finish", 12, "finished", (0.08,)),
    Cycle(10, 11, "Cotton cupboard dry", 60, "cancelled", (0.45,)),
    Cycle(7, 11, "Cotton cupboard dry", 162, "finished", (1.29,)),
    Cycle(4, 18, "Synthetics", 92, "finished", (0.59,)),
    Cycle(2, 11, "Cotton iron dry", 138, "finished", (1.05,)),
]
DRYER_METERS = {"dryer_energy": 734.2}
COFFEE_PRODUCTS = [
    Product("Espresso beans Crema", "Coffee beans", "beverage_ingredient", 0.4, "g", 14.99, 1000),
    Product("Whole milk", "Milk", "beverage_ingredient", 1.03, "ml", 1.19, 1000),
]  # fmt: skip
# Electricity and water are per Program, so a drink counts on no meter.
DRINKS = [
    Cycle(10, 7, "Espresso", 0.4, "finished"),
    Cycle(9, 8, "Cappuccino", 1.0, "finished"),
    Cycle(8, 7, "Lungo", 0.8, "finished"),
    Cycle(7, 15, "Espresso", 0.4, "finished"),
    Cycle(6, 8, "Latte macchiato", 1.3, "finished"),
    Cycle(5, 7, "Espresso", 0.2, "cancelled"),
    Cycle(5, 15, "Cappuccino", 1.0, "finished"),
    Cycle(4, 7, "Espresso", 0.4, "finished"),
    Cycle(3, 8, "Lungo", 0.8, "finished"),
    Cycle(2, 7, "Cappuccino", 1.0, "finished"),
    Cycle(1, 7, "Latte macchiato", 1.3, "finished"),
    Cycle(1, 15, "Espresso", 0.4, "finished"),
]
# Without a meter: the oven's electricity comes from its Program Defaults.
COOKINGS = [
    Cycle(27, 18, "Fan plus 180°", 55, "finished"),
    Cycle(24, 12, "Pizza 220°", 25, "finished"),
    Cycle(21, 18, "Top/bottom heat 200°", 70, "finished"),
    Cycle(18, 19, None, 40, "finished"),
    Cycle(15, 17, "Fan plus 180°", 90, "finished"),
    Cycle(12, 18, "Grill", 20, "cancelled"),
    Cycle(9, 13, "Fan plus 180°", 45, "finished"),
    Cycle(6, 19, "Pizza 220°", 22, "finished"),
    Cycle(4, 18, "Top/bottom heat 200°", 65, "finished"),
    Cycle(1, 18, "Grill", 30, "finished"),
]
OVEN_PROGRAMS = {
    "Fan plus 180°": 1.1,
    "Top/bottom heat 200°": 1.4,
    "Grill": 0.9,
    "Pizza 220°": 0.8,
}


class Charge(NamedTuple):
    days_ago: int
    # When the car is plugged in.
    hour: int
    charging: int
    # Minutes it stays plugged in once full.
    full: int
    kwh: float


SESSIONS = [
    Charge(25, 19, 240, 600, 38.5),
    Charge(22, 18, 95, 0, 14.2),
    Charge(19, 20, 180, 540, 29.0),
    Charge(16, 19, 60, 0, 9.8),
    Charge(13, 18, 300, 480, 47.6),
    Charge(11, 21, 120, 420, 19.3),
    Charge(8, 19, 75, 0, 11.9),
    Charge(6, 18, 210, 600, 33.4),
    Charge(3, 20, 140, 300, 22.7),
    Charge(1, 19, 90, 0, 14.6),
]


class Mow(NamedTuple):
    days_ago: int
    # When it leaves the station.
    hour: int
    minutes: int
    # Minutes charging after it.
    charging: int
    # What the station's meter counts.
    kwh: float
    # Minutes it was stuck; 0: never.
    stuck: int


MOWS = [
    Mow(20, 9, 90, 70, 0.25, 0),
    Mow(18, 10, 110, 80, 0.3, 0),
    Mow(16, 9, 75, 60, 0.2, 0),
    Mow(14, 14, 100, 75, 0.28, 0),
    Mow(12, 9, 85, 65, 0.24, 25),
    Mow(10, 10, 115, 85, 0.31, 0),
    Mow(8, 15, 80, 60, 0.22, 0),
    Mow(6, 9, 95, 70, 0.27, 0),
    Mow(4, 10, 90, 70, 0.26, 0),
    Mow(2, 9, 95, 75, 0.27, 0),
]
TAGS = ["Customer Miller", "Household", "Garden", "Electronics", "Gifts", "Prototypes"]
