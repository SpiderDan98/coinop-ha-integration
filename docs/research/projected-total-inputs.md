# Inputs for a Run's projected total: what each supported integration exposes

Research for issue #128 ("Projected Total of an open Run": the cost measured so far plus the rest still to come). As of 2026-11-22.
Primary sources: the entity descriptions in each integration's source code. Commit SHAs are pinned in the links.

## Summary

- **Remaining time is available almost everywhere, but in different shapes.**
  - Some integrations report a duration, in minutes, seconds, milliseconds or hours.
  - Others report only a finish timestamp: PrusaLink, OctoPrint, HA core Home Connect, LG ThinQ, SmartThings and Home Connect Alt.
  - A projection has to accept both and reduce them to "seconds left".
- **Progress (%)** is available on every printer integration. Most appliance integrations have it too. Where it is missing (Miele, LG ThinQ), it can be derived from elapsed and remaining (or total) time.
- **Several values drop out while paused.** OctoPrint's finish time and Moonraker's time left, ETA and progress go to None or 0 while a print is paused. The last known value has to be held.
- **The planned total material** comes from the slicer and is the better basis for the material still to come. It is exposed by:
  - Anycubic Cloud & LAN: attribute `estimated_filament`;
  - Bambu Lab: weight and length, also per slot;
  - Creality: length in the unit Coin-op already reads;
  - Elegoo: on the CC2 protocol only, per slot only through a gcode proxy.

  Anycubic Local and Moonraker read it internally but expose no entity. PrusaLink and OctoPrint expose no material at all.
- **The drying state of a multi-material unit** is exposed by only three integrations:
  - both Anycubic integrations: on/off and the minutes of drying left;
  - Bambu Lab: AMS 2 Pro, AMS HT and AMS 3H, on recent firmware.

  Creality's CFS, Elegoo's CANVAS and every other printer integration report no drying. Moonraker exposes real heater duty cycles (%), including `heater_generic` heaters.
- **Appliance forecasts are relative.** Miele's energy and water forecast and Home Connect's `EnergyForecast`/`WaterForecast` are percentages, not kWh or litres, and HA core Home Connect doesn't expose them at all. WashData already publishes a projected total itself: `projected_energy_kwh` and `projected_cost`.
- **EV chargers:** only evcc gives what a projection needs, namely the energy still to charge, the remaining time and the target SoC. go-e gives it only while a session energy limit is set. Tesla Wall Connector, Easee, Zaptec, OCPP and Wallbox report no target at all.

## 3D printers

Suffixes are written for the profiles' `find(domain, suffix)`.

### Anycubic 3D Printer - Local Control (`chrisfore/anycubic_ha_local` @ `8ef65afd`)

