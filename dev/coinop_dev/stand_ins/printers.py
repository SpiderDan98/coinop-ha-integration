"""How the 3D printer integrations register a printer."""

from typing import Any

from . import ENTRY_ID, EntityShape, HaDeviceShape, Registration

# A camera that streams nothing, and an image entity's state: when its picture changed.
CAMERA = "idle"
PICTURE = "2026-05-01T09:30:00+00:00"

ANYCUBIC_LOCAL_EVENT_TYPES = [
    "started",
    "paused",
    "resumed",
    "finished",
    "stopped",
    "error",
    "clear_ready",
    "clear_done",
    "clear_failed",
]


def anycubic_local(
    *,
    serial: str = "S1SERIAL",
    images: tuple[str, ...] = ("object_thumbnail", "object_top_view"),
) -> Registration:
    """chrisfore/anycubic_ha_local (domain `anycubic`): a Kobra S1 with an ACE Pro,
    unique ids `<serial>_<key>`, the ACE its own HA device linked to the printer. Its
    image entities only exist after the printer's first job, so `images` may leave
    them out."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{serial}_{key}", **kwargs)

    def ace(key: str, state: str) -> tuple[str, EntityShape]:
        return f"ace0_{key}", EntityShape(
            "sensor",
            f"{serial}_ace0_{key}",
            state=state,
            object_id=f"ace_pro_{key}",
            linked=True,
        )

    entities = [
        # Its state is when the last event came, which none has yet.
        own(
            "event",
            "print_event",
            state="unknown",
            capabilities={"event_types": ANYCUBIC_LOCAL_EVENT_TYPES},
        ),
        own("sensor", "status", state="idle"),
        own(
            "sensor",
            "filename",
            state="benchy.gcode",
            object_id="anycubic_kobra_s1_file_name",
        ),
        own("sensor", "filament_used", state="0", unit="g"),
        own("sensor", "pause_reason", state="none"),
        own("binary_sensor", "printing", state="off"),
        own("camera", "camera", state=CAMERA),
        *(own("image", key, state=PICTURE) for key in images),
        *(ace(f"slot_{number}", "PLA") for number in range(1, 5)),
        ace("loaded_slot", "1"),
        ace("humidity", "32"),
    ]
    return Registration(
        "anycubic",
        (
            HaDeviceShape(
                {
                    "identifiers": {("anycubic", serial)},
                    "manufacturer": "Anycubic",
                    "name": "Anycubic Kobra S1",
                    "model": "Anycubic Kobra S1",
                },
                dict(entities),
                linked={
                    "identifiers": {("anycubic", f"{serial}_ace0")},
                    "manufacturer": "Anycubic",
                    "name": "ACE Pro",
                    "model": "ACE Pro",
                },
            ),
        ),
    )


def anycubic_cloud(
    *, mac: str = "aa:bb:cc:dd:ee:ff", name: str = "Kobra S1", cloud: bool = True
) -> Registration:
    """Nino6689/hass-anycubic (domain `anycubic_cloud`), 2.x and 3.0 alike: a Kobra S1
    with an ACE Pro, unique ids `<MAC>-<key>`. The job preview only exists with the
    cloud."""

    def add(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{mac}-{key}", **kwargs)

    def ace(key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return add("sensor", key, linked=True, **kwargs)

    entities = [
        add("sensor", "job_state", state="idle"),
        add("sensor", "job_name", state="benchy"),
        add("sensor", "job_filament_used", state="0", unit="mm"),
        add("sensor", "job_filament_required", state="0"),
        add("sensor", "job_energy", state="0", unit="kWh"),
        add("sensor", "job_electricity_cost", state="0"),
        add("sensor", "last_job_total_cost", state="0.42"),
        add("binary_sensor", "job_in_progress", state="off"),
        add("camera", "camera", state=CAMERA),
        *(
            [
                add(
                    "image",
                    "job_image_url",
                    state=PICTURE,
                    object_id=f"{name}_job_preview",
                ),
                add("camera", "cloud_camera", state=CAMERA),
            ]
            if cloud
            else []
        ),
        *(
            entry
            for number in range(1, 5)
            for entry in (
                ace(f"ace_slot_{number}", state="PLA"),
                ace(f"ace_slot_{number}_filament_remaining", state="640", unit="g"),
            )
        ),
        ace("ace_loaded_slot", state="1"),
        ace("secondary_ace_loaded_slot", state="unknown"),
    ]
    return Registration(
        "anycubic_cloud",
        (
            HaDeviceShape(
                {
                    "identifiers": {("anycubic_cloud", "1234-5678")},
                    "manufacturer": "Anycubic",
                    "name": name,
                    "model": "Anycubic Kobra S1",
                },
                dict(entities),
                linked={
                    "identifiers": {("anycubic_cloud", "1234-5678-ace0")},
                    "manufacturer": "Anycubic",
                    "name": f"{name} ACE Pro",
                    "model": "ACE Pro",
                },
            ),
        ),
    )


BAMBU_LAB_PRINT_STATUS_OPTIONS = [
    "failed",
    "finish",
    "idle",
    "init",
    "offline",
    "pause",
    "prepare",
    "running",
    "slicing",
    "unknown",
]


def bambu_lab(*, serial: str = "01P00A123456789", camera: bool = True) -> Registration:
    """greghesp/ha-bambulab (domain `bambu_lab`): a P1S with an AMS, unique ids
    `<serial>_<key>`; the AMS is its own HA device linked to the printer, its unique
    ids `<model>_<serial>_AMS_<AMS serial>_<key>`. Without `camera` the printer has the
    option on that offers its chamber picture as an image entity instead of a camera."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{serial}_{key}", **kwargs)

    def ams(key: str, state: str) -> tuple[str, EntityShape]:
        return f"ams_{key}", EntityShape(
            "sensor",
            f"P1S_{serial}_AMS_006A123456_{key}",
            state=state,
            object_id=f"ams_1_{key}",
            linked=True,
        )

    entities = [
        own(
            "sensor",
            "print_status",
            state="idle",
            capabilities={"options": BAMBU_LAB_PRINT_STATUS_OPTIONS},
        ),
        own("sensor", "subtask_name", state="Benchy"),
        own("sensor", "print_weight", state="12.4", unit="g"),
        own("sensor", "print_length", state="4.1", unit="m"),
        own("sensor", "print_progress", state="0", unit="%"),
        own("sensor", "active_tray", state="none"),
        own("image", "cover_image", state=PICTURE),
        own("image", "pick_image", state=PICTURE),
        own("camera", "camera", state=CAMERA)
        if camera
        else own("image", "p1p_camera", state=PICTURE),
        *(ams(f"tray_{number}", "PLA Basic") for number in range(1, 5)),
        ams("ams_status", "idle"),
        ams("humidity_index", "2"),
    ]
    return Registration(
        "bambu_lab",
        (
            HaDeviceShape(
                {
                    "identifiers": {("bambu_lab", serial)},
                    "manufacturer": "Bambu Lab",
                    "name": "P1S",
                    "model": "P1S",
                },
                dict(entities),
                linked={
                    "identifiers": {("bambu_lab", "006A123456")},
                    "manufacturer": "Bambu Lab",
                    "name": "AMS 1",
                    "model": "AMS",
                },
            ),
        ),
    )


