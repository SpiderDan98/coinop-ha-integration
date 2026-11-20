# Anycubic Kobra S1 in Home Assistant: available integrations and what they expose

Research for issue #2 ("How do you connect the Anycubic Kobra S1 to Home Assistant?"). As of 2026-11-19.
Primary sources: the integrations' repos (README, source code, releases, issues). Commit SHAs are pinned in the links.

## Summary

- **Two actively maintained HACS integrations exist. Both are in the HACS default catalog and both explicitly support the Kobra S1:**
  1. **`Nino6689/hass-anycubic`** ("Anycubic Cloud & LAN", domain `anycubic_cloud`). It is the maintained fork of the dead `WaresWichall/hass-anycubic_cloud`. Upstream's last release was Dec 2024, and the fork reports that it no longer starts on current HA. It works via the cloud **or** locally via LAN Mode. The project states its reference test hardware is a **Kobra S1 + ACE Pro**.
  2. **`chrisfore/anycubic_ha_local`** (domain `anycubic`). It works **locally only** (LAN Mode), with no account and no custom firmware. It is validated on the S1 Max. For the plain S1 its README claims "same feature set".
- **"Local" means the stock firmware's LAN Mode for both.** The printer then runs its own MQTT broker (TLS, port 9883). Credentials come from a handshake via `http://<ip>:18910/info`.
  - **Caveat:** turning LAN Mode on from the touchscreen removes the printer from the Anycubic account (confirmed on S1 FW 2.7.2.7).
  - Cloud and LAN are mutually exclusive on the printer.
- **Run start/end:** both protocols (cloud and LAN) report a job state with `printing`, `paused`, `finished`/`complete`, `stopped`/`cancelled`, plus preparation phases such as `preheating` and `levelling`. **There is no dedicated "error" state.** An error shows up as a pause or stop that carries a reason code.
  - `chrisfore` has the cleanest signal for Coin-op: `event.<printer>_print_event` fires `started`, `paused`, `resumed`, `finished`, `stopped` and `error` (`error` means an unrequested pause or stop). Each event carries `filename`, `progress` and, where relevant, `reason_code`.
  - `Nino6689` has `sensor.*_job_state` plus the binary_sensors `job_in_progress`, `job_complete`, `job_failed` and `job_is_paused`. It fires **no** HA events for the job lifecycle.
  - In LAN Mode, Nino6689 2.x moves `job_state` straight to `idle` when a print ends. `finished`/`cancelled` only persist from the 3.0 beta on.