Unique ids are `<serial>_<key>`, and an ACE's are `<serial>_ace<N>_<key>` ([entity.py#L41](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/entity.py#L41), [#L65](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/entity.py#L65)).

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `_progress` | % | | [definitions.py#L43-L45](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/definitions.py#L43-L45) |
| Remaining time | `sensor`, `_time_remaining` | min | | [definitions.py#L50-L53](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/definitions.py#L50-L53) |
| Planned material | not exposed | | The slicer's `paint_infos` are parsed but no entity is made from them. | [models.py#L417](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L417) |
| Drying on/off | `switch`, `_ace0_drying` | on/off | Only on an ACE with a dry box. Its state is echoed only on the next poll. | [switch.py#L24-L56](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/switch.py#L24-L56) |
| Drying left | `sensor`, `_ace0_drying_remaining` | min | 0 while drying is off. Unknown until a report says either way. Dry box only. | [definitions.py#L117-L123](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/definitions.py#L117-L123), [models.py#L74-L91](https://github.com/chrisfore/anycubic_ha_local/blob/8ef65afd2493c148bf70ee40c6168a2b8efe9b41/custom_components/anycubic/anycubic_local/models.py#L74-L91) |

### Anycubic Cloud & LAN (`Nino6689/hass-anycubic` @ `826065ad`)

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `-job_progress` | % | | [sensor.py#L382-L387](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/sensor.py#L382-L387) |
| Remaining time | `sensor`, `-job_time_remaining` | min | Also `-job_eta` (timestamp) | [sensor.py#L394-L399](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/sensor.py#L394-L399) |
| Planned material | attribute `estimated_filament` on `sensor`, `-job_name` | | | [coordinator.py#L750-L758](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/coordinator.py#L750-L758) |
| Drying on/off | `binary_sensor`, `-dry_status_is_drying`; second ACE `-secondary_dry_status_is_drying` | on/off | | [binary_sensor.py#L57-L69](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/binary_sensor.py#L57-L69) |
| Drying left | `sensor`, `-dry_status_remaining_time`; also `-dry_status_total_duration`, `-dry_status_target_temperature` (°C), and `secondary_` for a second ACE | **no unit declared**; minutes, as the integration's own card shows it ([stats_component.ts#L282-L300](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/frontend_panel/src/components/printer_card/stats/stats_component.ts#L282-L300)), and 0 while not drying (`AnycubicDryingStatus.remaining_time` in `anycubic-cloud-api` 0.4.37) | | [sensor.py#L70-L86](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/sensor.py#L70-L86), [#L199-L213](https://github.com/Nino6689/hass-anycubic/blob/826065adf4a12145a017856d91630a6deb4dde3a/custom_components/anycubic_cloud/sensor.py#L199-L213) |

### Bambu Lab (`greghesp/ha-bambulab` @ `7c740224`)

The printer's unique ids are `<serial>_<key>`. Each AMS is its own HA device with unique ids `<device_type>_<serial>_AMS_<ams_serial>_<key>`, so with several AMS units one suffix matches several entities ([sensor.py#L272](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/sensor.py#L272)).

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `_print_progress` | % | | [definitions.py#L564-L571](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/definitions.py#L564-L571) |
| Remaining time | `sensor`, `_remaining_time`; `_end_time` | min; timestamp | | [definitions.py#L633-L671](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/definitions.py#L633-L671) |
| Planned material | `sensor`, `_print_weight` (already read); `_print_length` | g; m; per-slot attributes | Planned. Local prints need FTP; others use the cloud task. Unknown shows as `0`. | [definitions.py#L733-L762](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/definitions.py#L733-L762), [models.py#L1374-L1387](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/pybambu/models.py#L1374-L1387) |
| Drying on/off | AMS `binary_sensor`, `_drying` | on/off | AMS 2 Pro, AMS HT and AMS 3H only, with firmware A1 ≥ 01.06.10.33, P1 ≥ 01.07.50.18 or X1 ≥ 01.08.50.18; never on the X1E | [definitions.py#L192-L204](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/definitions.py#L192-L204), [models.py#L354-L375](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/pybambu/models.py#L354-L375) |
| Drying left | AMS `sensor`, `_remaining_drying_time` | min | Same models | [definitions.py#L1031-L1042](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/definitions.py#L1031-L1042) |
| Extra load | `sensor`, `_target_chamber_temp` | °C | Chamber heater on the X1E, H2, H3 and X2 series only. No heater power. | [definitions.py#L375-L396](https://github.com/greghesp/ha-bambulab/blob/7c740224c72401890ac9744643aa1b0c73e732f4/custom_components/bambu_lab/definitions.py#L375-L396) |

### PrusaLink (HA core @ `d70e445d`)

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `_job.progress` | % | Unavailable while idle | [sensor.py#L172-L181](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/prusalink/sensor.py#L172-L181) |
| Remaining time | `sensor`, `_job.finish` | timestamp | No duration. Changes under 2 min are ignored. | [sensor.py#L208-L224](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/prusalink/sensor.py#L208-L224) |
| Planned material, drying | not exposed | | | |

### OctoPrint (HA core @ `d70e445d`)

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `Job Percentage-` (`start=True`) | % | Shows 0 without a value | [sensor.py#L167-L190](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/octoprint/sensor.py#L167-L190) |
| Remaining time | `sensor`, `Estimated Finish Time-` (`start=True`) | timestamp | None while paused | [sensor.py#L193-L221](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/octoprint/sensor.py#L193-L221) |
| Planned material, drying | not exposed | | | |

### Creality (`3dg1luk43/ha_creality_ws` @ `58c00818`)

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `-print_progress` | % | | [sensor.py#L134-L144](https://github.com/3dg1luk43/ha_creality_ws/blob/58c00818e8303a0d636bd05929cad215aed9ccb3/custom_components/ha_creality_ws/sensor.py#L134-L144) |
| Remaining time | `sensor`, `-print_left_time` | s | 0 while the printer is off | [sensor.py#L567-L582](https://github.com/3dg1luk43/ha_creality_ws/blob/58c00818e8303a0d636bd05929cad215aed9ccb3/custom_components/ha_creality_ws/sensor.py#L567-L582) |
| Planned material | `sensor`, `-expected_material_length`; `-expected_material_weight` | cm (as `-used_material_length`); g | Planned. Created only once the firmware has answered for a job. The weight is unknown for Creality Print files and multi-material jobs. | [sensor.py#L463-L525](https://github.com/3dg1luk43/ha_creality_ws/blob/58c00818e8303a0d636bd05929cad215aed9ccb3/custom_components/ha_creality_ws/sensor.py#L463-L525) |
| Drying | not exposed | | The CFS reports temperature and humidity only | [sensor.py#L717-L758](https://github.com/3dg1luk43/ha_creality_ws/blob/58c00818e8303a0d636bd05929cad215aed9ccb3/custom_components/ha_creality_ws/sensor.py#L717-L758) |

### Elegoo (`danielcherubini/elegoo-homeassistant` @ `ce9c1559`)

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `_percent_complete` | % | | [definitions.py#L776-L787](https://github.com/danielcherubini/elegoo-homeassistant/blob/ce9c1559cb439e8d77ba860d42572d3c2b404a26/custom_components/elegoo_printer/definitions.py#L776-L787) |
| Remaining time | `sensor`, `_ticks_remaining`; `_end_time` | **ms**; timestamp | The end time updates only while printing | [definitions.py#L715-L737](https://github.com/danielcherubini/elegoo-homeassistant/blob/ce9c1559cb439e8d77ba860d42572d3c2b404a26/custom_components/elegoo_printer/definitions.py#L715-L737) |
| Planned material | `sensor`, `_total_filament_used` (CC2 only, g, no unit declared); `_a{1..4}_grams` per slot (with a gcode proxy only) | g | Planned | [definitions.py#L1307-L1363](https://github.com/danielcherubini/elegoo-homeassistant/blob/ce9c1559cb439e8d77ba860d42572d3c2b404a26/custom_components/elegoo_printer/definitions.py#L1307-L1363) |
| Drying | not exposed | | CANVAS reports no temperature or humidity | [ams.py#L99-L101](https://github.com/danielcherubini/elegoo-homeassistant/blob/ce9c1559cb439e8d77ba860d42572d3c2b404a26/custom_components/elegoo_printer/sdcp/models/ams.py#L99-L101) |

### Moonraker (`marcolivierarsenault/moonraker-home-assistant` @ `069064a9`)

| Input | Entity | Unit | Caveats | Source |
|---|---|---|---|---|
| Progress | `sensor`, `_progress` | % | 0 when not printing, paused included | [sensor.py#L246-L260](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/069064a9b1e062bdbb64c26000db21aec0b344da/custom_components/moonraker/sensor.py#L246-L260) |
| Remaining time | `sensor`, `_print_time_left`; `_slicer_print_time_left_estimate`; `_print_eta` | **h**; h; timestamp | 0 or None while paused | [sensor.py#L156-L222](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/069064a9b1e062bdbb64c26000db21aec0b344da/custom_components/moonraker/sensor.py#L156-L222) |
| Planned material | not exposed | | `filament_total` is fetched but only used for its time calculation | [__init__.py#L662-L664](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/069064a9b1e062bdbb64c26000db21aec0b344da/custom_components/moonraker/__init__.py#L662-L664) |
| Drying | not exposed | | | |
| Extra load | `sensor`, `_heater_generic_<name>_power`, `_heater_bed_power`, `_extruder_power` | % duty | Real duty cycle | [sensor.py#L704-L778](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/069064a9b1e062bdbb64c26000db21aec0b344da/custom_components/moonraker/sensor.py#L704-L778) |

## Appliances

| Integration | Progress | Remaining time | Forecast | Notes |
|---|---|---|---|---|
| Miele (core @ `d70e445d`) | not exposed, derive it | `sensor`, `-state_remaining_time` (min, diagnostic); `-state_finish_timestamp`; `-state_elapsed_time` | `sensor`, `-energy_forecast`, `-water_forecast`: **%**, not kWh | Also reports consumption so far, already read. [sensor.py#L330-L514](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/miele/sensor.py#L330-L514) |
| Home Connect (core) | `sensor`, `-BSH.Common.Option.ProgramProgress` | `sensor`, `-BSH.Common.Option.RemainingProgramTime`: **timestamp** | not exposed | Both only while running, paused, delayed or finished. [sensor.py#L55-L88](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/home_connect/sensor.py#L55-L88) |
| LG ThinQ (core) | not exposed, derive it | `sensor`, `_…remain` (timestamp); `_…total` (min) | not exposed | [sensor.py#L373-L429](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/lg_thinq/sensor.py#L373-L429) |
| SmartThings (core) | `sensor`, `_main_samsungce.washerOperatingState_progress_progress` (also `dryer…`) | `sensor`, `_main_{washer,dryer,dishwasher,oven}OperatingState_completionTime_completionTime`: timestamp | not exposed | No reset while idle. [sensor.py#L1135-L1183](https://github.com/home-assistant/core/blob/d70e445d63f8793cefe9f3bf97c6986bedc23300/homeassistant/components/smartthings/sensor.py#L1135-L1183) |
| WashData (`3dg1luk43/ha_washdata` @ `5d6fda8b`) | `sensor`, `_cycle_progress` | `sensor`, `_time_remaining` (min) | **attributes `projected_energy_kwh`, `projected_cost` on `_cycle_progress`** | Its own projection from the learned power curve. [sensor.py#L454-L578](https://github.com/3dg1luk43/ha_washdata/blob/5d6fda8b38d0a2641916ea58d84104fab14b0c14/custom_components/ha_washdata/sensor.py#L454-L578) |
| Home Connect Local (`chris-mc1/homeconnect_local_hass` @ `baa64d14`) | `sensor`, `-sensor_program_progress` | `sensor`, `-sensor_remaining_program_time` (s) | `sensor`, `-sensor_energy_forecast`, `-sensor_water_forecast`: **%** | Only if the appliance's description lists the key. [common.py#L286-L321](https://github.com/chris-mc1/homeconnect_local_hass/blob/baa64d14a53c5e4777512117790b81d272361858/custom_components/homeconnect_ws/entity_descriptions/common.py#L286-L321) |
| Home Connect Alt (`ekutner/home-connect-hass` @ `d62771e6`) | `sensor`, `_bsh_common_option_programprogress` | `sensor`, `_bsh_common_option_remainingprogramtime`: timestamp | `_bsh_common_option_energyforecast`: %, only if the cloud lists it among the program's options | Totals and elapsed time are `h:mm` strings. [sensor.py#L43-L236](https://github.com/ekutner/home-connect-hass/blob/d62771e6b6e4c7ca7713da09dac9e7bd0486b805/custom_components/home_connect_alt/sensor.py#L43-L236) |

## EV chargers

| Integration | What a projection can use | Source |
|---|---|---|
| evcc (`marq24/ha-evcc` @ `17c5e5af`) | `sensor`, `_charge_remaining_energy` (kWh), `_charge_remaining_duration` (s), `_vehicle_soc`, `_effective_limit_soc` (%), `_charge_power` (kW). Only meaningful while evcc knows the vehicle's SoC. | [const.py#L1836-L1897](https://github.com/marq24/ha-evcc/blob/17c5e5affa1a80c6941dc309c351d2564e918f4d/custom_components/evcc_intg/const.py#L1836-L1897) |
| go-e MQTT (`syssi/homeassistant-goecharger-mqtt` @ `06653caa`) | `number`, `-number-dwo-0`: the session energy limit (Wh), null while off. The remainder is the limit minus the energy so far. | [number.py#L105-L115](https://github.com/syssi/homeassistant-goecharger-mqtt/blob/06653caa12f3b42a902beaae1a2e75a2c4429c3b/custom_components/goecharger_mqtt/definitions/number.py#L105-L115) |
| go-e API v2 (`marq24/ha-goecharger-api2` @ `acbf536f`) | `number`, `_dwo`: the session energy limit (Wh), null while off | [const.py#L327-L339](https://github.com/marq24/ha-goecharger-api2/blob/acbf536fd114ee409c88001dbd583838cba93d75/custom_components/goecharger_api2/const.py#L327-L339) |
| Tesla Wall Connector, Wallbox (core), Easee, Zaptec, OCPP | Power only. Wallbox and OCPP give SoC only on some DC chargers and never a target. Remaining time: not exposed. | |

## Conclusions for Coin-op

1. **Remaining time is the core input.** It must accept a duration in any time unit or a finish timestamp. The last known value is held while it drops out during a pause.
2. **Material still to come:** planned minus measured where a planned total exists. Otherwise measured ÷ progress. Without either, no material is projected, the same as no material is measured today.
3. **Drying** applies only to the Anycubic integrations and Bambu's AMS. Its extra power lasts for whichever is shorter, the drying left or the Run left.
4. **Appliances:** the rest of a Program's default, scaled by progress. The relative forecasts are not usable as amounts. WashData's projection can be read directly.
5. **EV chargers:** evcc's remaining energy, and go-e's limit while it is set. The other chargers get no projection.