PRUSALINK_PRINTER_STATE_OPTIONS = [
    "idle",
    "busy",
    "printing",
    "paused",
    "finished",
    "stopped",
    "error",
    "attention",
    "ready",
]


def prusalink(*, title: str = "Prusa MK4") -> Registration:
    """Home Assistant's PrusaLink (domain `prusalink`): an MK4, unique ids
    `<config entry id>_<key>`; the HA device is the config entry's, named after its
    title."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{ENTRY_ID}_{key}", **kwargs)

    entities = [
        # Named after the HA device itself.
        own(
            "sensor",
            "printer.state",
            state="idle",
            capabilities={"options": PRUSALINK_PRINTER_STATE_OPTIONS},
            object_id=title,
        ),
        own("sensor", "job.filename", state="unknown"),
        own("sensor", "job.progress", state="unknown", unit="%"),
        # The filament type, not an amount.
        own("sensor", "printer.telemetry.material", state="PLA"),
        own(
            "sensor",
            "printer.telemetry.temp-nozzle",
            state="24.5",
            unit="°C",
            disabled=True,
        ),
        own("camera", "job_preview", state=CAMERA),
        own("button", "job.cancel", state="unknown"),
    ]
    return Registration(
        "prusalink",
        (
            HaDeviceShape(
                {
                    "identifiers": {("prusalink", ENTRY_ID)},
                    "manufacturer": "Prusa",
                    "name": title,
                },
                dict(entities),
            ),
        ),
        entry={"title": title},
    )


OCTOPRINT_DEVICE_ID = "6f2c5b1e-8a0d-4c3b-9e7f-1a2b3c4d5e6f"
OCTOPRINT_CURRENT_STATE_OPTIONS = [
    "open_serial",
    "detect_serial",
    "connecting",
    "operational",
    "starting_sd",
    "starting_streaming",
    "starting",
    "printing_sd",
    "printing_streaming",
    "printing",
    "cancelling",
    "pausing",
    "paused",
    "resuming",
    "finishing",
    "offline",
    "error",
    "offline_after_error",
    "transferring_file",
]


def octoprint(*, camera: bool = True) -> Registration:
    """Home Assistant's `octoprint`: a printer, unique ids `<Name>-<device id>`, the
    device id being the config entry's unique id; the camera's unique id is the device
    id alone. Without `camera` the webcam is turned off in OctoPrint."""

    def own(platform: str, name: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return name, EntityShape(platform, f"{name}-{OCTOPRINT_DEVICE_ID}", **kwargs)

    entities = [
        # Before `Current File`, so a match on that name alone would take it.
        own("sensor", "Current File Size", state="1.2", unit="MB"),
        own(
            "sensor",
            "Current State",
            state="operational",
            capabilities={"options": OCTOPRINT_CURRENT_STATE_OPTIONS},
        ),
        own("sensor", "Current File", state="benchy.gcode"),
        own("sensor", "Job Percentage", state="0", unit="%"),
        own("sensor", "Estimated Finish Time", state="unknown"),
        own("sensor", "Start Time", state="unknown"),
        own("sensor", "actual tool0 temp", state="24.5", unit="°C"),
        own("binary_sensor", "Printing", state="off"),
        own("binary_sensor", "Printing Error", state="off"),
    ]
    if camera:
        entities.append(
            (
                "camera",
                EntityShape(
                    "camera",
                    OCTOPRINT_DEVICE_ID,
                    state=CAMERA,
                    object_id="octoprint_camera",
                ),
            )
        )
    return Registration(
        "octoprint",
        (
            HaDeviceShape(
                {
                    "identifiers": {("octoprint", OCTOPRINT_DEVICE_ID)},
                    "manufacturer": "OctoPrint",
                    "name": "OctoPrint",
                },
                dict(entities),
            ),
        ),
        entry={"unique_id": OCTOPRINT_DEVICE_ID},
    )


CREALITY_PRINT_STATUS_OPTIONS = [
    "off",
    "error",
    "self-testing",
    "completed",
    "paused",
    "stopped",
    "printing",
    "processing",
    "idle",
]


def creality(*, host: str = "192.168.1.50", camera: bool = True) -> Registration:
    """3dg1luk43/ha_creality_ws (domain `ha_creality_ws`): a K1C, unique ids
    `<host>-<key>`; the job's file is the `file` attribute of the print status.
    Without `camera` the camera is set up in custom mode without a URL."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{host}-{key}", **kwargs)

    entities = [
        own(
            "sensor",
            "print_status",
            state="idle",
            capabilities={"options": CREALITY_PRINT_STATUS_OPTIONS},
        ),
        own("sensor", "used_material_length", state="0", unit="cm"),
        own("sensor", "expected_material_length", state="0", unit="cm"),
        own("sensor", "filament_consumption", state="0", unit="g"),
        own("sensor", "print_job_time", state="0", unit="s"),
        own("image", "current_print_preview", state=PICTURE),
        *([own("camera", "camera", state=CAMERA)] if camera else []),
    ]
    return Registration(
        "ha_creality_ws",
        (
            HaDeviceShape(
                {
                    "identifiers": {("ha_creality_ws", host)},
                    "manufacturer": "Creality",
                    "name": "K1C",
                    "model": "K1C",
                },
                dict(entities),
            ),
        ),
    )


