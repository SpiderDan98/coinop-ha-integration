"""The test data the Pieces fill Coin-op with."""

# Each Device's inputs are helpers from the dev configuration.yaml.
PRINTERS = {"prusa": 120.0, "bambu": 150.0}

MATERIALS = [
    ("Prusament PLA Galaxy Black", "PLA", "#1d1d24", "Prusa", 29.99),
    ("Extrudr PETG White", "PETG", "#f3f3f3", "Extrudr", 24.90),
    ("Polymaker ASA Red", "ASA", "#c0262d", "Polymaker", 32.50),
    ("eSun PLA+ Blue", "PLA", "#1f5fbf", "eSun", 19.99),
    ("Bambu PLA Matte Ivory", "PLA", "#e9e3d3", "Bambu Lab", 22.99),
    ("Prusament PETG Orange", "PETG", "#f26b1d", "Prusa", 29.99),
    ("Polymaker PC Grey", "PC", "#8a8d91", "Polymaker", 39.00),
    ("Sunlu TPU Clear", "TPU", "#d8e6ea", "Sunlu", 27.00),
]
DENSITY = {"PLA": 1.24, "PETG": 1.27, "ASA": 1.07, "PC": 1.20, "TPU": 1.21}

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
# Name, type, form, density, pack unit, pack price, pack size.
LAUNDRY = [
    ("Liquid detergent Color", "Liquid detergent", "detergent", 1.04, "ml", 9.95, 1500),
    (
        "Fabric softener Sensitive",
        "Fabric softener",
        "fabric_softener",
        1.0,
        "ml",
        2.49,
        1000,
    ),
    ("Oxygen whitener", "Whitener", "laundry_additive", 0.9, "g", 3.95, 750),
    (
        "Colour catcher sheets",
        "Colour catcher sheets",
        "laundry_additive",
        None,
        "pcs",
        3.49,
        20,
    ),
]
# Days ago, Program (None: never recognised), minutes into the load it is
# recognised, minutes, kWh, litres, grams of detergent off the scale, Outcome.
LOADS = [
    (26, "Cotton 60°", 0, 128, 1.12, 58.0, 78, "finished"),
    (23, "Eco 40-60", 0, 218, 0.71, 49.0, 72, "finished"),
    (20, "Wool", 0, 62, 0.38, 44.0, 41, "finished"),
    (17, None, 0, 95, 0.85, 52.0, 76, "finished"),
    (14, "Cotton 60°", 0, 125, 1.18, 56.5, 80, "finished"),
    (12, "Quick 30", 8, 31, 0.32, 38.0, 50, "finished"),
    (9, "Eco 40-60", 0, 40, 0.35, 30.5, 70, "cancelled"),
    (6, "Cotton 60°", 0, 131, 1.09, 57.0, 77, "finished"),
    (3, "Eco 40-60", 0, 221, 0.74, 48.0, 74, "finished"),
    (1, "Wool", 0, 60, 0.41, 46.0, 39, "finished"),
]
# A Program's minutes, kWh, litres and grams of detergent, for the long history.
TYPICAL = {
    "Cotton 60°": (128, 1.12, 57.0, 78),
    "Eco 40-60": (219, 0.72, 48.5, 72),
    "Wool": (61, 0.4, 45.0, 40),
    "Quick 30": (31, 0.32, 38.0, 50),
}
# The meters' readings before the first load.
WASHER_METERS = {
    "washer_energy": 412.5,
    "washer_water": 18250.0,
    "detergent_scale": 650.0,
}
# Days ago, hour it starts at, minutes, litres.
WATERINGS = [
    (12, 6, 20, 182.0),
    (9, 6, 20, 176.5),
    (6, 20, 35, 311.0),
    (4, 6, 20, 180.5),
    (2, 6, 25, 224.0),
    (1, 20, 15, 133.5),
]
IRRIGATION_WATER = 48200.0
# Name, type, form, density, pack unit, pack price, pack size.
DISHWASHER_PRODUCTS = [
    ("All-in-one tabs", "Dishwasher tabs", "dishwasher_product", None, "pcs", 8.99, 60),
    ("Dishwasher salt", "Dishwasher salt", "dishwasher_product", 1.2, "g", 1.49, 2000),
    ("Rinse aid Shine", "Rinse aid", "dishwasher_product", 1.02, "ml", 2.95, 750),
]
# Days ago, hour it starts at, Program, minutes, Outcome, then what each of the
# Device's meters counts, in their order.
DISHES = [
    (27, 20, "Eco 50°", 225, "finished", 0.78, 9.5),
    (24, 21, "Auto 45-65°", 150, "finished", 1.05, 11.0),
    (21, 20, "Eco 50°", 228, "finished", 0.8, 9.6),
    (18, 13, "Quick 45°", 58, "finished", 0.82, 10.5),
    (15, 20, "Intensive 70°", 170, "finished", 1.45, 14.5),
    (12, 20, "Eco 50°", 224, "finished", 0.77, 9.4),
    (9, 19, "Auto 45-65°", 40, "cancelled", 0.31, 4.0),
    (6, 20, "Eco 50°", 226, "finished", 0.79, 9.5),
    (3, 21, "Auto 45-65°", 148, "finished", 1.02, 10.8),
    (1, 20, "Eco 50°", 225, "finished", 0.78, 9.5),
]
# A Program's minutes, then what each meter counts, for the long history.
TYPICAL_DISHES = {
    "Eco 50°": (225, 0.78, 9.5),
    "Auto 45-65°": (150, 1.05, 11.0),
    "Intensive 70°": (170, 1.45, 14.5),
    "Quick 45°": (58, 0.82, 10.5),
}
DISHWASHER_METERS = {"dishwasher_energy": 286.4, "dishwasher_water": 3140.0}
DRYER_PRODUCTS = [
    ("Dryer sheets Fresh", "Dryer sheets", "laundry_additive", None, "pcs", 3.99, 80),
    (
        "Dryer fragrance Lavender",
        "Dryer fragrance",
        "laundry_additive",
        1.0,
        "ml",
        5.49,
        250,
    ),
]
TUMBLES = [
    (25, 11, "Cotton cupboard dry", 165, "finished", 1.32),
    (22, 18, "Synthetics", 95, "finished", 0.61),
    (19, 11, "Cotton iron dry", 140, "finished", 1.08),
    (16, 10, "Cotton cupboard dry", 170, "finished", 1.38),
    (12, 19, "Wool finish", 12, "finished", 0.08),
    (10, 11, "Cotton cupboard dry", 60, "cancelled", 0.45),
    (7, 11, "Cotton cupboard dry", 162, "finished", 1.29),
    (4, 18, "Synthetics", 92, "finished", 0.59),
    (2, 11, "Cotton iron dry", 138, "finished", 1.05),
]
TYPICAL_TUMBLES = {
    "Cotton cupboard dry": (165, 1.32),
    "Cotton iron dry": (140, 1.08),
    "Synthetics": (95, 0.61),
    "Wool finish": (12, 0.08),
}
DRYER_METERS = {"dryer_energy": 734.2}
COFFEE_PRODUCTS = [
    (
        "Espresso beans Crema",
        "Coffee beans",
        "beverage_ingredient",
        0.4,
        "g",
        14.99,
        1000,
    ),
    ("Whole milk", "Milk", "beverage_ingredient", 1.03, "ml", 1.19, 1000),
]
# Electricity and water are per Program, so a drink counts on no meter.
DRINKS = [
    (10, 7, "Espresso", 0.4, "finished"),
    (9, 8, "Cappuccino", 1.0, "finished"),
    (8, 7, "Lungo", 0.8, "finished"),
    (7, 15, "Espresso", 0.4, "finished"),
    (6, 8, "Latte macchiato", 1.3, "finished"),
    (5, 7, "Espresso", 0.2, "cancelled"),
    (5, 15, "Cappuccino", 1.0, "finished"),
    (4, 7, "Espresso", 0.4, "finished"),
    (3, 8, "Lungo", 0.8, "finished"),
    (2, 7, "Cappuccino", 1.0, "finished"),
    (1, 7, "Latte macchiato", 1.3, "finished"),
    (1, 15, "Espresso", 0.4, "finished"),
]
TYPICAL_DRINKS = {
    "Espresso": (0.4,),
    "Lungo": (0.8,),
    "Cappuccino": (1.0,),
    "Latte macchiato": (1.3,),
}
# Days ago, hour it starts at, Program (None: never recognised), minutes, Outcome.
COOKINGS = [
    (27, 18, "Fan plus 180°", 55, "finished"),
    (24, 12, "Pizza 220°", 25, "finished"),
    (21, 18, "Top/bottom heat 200°", 70, "finished"),
    (18, 19, None, 40, "finished"),
    (15, 17, "Fan plus 180°", 90, "finished"),
    (12, 18, "Grill", 20, "cancelled"),
    (9, 13, "Fan plus 180°", 45, "finished"),
    (6, 19, "Pizza 220°", 22, "finished"),
    (4, 18, "Top/bottom heat 200°", 65, "finished"),
    (1, 18, "Grill", 30, "finished"),
]
OVEN_PROGRAMS = {
    "Fan plus 180°": 1.1,
    "Top/bottom heat 200°": 1.4,
    "Grill": 0.9,
    "Pizza 220°": 0.8,
}
# Days ago, hour the car is plugged in, minutes charging, minutes it stays plugged in
# once full, kWh.
SESSIONS = [
    (25, 19, 240, 600, 38.5),
    (22, 18, 95, 0, 14.2),
    (19, 20, 180, 540, 29.0),
    (16, 19, 60, 0, 9.8),
    (13, 18, 300, 480, 47.6),
    (11, 21, 120, 420, 19.3),
    (8, 19, 75, 0, 11.9),
    (6, 18, 210, 600, 33.4),
    (3, 20, 140, 300, 22.7),
    (1, 19, 90, 0, 14.6),
]
# Days ago, hour it leaves the station at, minutes mowing, minutes charging after it,
# kWh the station counts, minutes it was stuck (0: never).
MOWS = [
    (20, 9, 90, 70, 0.25, 0),
    (18, 10, 110, 80, 0.3, 0),
    (16, 9, 75, 60, 0.2, 0),
    (14, 14, 100, 75, 0.28, 0),
    (12, 9, 85, 65, 0.24, 25),
    (10, 10, 115, 85, 0.31, 0),
    (8, 15, 80, 60, 0.22, 0),
    (6, 9, 95, 70, 0.27, 0),
    (4, 10, 90, 70, 0.26, 0),
    (2, 9, 95, 75, 0.27, 0),
]

TAGS = ["Customer Miller", "Household", "Garden", "Electronics", "Gifts", "Prototypes"]