- **Material usage:** the printer reports exactly **one** number per job, `supplies_usage`, in **mm**. It is the filament actually extruded, purge included.
  - **The printer measures nothing per slot.** Both integrations derive grams as mm × cross-section (1.75 mm) × material density.
  - A per-slot split is only an estimate: the slicer's `paint_infos` provide the ratios, which are applied to the actual total.
  - `Nino6689` computes that split but does not expose per-slot grams as an entity yet (issue #31, planned). `chrisfore` only exposes total grams.
- **Material and colour per ACE slot:** both expose them. The state is the material type, and attributes carry the colour hex and the SKU. The ACE's fill level (`consumables_percent`) always reads 0 on S1/ACE Pro, so it is useless.
- **Preview image:** `chrisfore` provides two local `image` entities, the slicer thumbnail and a 512×512 top view, fetched with a `fileDetails` request. `Nino6689` provides `image.*_job_preview`, but per its own mode table **only via the cloud**.
- **Camera:** both provide a local `camera` entity (HTTP-FLV on port 18088, via ffmpeg). `Nino6689` also has a cloud WebRTC camera, which cannot take snapshots.
- **Rinkhals (custom firmware, S1 supported) + Moonraker + `moonraker-home-assistant`** also works, but it is the riskier route:
  - it is a root firmware overlay;
  - job state comes from patched mapping, because GoKlipper reports `standby` first at print end and Rinkhals rewrites that;
  - the Moonraker HA integration has a history of breaking with Kobra printers;
  - whether GoKlipper fills `print_stats.filament_used` is **unconfirmed**.
- **Relevant to Coin-op's scope:** `Nino6689/hass-anycubic` **already computes electricity and filament cost per job**. It offers `job_energy`, `job_electricity_cost` and `last_job_total_cost`, reads a smart plug's energy sensor and supports dynamic tariffs. For the S1 this overlaps directly with Coin-op.

---

## 1. Candidate overview

| Project | Route | Kobra S1 | Latest release | Status |
|---|---|---|---|---|
| [Nino6689/hass-anycubic](https://github.com/Nino6689/hass-anycubic) | HACS, cloud **or** LAN Mode | ✅ the project's reference test hardware | v2.9.11 + v3.0.0-beta.5, both 2026-11-14 | very active, 9 open issues |
| [chrisfore/anycubic_ha_local](https://github.com/chrisfore/anycubic_ha_local) | HACS, LAN Mode only | ✅ "same feature set as S1 Max" (validated on S1 Max) | v1.4.0, 2026-11-18 | active, 0 open issues |
| [WaresWichall/hass-anycubic_cloud](https://github.com/WaresWichall/hass-anycubic_cloud) | HACS, cloud | (formerly) | v0.2.2, 2024-12-01 | **abandoned** |
| [rinkhals-community/Rinkhals](https://github.com/rinkhals-community/Rinkhals) + [moonraker-home-assistant](https://github.com/marcolivierarsenault/moonraker-home-assistant) | custom firmware + Moonraker | ✅ FW 2.7.0.9 / 2.7.2.7 | Rinkhals test builds 2026-11-19, Moonraker-HA 1.14.0 on 2026-11-13 | active, but invasive |
| [metheos/anycubic-s1-mqtt-bridge](https://github.com/metheos/anycubic-s1-mqtt-bridge) | Docker/add-on bridge, LAN → HA MQTT discovery | ✅ (S1-specific) | no releases, last commit 2026-02-19 | dormant, 7 open issues |
| [adamoutler/anycubic-homeassistant](https://github.com/adamoutler/anycubic-homeassistant) | – | ❌ Photon Mono X only ([README](https://github.com/adamoutler/anycubic-homeassistant/blob/master/README.md)) | – | not relevant |
| HA Core `anycubic` | – | – | does not exist (`homeassistant/components/anycubic` returns 404) | Nino6689 has a LAN-only core integration "prepared, not yet submitted" ([README](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#where-this-is-heading)) |

Metadata from the GitHub API (`gh api repos/<repo>` and `/releases`), queried 2026-11-19.

---

## 2. Nino6689/hass-anycubic ("Anycubic Cloud & LAN")

### Origin, maintenance, stability
- **Fork of the abandoned upstream.** It is the maintained fork of `WaresWichall/hass-anycubic_cloud` and has been in the HACS default catalog since August 2026.
  - It keeps the same domain (`anycubic_cloud`) and the same unique-id scheme.
  - Upstream 0.2.2 fails at setup on current HA because of a `paho-mqtt 1.6.1` dependency ([README "Project status"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#project-status)).
  - The upstream author wrote on 2024-10-23: "I'm not using anycubic anymore" ([WaresWichall#33](https://github.com/WaresWichall/hass-anycubic_cloud/issues/33)).
- **Single-maintainer project.** Its README says the Kobra S1 with ACE Pro "is the only hardware every change here is actually tested against". Other models are "supported by report rather than by verification" ([README "Hardware and testing scope"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#hardware-and-testing-scope)).
- **High churn.**
  - At least 40 releases since v2.0.0-beta.8 (2026-08-08).
  - A full clean-room rewrite, 3.0, has been in beta since 2026-09-28. It runs on the new libraries `anycubic-lan` and `anycubic-cloud-client`.
  - The release notes say entity ids are preserved ("128 of 129 entities read exactly what 2.x reads").
  - 3.0 requires HA ≥ 2025.10 ([v3.0.0-beta.1](https://github.com/Nino6689/hass-anycubic/releases/tag/v3.0.0-beta.1), [v3.0.0-beta.5](https://github.com/Nino6689/hass-anycubic/releases/tag/v3.0.0-beta.5)).
- **Reverse-engineered, no official API.** The project has asked Anycubic for a developer portal and is still waiting for a reply ([README](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#where-this-is-heading), [#40](https://github.com/Nino6689/hass-anycubic/issues/40)).
- **Dependencies.** 2.x depends on the PyPI library `anycubic-cloud-api==0.4.37` ([manifest.json](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/manifest.json)), whose source is [Nino6689/anycubic-cloud-api](https://github.com/Nino6689/anycubic-cloud-api). The manifest declares `iot_class: cloud_push` even though LAN is supported.

### Cloud vs. local
- **Cloud:** there is no password login. You paste a token taken from Anycubic Slicer Next, the web console or the Android app.
  - Only slicer tokens get MQTT push. Web tokens get polling only.
  - Tokens expire after 90 days ([README "Get an auth token"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#2-get-an-auth-token), [Troubleshooting](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#troubleshooting)).
  - By default MQTT is only connected "while a print is running" ([README "Choose a connect mode"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#4-choose-a-connect-mode)).
- **LAN Mode:** the printer runs its own MQTT broker.
  - Handshake: `GET http://<host>:18910/info`, then a signed request, then an AES-decrypted reply containing broker, username and password.
  - The broker listens on `mqtts://…:9883` with a self-signed certificate ([lan/handshake.py](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/lan/handshake.py#L1-L27), [const/lan.py](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/const/lan.py)).
  - Locally, "reports must be asked for … state is polled rather than streamed" ([lan/client.py](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/lan/client.py#L1-L25)). The README says polling runs about every 15 s.
- **README warning:** "Switching LAN Mode on removes the printer from your Anycubic account, and switching it back off does not restore it." Confirmed on Kobra S1 FW 2.7.2.7 ([README "Talk to the printer directly"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#5-optional-talk-to-the-printer-directly)).
- **What each mode gives you**, per the README table ([“What each mode gives you”](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#what-each-mode-gives-you)):
  - both modes: telemetry, ACE slots with material and colour, job tracking (progress, ETA, layers), controls;
  - **cloud only:** job preview image, lifetime counters, file library;
  - **LAN only:** camera snapshots and recording, AI-detection state.

### Entities (verified in code)
The entity descriptions are in [sensor.py](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/sensor.py), [binary_sensor.py](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/binary_sensor.py) and [image.py](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/image.py). Values are mapped in [coordinator.py L515–L578](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/coordinator.py#L515-L578).

| Coin-op need | Entity | Source / unit |
|---|---|---|
| Print state | `sensor.*_job_state` | `latest_project_print_status`, otherwise `"idle"` while the printer is online |
| | `binary_sensor.*_job_in_progress`, `*_job_complete`, `*_job_failed`, `*_job_is_paused` | from the project status |
| | `sensor.*_current_status` | printer status; `"moving"` while axes move |
| Error | `sensor.*_last_error_code`, `sensor.*_last_error` | sticky once set ("a fault is announced once") |
| Job/file name | `sensor.*_job_name` | `latest_project_name`; attributes include `filament_types`, `estimated_filament`, `created_timestamp`, `finished_timestamp`, `print_supplies_usage` ([coordinator.py L750–L758](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/coordinator.py#L750-L758)) |
| Filament used | `sensor.*_job_filament_used` | **mm** (`UnitOfLength.MILLIMETERS`), from `supplies_usage` ([sensor.py L430–L435](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/sensor.py#L430-L435)) |
| | `sensor.*_last_job_filament` (g, disabled by default), `sensor.*_job_filament_required` (g, forecast) | per README and coordinator |
| Remaining time | `sensor.*_job_time_remaining` (min), `sensor.*_job_eta` (timestamp), `sensor.*_job_time_elapsed` (min) | |
| Material/colour per slot | `sensor.*_ace_slot_1…4` (state = material; attributes `color_hex`, `colors_hex`, `sku`, `spool_loaded`), `sensor.*_ace_loaded_slot` (1-based) | |
| Remaining per slot | `sensor.*_ace_slot_N_filament_remaining` (g, estimate, disabled by default) | |
| Preview image | `image.*_job_preview` (key `job_image_url`) | cloud URL or `slice_param.image_id` ([project.py L1218ff](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/data_models/project.py#L1218-L1236)) |
| Camera | `camera.*_camera` (LAN, HTTP-FLV, snapshots via ffmpeg), `camera.*_cloud_camera` (WebRTC, no snapshots) | [README "Watching the printer"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#-watching-the-printer) |
| Cost | `sensor.*_job_cost`, `*_last_job_cost`, `*_job_energy`, `*_job_electricity_cost`, `*_last_job_energy`, `*_last_job_electricity_cost`, `*_last_job_total_cost` | [README "What your prints cost"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#-what-your-prints-cost), [energy.py](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/energy.py) |

**`job_state` values.** Defined in [project.py L1103–L1135](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/data_models/project.py#L1103-L1135), with the enum in [enums.py L10–L19](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/const/enums.py#L10-L19).
- Values: `paused`, `printing`, `finished` (code 2), `failed` (code 3 = *Cancelled*), `downloading`, `checking`, `preheating`, `slicing`, `levelling`.
- Unknown codes fall back to the printer's plain-text phase, otherwise `unknown`.
- So `job_failed` means "cancelled", **not** "error". The state does not distinguish a user cancel from a fault cancel. For that you need `last_error_code`.

**MQTT transitions parsed by the library.** In [printer.py L1224–L1302](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/data_models/printer.py#L1224-L1302), the library handles these `action/state` pairs:
- `start/printing`, `start/downloading`, `start/checking`, `start/preheating`, `start/finished`
- `pause/pausing|paused`, `resume/resuming|resumed`
- `start|stop/stoped|stopping` (sic, "stoped")

Every payload carries a `taskid`. These raw signals are what Run detection ultimately rests on.

**Events.** The code fires exactly one HA event: `anycubic_cloud` with `type: print_cloud_start`. It only fires when a print is started through the integration's own upload services ([services.py L507–L521](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/services.py#L507-L521)). There are **no** events for start, finish or cancel, so Coin-op would have to watch state changes.

**Known LAN Mode gap** ([#35](https://github.com/Nino6689/hass-anycubic/issues/35), maintainer comments).
- Since 2.9.1, `job_state` shows `idle` instead of `unavailable` when nothing is printing.
- But over LAN, a finished print goes **straight from `printing` to `idle`**, with no `finished` in between.
- `finished`/`cancelled` only persist from 3.0.0-beta.2 on. This matters for telling success from cancel.

**How per-slot filament is computed.** Sources: [filament.py](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/filament.py#L1-L21) and [L188–L234](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/filament.py#L188-L234).
- The base is `supplies_usage` (mm, actual, purge included), converted with a per-material density and 1.75 mm diameter.
- Multi-colour jobs are split by the ratios of the slicer's `paint_infos[].filament_used`. Single-material jobs are charged to the slot that was active during the print.
- A job that cannot be attributed is charged **nothing**.
- Slot remaining drops **only at job end**, in one step ([README "Filament remaining"](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#filament-remaining-estimated)).
- Per-slot grams per job are not exposed as an entity yet ([#31](https://github.com/Nino6689/hass-anycubic/issues/31), "still planned").
- `consumables_percent` (the ACE fill level) always reads 0 on S1 + ACE Pro (README "Unit telemetry").

---

## 3. chrisfore/anycubic_ha_local ("Local Control – NO Cloud")

### Maintenance, stability
- **Project state.** HACS default, AGPL-3.0, created 2026-06-15.
  - 33 releases; the latest is v1.4.0 on 2026-11-18.
  - 0 open and 23 closed issues, most of them resolved quickly (`gh issue list --state all`).
- **Printer support** ([README "Supported printers"](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/README.md#supported-printers)): "Kobra S1 Max ✅ Validated on hardware", "Kobra S1 ✅ Same feature set as the S1 Max". So there is no explicit hardware validation on the S1, which is an uncertainty.
- **Manifest** ([manifest.json](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/manifest.json)): `iot_class: local_push`; the only requirement is `paho-mqtt`.
- **Origin of the handshake.** This project documented the LAN handshake first. Nino6689 cites it as the source of its own independent implementation ([Nino handshake.py docstring](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/lan/handshake.py#L22-L25)).
- **Update behaviour.**
  - An early bug meant data only arrived while Anycubic Slicer was running ([#9](https://github.com/chrisfore/anycubic_ha_local/issues/9), closed).
  - Now there is a 30 s heartbeat poll (`DEFAULT_QUERY_INTERVAL = 30` in `const.py`).
  - Pushed `print`, `tempature` and `fan` reports are folded in as they arrive ([models.py `apply_progress`](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L278-L297)).

### Entities (verified in code)
Overview in the [README "Entities"](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/README.md#entities), checked against the code:

| Coin-op need | Entity | Code |
|---|---|---|
| Print state | sensor *Status* (derived from `info.state` + `project.state`), binary_sensors *Printing*, *Paused* | [models.py `parse_info` L177–L213](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L177-L213) |
| **Lifecycle events** | `event.*_print_event`; `event_types`: `started`, `paused`, `resumed`, `finished`, `stopped`, `error` (+ `clear_ready`/`clear_done`/`clear_failed` for bed cool-down); attributes `filename`, `progress`, plus `reason_code`/`reason` on pause/stop/error | [event.py](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/event.py), [coordinator.py `_fire`/`_track_status` L442–L473](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/coordinator.py#L442-L473) |
| Error reason | sensor *Pause reason*; codes such as 10401 *Paused by user*, 10601 *Stopped by user*, 11518 *Filament is stuck* | [README "Print events"](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/README.md#print-events-and-notifications) |
| File name | sensor *File name* (`project.filename`) | `parse_info` |
| Filament used | sensor *Filament used* in **g** (`SensorDeviceClass.WEIGHT`); attributes `length_mm`, `density`, `density_from` | [sensor.py L97–L145](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/sensor.py#L97-L145) |
| Remaining time | sensors *Time remaining*, *Elapsed time* (`remain_time`, `print_time`) | `parse_info` |
| Material/colour per slot | ACE *Slot 1–4* (material, `color_hex`, `sku`, `remaining` = `consumables_percent`), *Loaded slot*, *External spool* | [models.py `Slot` L23–L30](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L23-L30) |
| Preview image | `image` *Object thumbnail* (slicer preview) and *Object top view* (512×512 render); both **local**, via a `fileDetails` request sent once per job; base64, capped at 2 MB | [models.py L412–L458](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L412-L458), [coordinator.py `_request_file_details` L794](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/coordinator.py#L794-L806) |
| Camera | `camera` (printer's own stream, port 18088, ffmpeg); optional *Rinkhals camera* source | [camera.py L334](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/camera.py#L334), [rinkhals_camera.py](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/rinkhals_camera.py) |

**Event logic** (`_track_status`, [coordinator.py L450–L473](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/coordinator.py#L450-L473)):
- `started` fires on entering any of the `JOB_PHASES` = {preheating, auto_leveling, vibrating, flow_calibrating, printing, pausing, paused, resuming, resumed} ([const.py L408–L414](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/const.py#L408-L414)).
- `stopped` fires on entering {stopping, stoped, stopped}.
- `finished` fires on moving from a job phase to `idle`/`finished`.
- `error` fires once when a pause or stop carries a reason code that did not come from the user.

**Limitations:**
- **Grams rely on a guessed density.** It is taken from the file name (Anycubic's slicer puts the material in it), then from the active slot, and falls back to PLA. So there is **no** per-slot split for multi-material prints. The `paint_infos` from `fileDetails` are parsed ([models.py L417](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L417)) but not turned into per-slot usage.
- **Slot `remaining` is useless on the S1.** It is `consumables_percent`, which is effectively 0 there ([#5](https://github.com/chrisfore/anycubic_ha_local/issues/5)).

---

## 4. Rinkhals + Moonraker

- **What it is.** Rinkhals is "custom firmware for some Anycubic Kobra 3D printers" on GoKlipper.
  - It keeps the stock features and adds Moonraker, Mainsail/Fluidd, SSH (root/rockchip) and an apps system.
  - The Kobra S1 (+ Combo) is tested on FW `2.7.0.9` and `2.7.2.7` ([README](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/README.md#L25)).
  - It installs as an SWU file from USB, and the README carries a brick warning.
- **Maintainer change.** `jbatonnet/Rinkhals` was deprecated as of 2026-07-01, and development moved to `rinkhals-community/Rinkhals` ([jbatonnet README](https://github.com/jbatonnet/Rinkhals)). The new repo is very active, with test builds on 2026-11-17/18/19 and 14 open issues.
- **Moonraker integration.** Rinkhals runs "vanilla Moonraker plus a special Kobra component" that adapts Moonraker to GoKlipper ([docs/about/index.md](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/docs/docs/about/index.md)).
  - [kobra.py `patch_status` L855–L935](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/files/4-apps/home/rinkhals/apps/40-moonraker/kobra.py#L855-L935) rewrites GoKlipper states: `heating`/`leveling`/`resonance` → `printing`, `onpause` → `paused`, and several "complete" variants → `complete`.
  - Per the code comments, GoKlipper reports "standby the moment the gcode file is fully consumed, while its end-of-print routine is still running", and Moonraker would record that as *cancelled*.
  - So Rinkhals holds `printing` until `complete` arrives, with a safety-net timeout (Rinkhals issues #184 and #445, referenced in the code).
  - In other words, the state mapping is a heuristic, not native.
- **ACE.**
  - Rinkhals emulates a Happy Hare MMU object with `gate_material`, `gate_color` and `gate_filament_name` ([mmu_ace.py L1437ff](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/files/4-apps/home/rinkhals/apps/40-moonraker/mmu_ace.py#L1437-L1444)).
  - It also offers per-ACE-gate Spoolman tracking ([guides/spoolman-support.md](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/docs/docs/guides/spoolman-support.md)).
  - That makes per-spool usage via Moonraker/Spoolman conceivable.
- **HA side.** [moonraker-home-assistant](https://github.com/marcolivierarsenault/moonraker-home-assistant) (1.14.0, 2026-11-13) exposes, among others ([sensor.py L89–L246](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/40099a584eb3bef7e5616e3f70fc347b92b33c6b/custom_components/moonraker/sensor.py#L89-L246), [camera.py](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/40099a584eb3bef7e5616e3f70fc347b92b33c6b/custom_components/moonraker/camera.py)):
  - `print_state` (an ENUM from `print_stats.state`), `filename`, `filament_used` (m, from `print_stats.filament_used`), `print_time_left`, `print_eta`, `progress`;
  - a thumbnail camera (`PreviewCamera`) and an MJPEG camera.
  - It does **not** read the MMU object; no `mmu` appears in its code.
- **Stability history** (all of these issues are now closed):
  - Initially all sensors were missing with Rinkhals on the S1 ([jbatonnet/Rinkhals#62](https://github.com/jbatonnet/Rinkhals/issues/62), [moonraker-HA#465](https://github.com/marcolivierarsenault/moonraker-home-assistant/issues/465)).
  - Version 1.11.0 broke the S1 ([#619](https://github.com/marcolivierarsenault/moonraker-home-assistant/issues/619)).
  - Sensors froze after a print finished ([#634](https://github.com/marcolivierarsenault/moonraker-home-assistant/issues/634)).
  - A missing `hostname` in `printer.info` stopped the integration from loading ([#761](https://github.com/marcolivierarsenault/moonraker-home-assistant/issues/761)).
- **Uncertain:** whether GoKlipper/Rinkhals fills `print_stats.filament_used` with real values could **not be confirmed** from the sources. `kobra.py` does not patch that field. This needs a hardware test.
- **Rinkhals monitoring app:** it publishes **system metrics** via MQTT discovery to HA, not print data ([monitoring-app.md](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/docs/docs/about/monitoring-app.md)).
- **LAN Mode without losing the account:** the Rinkhals app `cloud2lan-bridge` turns on LAN Mode without removing the printer from the account, and keeps the Anycubic app working. The same page warns that the touchscreen toggle "removes the printer from your Anycubic account" on S1 FW 2.7.2.7 ([guides/anycubic-app-in-lan-mode.md](https://github.com/rinkhals-community/Rinkhals/blob/8cac7c49eac9ff96ea68e5c5c34c476c00a8d579/docs/docs/guides/anycubic-app-in-lan-mode.md)).

---

## 5. metheos/anycubic-s1-mqtt-bridge

- **What it is.** A Python/Docker service, also packaged as an HA add-on (`ha-addon/`).
  - It connects locally to the S1, using the `:18910/info` handshake ([asm.py L2358](https://github.com/metheos/anycubic-s1-mqtt-bridge/blob/8036d0cc9706844fd7dafb738590fbc66d158ff1/asm.py#L2358)).
  - It publishes entities to the HA broker via MQTT discovery: *Printer State*, temperatures, material and colour per slot, a preview image and a snapshot.
  - `supplies_usage` is published as `material_usage` ([asm.py L1548](https://github.com/metheos/anycubic-s1-mqtt-bridge/blob/8036d0cc9706844fd7dafb738590fbc66d158ff1/asm.py#L1548)).
  - The camera has to be configured by hand as an ffmpeg camera on `http://<ip>:18088/flv` ([README](https://github.com/metheos/anycubic-s1-mqtt-bridge/blob/8036d0cc9706844fd7dafb738590fbc66d158ff1/README.md#home-assistant-integration)).
- **Status.** Last commit 2026-02-19, no releases, 7 open issues, including "Wrong values" (2026-11-15) and "Discovery failed". **Not recommended** next to the two HACS integrations.

---

## 6. Anycubic primary sources

- **LAN guide.** The Anycubic wiki has a "LAN connection guide" for the Kobra S1 series ([DE](https://wiki.anycubic.com/de/fdm-3d-printer/kobra-s1/lan-connection-guide), [ZH](https://wiki.anycubic.com/zh/fdm-3d-printer/kobra-s1/lan-connection-guide)).
  - The pages are JavaScript-rendered and could not be fetched as text.
  - Per the search-result snippet of the ZH page, LAN Mode allows sending prints, viewing progress and video with Anycubic Slicer Next locally, and cloud remote control is disabled while it is on.
  - **Not verified first-hand.**
- **No API spec.** There is **no documented public API or MQTT specification from Anycubic**. Every project here is built on reverse engineering of the slicer and app ([Nino README](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/README.md#where-this-is-heading)). Error codes are listed in the Anycubic wiki ([example 11518](https://wiki.anycubic.com/en/error-codes/11518-code/k3), linked from the chrisfore README).

---

## 7. Implications for Coin-op (assessment, not a sourced claim)

1. **Run detection.** The most robust approach is to depend on a generic signal: "printing / not printing" plus an end state. Concretely, that is `event.*_print_event` (chrisfore) **or** state changes of `binary_sensor.*_job_in_progress` / `sensor.*_job_state` (Nino6689).
   - Success vs. cancel is only unambiguous with chrisfore (`finished` vs. `stopped`).
   - With Nino6689 it is unambiguous via the cloud or in 3.0 (`finished` vs. `failed`), but not in 2.x LAN Mode.
2. **Material.** The only measured value is total length in mm per job. Grams and the per-slot split are always derived (density, slicer ratios).
   - If Coin-op reads `job_filament_used` (mm) or `length_mm`, it stays independent of each integration's density heuristic.
   - Coin-op must capture the last value before the job ends, because job entities may reset or go unavailable afterwards.
3. **Images.** Only chrisfore provides the thumbnail locally; Nino6689 provides it via the cloud only. Both provide a local camera.
4. **Overlap.** Nino6689 already offers per-job electricity cost. Coin-op should decide whether to:
   - use it as a data source,
   - compete with it, or
   - deliberately differentiate, for example with cross-printer accounting or a Run history with images.

## Open questions / uncertainties

- **chrisfore on the plain Kobra S1** (not Max): only "same feature set" is claimed. It is not hardware-validated.
- **Nino6689 3.0 local preview image:** not checked. The 3.0 code lives in a separate repo ([hass-anycubic-next](https://github.com/Nino6689/hass-anycubic-next)) or on a beta tag.
- **Multiple simultaneous LAN clients:** whether the printer's LAN broker accepts several at once (both integrations plus the slicer) is not documented. chrisfore#9 suggests the slicer and HA can run side by side.
- **`print_stats.filament_used` under Rinkhals/GoKlipper:** unconfirmed.
- **`supplies_usage` across pause/resume and after the end:**
  - How the value behaves across pause/resume is undocumented.
  - Whether it stays in `info.last_project` after the end is also unclear. chrisfore's code treats `last_project` as a fallback for `project` ([models.py L180](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L180)), but the actual S1 behaviour is not documented.