ELEGOO_RESIN_STATUS_OPTIONS = [
    "idle",
    "homing",
    "dropping",
    "printing",
    "lifting",
    "pausing",
    "paused",
    "stopping",
    "stopped",
    "complete",
    "file_checking",
    "recovery",
    "printing_recovery",
    "loading",
    "preheating",
    "leveling",
]
ELEGOO_FDM_STATUS_OPTIONS = [
    *ELEGOO_RESIN_STATUS_OPTIONS,
    "printers_checking",
    "resuming",
    "error",
    "resonance_testing",
    "print_started",
    "auto_leveling_completed",
    "preheating_completed",
    "homing_completed",
    "resonance_testing_completed",
    "auto_feeding",
    "filament_unloading",
    "filament_unload_abnormal",
    "filament_unload_paused",
    "unrecognized",
]


def elegoo(
    *,
    machine_id: str = "f25273b12b094c5a8b9513a30ca60049",
    resin: bool = False,
    cover_image: bool = True,
) -> Registration:
    """danielcherubini/elegoo-homeassistant (domain `elegoo_printer`): a Centauri
    Carbon (FDM, with OpenCentauri firmware), or with `resin` a Saturn, which has no
    extrusion sensor, unique ids `<machine id>_<key>`. Without `cover_image` the
    printer speaks the MQTT protocol, which has no cover image."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{machine_id}_{key}", **kwargs)

    options = ELEGOO_RESIN_STATUS_OPTIONS if resin else ELEGOO_FDM_STATUS_OPTIONS
    model = "Saturn 4 Ultra" if resin else "Centauri Carbon"
    entities = [
        own("sensor", "print_status", state="idle", capabilities={"options": options}),
        own("sensor", "current_status", state="idle"),
        own("sensor", "filename", state="benchy.gcode"),
        own("sensor", "percent_complete", state="0", unit="%"),
        *(
            []
            if resin
            else [
                own("sensor", "current_extrusion", state="0", unit="mm"),
                own("sensor", "total_extrusion", state="123456.7", unit="mm"),
            ]
        ),
        *([own("image", "cover_image", state=PICTURE)] if cover_image else []),
        own("camera", "chamber_camera", state=CAMERA),
    ]
    return Registration(
        "elegoo_printer",
        (
            HaDeviceShape(
                {
                    "identifiers": {("elegoo_printer", machine_id)},
                    "manufacturer": "Elegoo",
                    "name": model,
                    "model": model,
                },
                dict(entities),
            ),
        ),
    )


MOONRAKER_PRINT_STATE_OPTIONS = [
    "standby",
    "printing",
    "paused",
    "complete",
    "cancelled",
    "error",
]


def moonraker(*, webcam: bool = True) -> Registration:
    """marcolivierarsenault/moonraker-home-assistant (domain `moonraker`): a Klipper
    printer, unique ids `<config entry id>_<key>`, all on one HA device. Its preview is
    the camera `thumbnail`; a webcam is a camera `<entry id>_<webcam name>_<index>`."""

    def own(platform: str, key: str, **kwargs: Any) -> tuple[str, EntityShape]:
        return key, EntityShape(platform, f"{ENTRY_ID}_{key}", **kwargs)

    entities = [
        # The printer's own state, which a print's state is not.
        own(
            "sensor",
            "state",
            state="ready",
            capabilities={"options": ["ready", "startup", "shutdown", "error"]},
        ),
        own(
            "sensor",
            "print_state",
            state="standby",
            capabilities={"options": MOONRAKER_PRINT_STATE_OPTIONS},
        ),
        own("sensor", "filename", state="benchy.gcode"),
        # The printer's lifetime extrusion, which also ends in `_filament_used`.
        own("sensor", "total_filament_used", state="1523.4", unit="m"),
        own("sensor", "filament_used", state="0", unit="m"),
        own("sensor", "progress", state="0", unit="%"),
        own("camera", "thumbnail", state=CAMERA),
        *([own("camera", "Chamber_0", state=CAMERA)] if webcam else []),
    ]
    return Registration(
        "moonraker",
        (
            HaDeviceShape(
                {
                    "identifiers": {("moonraker", ENTRY_ID)},
                    "name": "Voron 2.4",
                    "model": "Klipper",
                },
                dict(entities),
            ),
        ),
        entry={"title": "Voron 2.4"},
    )
