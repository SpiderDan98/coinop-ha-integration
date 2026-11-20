# Electricity cost per Run with a time-varying price

Research for GitHub issue #6 ("How do you calculate the electricity cost of a Run when the price changes over time?").
PV/battery is out of scope for v1.
Sources checked on 2026-11-19. All code citations are permalinks to these commits:

- home-assistant/core `dev` @ [`3109142`](https://github.com/home-assistant/core/tree/310914243c1bdbd6149f8466ca2c8eb0cdb36d50) (latest release: 2026.11.2)
- bramstroker/homeassistant-powercalc `master` @ [`3111313`](https://github.com/bramstroker/homeassistant-powercalc/tree/3111313a5e5f8721ae1281f4b9488e62820eee98) (latest release: v1.27.0)
- martinarva/dynamic_energy_cost `main` @ [`53e2890`](https://github.com/martinarva/dynamic_energy_cost/tree/53e28904002960fe2f73c70b33dc58ac3cfed292)
- zeronounours/HA-custom-component-energy-meter `main` @ [`adb57b1`](https://github.com/zeronounours/HA-custom-component-energy-meter/tree/adb57b1a665c22d7c1540da00d1ceb7904fcd31e)

Statements marked **[Inference]** are my own reading of the code. No source states them outright.

---

## Summary

- **The HA Energy dashboard only computes cost when the *energy meter* updates.** On each state change of the kWh sensor it does `cost += ΔE × price`, using whatever value the price entity has at that moment. Nothing is time-weighted, and a price change does not settle anything. So if energy builds up across a price change, all of it is charged at the *new* price. This error grows the less often the meter reports.
- **Units in core.** Core reads only the denominator of the price unit (`/Wh`, `/kWh`, `/MWh`, …) and converts it. It ignores the currency part, and cost is always in `hass.config.currency`. A price in `ct/kWh` is therefore treated as `EUR/kWh` without any warning, which makes the cost 100× too high **[Inference]**.
- **Missing or bad price in core.** When the price is non-numeric or `unavailable`, settlement pauses and the energy baseline stays where it is. The energy used in the meantime is later charged at the first valid price. Individual devices in the Energy dashboard get no cost at all.
- **PowerCalc (v1.27) has had cost sensors since July 2026.** They work for its own virtual energy sensors and for any external kWh sensor. Unlike core, PowerCalc **settles the energy used so far at the old price when the price changes**, and only then switches to the new price. It also converts the price denominator and supports a `surcharge` and a `multiplier` (e.g. VAT).
- **PowerCalc still settles against the *last reported* meter reading.** If the energy sensor reports rarely, energy used between that report and the price change still lands on the new price. PowerCalc's own energy sensors report only every 10 minutes when power is constant.
- **Without a measuring plug, PowerCalc builds a virtual power sensor** from a strategy (fixed W, standby, linear, LUT, playbook). It turns that into kWh with HA's Riemann-sum integration. The code default is the `left` method plus a time-based update every 600 s. The Riemann helper itself only integrates on state updates (and optionally on a `max_sub_interval` timer). After a restart it continues from the restored value but does not integrate the downtime.
- **Other projects.** `utility_meter` has no prices, only tariff buckets switched via a `select` entity. On a tariff switch, the *next* reading puts the whole ΔE into the new tariff, which is the same attribution error. The HACS integration *dynamic_energy_cost* settles on price changes like PowerCalc. On its power path it integrates `price × power` as a currency-per-hour rate with the left rule. *energy_meter* just subclasses the core cost sensor.
- **Applied to one Run.** With a piecewise-constant price, the exact cost is `Σ_segments price_i × E(segment_i ∩ Run)`. The core problem is splitting consumption cleanly at price boundaries and at the Run's start and end. Nearly all the effort and inaccuracy comes from how well E(t) is known at arbitrary times (meter lag, power sampling, estimation).
- **Recorder statistics (5-min / hourly) are a poor primary source.** Run boundaries rarely fall on 5-minute marks, and data is only ready after the next compile at `:x5:10`. Sources need a `state_class`, and estimated consumption has no statistics. One upside: 15- and 60-minute tariff changes line up with the 5-minute buckets. They are fine as a plausibility check or a fallback.
- **Recommendation: build a pure, testable function "price timeline × consumption timeline → cost".**
  - Feed it live from events: price `state_changed` and energy/power updates.
  - Persist **absolute** meter readings or partial energies with timestamps per price segment (`Store`/restore), not a running total. That keeps the calculation idempotent across restarts.
  - Split consumption at price boundaries by linear interpolation in time. With a power sensor or an estimate, the left rule does this more precisely.
  - Optionally recompute the Run from the recorder *state* history after it ends, to fill gaps such as HA downtime.
  - Use statistics only as a fallback.

---

## 1. How does the HA Energy dashboard compute cost from an "entity with current price"?

### 1.1 How `EnergyCostSensor` works

Source: [`homeassistant/components/energy/sensor.py`](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py)

- **When a cost sensor is created.** Only for `grid` (import and export/compensation), `gas` and `water` sources. It also needs `entity_energy_price` or `number_energy_price` to be set and no cost statistic (`stat_cost`) to be configured ([L216-L250](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L216-L250)). Its docstring calls it *"a fallback for when no specific cost sensor is available"* ([L417-L421](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L417-L421)).
- **No per-device cost.** `DeviceConsumption` only has `stat_consumption`, `stat_rate`, `name` and `included_in_stat`. There are no price fields ([`energy/data.py` L280-L294](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/data.py#L280-L294)).
- **Trigger.** The sensor subscribes only to the energy sensor, via `async_track_state_change_event` on `stat_energy_key` ([L702-L708](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L702-L708)). **A price change does not trigger settlement.**
- **Formula.** `native_value = cur_value + (energy - last_energy) * converted_energy_price`, followed by `_last_energy_sensor_state = energy_state` ([L628-L635](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L628-L635)). `_get_energy_price()` reads the price from `hass.states` at the moment of the energy update ([L637-L666](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L637-L666)).
- **No time weighting.** The whole ΔE since the previous energy update is charged at the price in effect *at update time* **[Inference from the formula]**. The less often the meter reports, the bigger the error with dynamic tariffs. For example, a meter reporting every few seconds is barely affected, one reporting hourly or daily is affected a lot.
- **The sensor itself.** `device_class=monetary`, `state_class=total`, unit `hass.config.currency` ([L456-L458](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L456-L458), [L770-L774](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L770-L774)). The dashboard shows this sensor's long-term statistics ([long-term statistics docs](https://github.com/home-assistant/home-assistant.io/blob/current/source/_docs/configuration/long-term-statistics.markdown), "The Energy dashboard uses the long-term statistics…").

### 1.2 Units

- **Price unit.** Core takes only the denominator, via `unit_of_measurement.partition("/")[2]`. If the denominator is not a valid unit, it assumes kWh *"for backwards compatibility"* ([L655-L666](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L655-L666)). `EnergyConverter` then converts the price to the meter's unit ([L668-L685](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L668-L685)). So `EUR/MWh`, `EUR/Wh` and `EUR/kWh` all work.
- **Currency and `ct/kWh`.** Everything before the `/` is discarded. Validation only checks `unit.endswith("/kWh" | "/Wh" | …)` ([`energy/validate.py` L36-L38, L305-L327](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/validate.py#L305-L327)). A price of `30 ct/kWh` would therefore be booked as 30 [HA currency]/kWh with no warning **[Inference; I found no test or issue confirming this]**.
- **Energy unit.** It must be in `UnitOfEnergy`. Otherwise the sensor logs a warning and settles nothing ([L555-L569](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L555-L569)). Since PR [#187475](https://github.com/home-assistant/core/pull/187475), a change of the meter's unit is converted ([L588-L600](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L588-L600)).

### 1.3 Missing or invalid price or meter

- **Price entity missing:** raises `EntityNotFoundError`, and the sensor returns without changing anything.
- **Price non-numeric** (`unavailable`, `unknown`): `ValueError` is caught, `energy_price = None`, and the sensor returns. `_last_energy_sensor_state` does not advance, so the accumulated ΔE is charged at whatever price is valid at the next energy update ([L536-L553](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L536-L553)). No energy is lost, but it may be priced wrongly **[Inference]**.
- **Meter non-numeric:** the sensor returns ([L531-L534](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L531-L534)).
- **State class:** must be `measurement` (only together with `last_reset`), `total` or `total_increasing` ([L511-L529](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L511-L529)).

### 1.4 Energy sensor resets

- **`total_increasing`:** `reset_detected()` in `sensor/recorder.py` reports a reset when `fstate < 0.9 × previous`. A drop of less than 10% only logs a "dip" warning. A negative value raises an error and the update is skipped ([`sensor/recorder.py` L524-L542](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/sensor/recorder.py#L524-L542)). The developer docs say the same: *"a decrease between state changes of < 10% will not trigger a new meter cycle"* ([developers: sensor.md](https://github.com/home-assistant/developers.home-assistant/blob/master/docs/core/entity/sensor.md#state-class-sensorstateclasstotal_increasing)).
- **`total` / `measurement`:** a reset is detected when `last_reset` changes ([L614-L619](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L614-L619)).
- **On a reset:** the cost sensor resets to 0 with a new `last_reset`, and the new meter value counts in full as consumption (`last_energy = 0.0`, [L621-L626](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L621-L626)).

### 1.5 HA restarts

- Since PR [#187451](https://github.com/home-assistant/core/pull/187451) (merged 2026-10-20, shipped in 2026.11.0), the sensor stores its last priced meter reading at *shutdown*. On the next start it charges the energy used during the downtime in a new cycle. Before that PR: *"Energy used while Home Assistant was stopped never got a cost"* (PR description).
- That reading is stored **only on stop**, not in the periodic restore saves every 15 minutes. The code comment explains why: after a crash, an older snapshot would charge some energy *twice* ([L742-L757](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L742-L757)). So after a crash, the downtime energy is still lost. Energy used during the downtime is also charged at the price in effect *after* startup **[Inference]**.

### 1.6 Known inaccuracies (issues)

- [#154699](https://github.com/home-assistant/core/issues/154699) "Energy Dashboard calculating wrong price / Price jumps" (Tibber). A maintainer traced how the cost sensor went `unknown` and then `0` after a pause in updates, and then *"counts entire value of consumption as new consumption"*. The issue was closed as stale without a fix (2026-08-26).
- [#95922](https://github.com/home-assistant/core/issues/95922): with a price entity, the cost sensor was `unknown` after boot, and the first consumption after startup was missed.
- [#135664](https://github.com/home-assistant/core/issues/135664) and [#121840](https://github.com/home-assistant/core/issues/121840): cost differs from `kWh × price`, or is only partly computed. Both were closed as stale without a root cause.
- **Structural issues [Inference]:**
  - ΔE that spans a price change is charged at the later price.
  - A price in a sub-unit (ct) is not scaled.
  - Downtime after a crash is never priced.

---

## 2. How do existing projects compute per-device cost?

### 2.1 PowerCalc

**Virtual power without measurement** ([strategies docs](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/strategies/index.md)):
- `fixed`: one W value while `on`. Optional per-state `states_power` and templates ([fixed.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/strategies/fixed.md)).
- `standby_power`: used when the source entity is `off`, `not_home`, `standby` or `unavailable`. `sleep_power` adds a second level after `delay` seconds ([standby-power.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/configuration/standby-power.md)).
- `linear`: interpolates between `min_power` and `max_power` from brightness, percentage or volume. Optional `gamma_curve` or `power_curve` ([linear.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/strategies/linear.md)).
- `lut`: CSV lookup tables for lights, described as *"the most accurate mode"* ([lut.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/strategies/lut.md)).
- `playbook`: replays recorded power curves, e.g. washing-machine programmes ([playbook.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/strategies/playbook.md)). The concept could be useful for job-shaped devices such as 3D printers.
- `daily_fixed_energy`: kWh per day, or W × `on_time`, added in steps (default every 1800 s) ([daily-energy.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/sensor-types/daily-energy.md)).

**Energy from power:**
- `VirtualEnergySensor` subclasses core's `IntegrationSensor` ([sensors/energy.py L7, L296](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/energy.py#L296)).
- Code defaults: integration method `left` (`DEFAULT_ENERGY_INTEGRATION_METHOD = ENERGY_INTEGRATION_METHOD_LEFT`) and `energy_update_interval = 600` s ([const.py L240-L241](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/const.py#L240-L241)).
- **Note:** the docs give the default method as `trapezoid` ([global-configuration.md L57](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/configuration/global-configuration.md)). Code and docs disagree, and I treat the code as authoritative.
- Energy sensors update on every power change and additionally every 10 minutes ([update-frequency.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/configuration/update-frequency.md)).

**Cost sensor** (new since 2026-07-04, PR [#4260](https://github.com/bramstroker/homeassistant-powercalc/pull/4260)). Docs: [cost-sensor.md](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/docs/source/sensor-types/cost-sensor.md). Code: [sensors/cost.py](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py).
- **Price source:** `energy_price` (fixed) or `energy_price_sensor`, set globally or per sensor. The effective price is `(price + surcharge) × multiplier`.
- **Scope:** works for PowerCalc's own energy sensors and *standalone* for any external kWh sensor (`cost: energy_sensor_id:`). PowerCalc also creates a cost sensor per utility-meter cycle.
- **Settling at a price change:** `_handle_price_state_change` reads the energy sensor's *current* state and charges the ΔE since the last settlement at `_current_price`, which is still the old price. Only then does it adopt the new price ([cost.py L349-L360](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py#L349-L360)). The docs say: *"a price change settles the energy consumed up to that point at the previous price"*.
- **Remaining gap [Inference]:** "up to that point" means up to the last *reported* meter reading. Energy used between that report and the price change is charged at the new price at the next energy update. With PowerCalc's own energy sensors at constant power, that can be up to 10 minutes of consumption.
- **Missing price:** `effective_price(None)` returns `None`, and `_accumulate` then leaves `_last_energy` untouched. The consumption is charged at the next valid price ([L362-L367](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py#L362-L367)). This is the same behaviour as core.
- **Resets:** a drop of less than 10% is ignored and the baseline is kept (fixed on 2026-11-18). A larger drop sets `delta = new_energy`. Utility-meter cost sensors start a new cycle instead ([L369-L388](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py#L369-L388)).
- **Units:** energy is converted to kWh, and the price denominator is converted to per-kWh. **The currency is taken from the prefix of the price unit**, so `€/kWh` becomes `€`. Without a prefix, the HA currency is used ([L60-L105](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py#L60-L105), [L289-L297](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py#L289-L297)). A `ct/kWh` price would therefore give a cost sensor in "ct". That is not an ISO 4217 code, which `monetary` expects ([developers: sensor.md](https://github.com/home-assistant/developers.home-assistant/blob/master/docs/core/entity/sensor.md)) **[Inference]**.
- **Restart:** PowerCalc restores the state and the `last_energy` attribute via `RestoreEntity` ([L276-L279](https://github.com/bramstroker/homeassistant-powercalc/blob/3111313a5e5f8721ae1281f4b9488e62820eee98/custom_components/powercalc/sensors/cost.py#L276-L279)).
  - Energy a hardware meter recorded during the downtime is charged at the first update, at the price valid then **[Inference]**.
  - It has no explicit crash guard like core's. The restored state can be up to 15 minutes old, but `last_energy` and the cost value are restored from the same snapshot, so each ΔE is still counted once **[Inference]**.

### 2.2 Integration (Riemann sum) helper

Source: [`integration/sensor.py`](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/integration/sensor.py). Docs: [integration.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/integration.markdown).

- **Methods:** `trapezoidal` (default), `left` and `right` ([L137-L177](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/integration/sensor.py#L137-L177)). The docs call `left` *"extremely accurate"* for rectangular signals such as a resistive load. It matches HA's state model, in which a state holds until the next one.
- **When it integrates:** on `state_changed` **and** on `state_reported` (the same value reported again). Optionally also on a timer, via `max_sub_interval` ([L498-L525](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/integration/sensor.py#L498-L525)).
- **Bad source values:** `unavailable` makes the sensor unavailable, and a non-numeric value adds no area ([L605-L643](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/integration/sensor.py#L605-L643)).
- **Restart:** only `native_value` and `last_valid_state` are restored ([L481-L496](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/integration/sensor.py#L481-L496)). Per the docs it *"continues integrating … as soon as the source sensor starts providing new readings"*. The downtime itself is **not** integrated **[Inference]**, and the power during the downtime is unknown anyway.
- **No price awareness.**

### 2.3 utility_meter

Source: [`utility_meter/sensor.py`](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/utility_meter/sensor.py). Docs: [utility_meter.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/utility_meter.markdown).

- **No prices**, only cycles and tariffs. The tariff is switched through a `select` entity, usually from an automation.
- **On a tariff switch:** the old tariff sensor stops collecting and `_last_valid_state` is set to `None`. The next source update yields ΔE `old_state → new_state`, and all of it goes to the *new* tariff ([L412-L442](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/utility_meter/sensor.py#L412-L442), [L500-L524](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/utility_meter/sensor.py#L500-L524)). This is the same attribution error as the energy cost sensor **[Inference]**.
- `periodically_resetting`, `delta_values` and `net_consumption` control how decreases are handled.

### 2.4 HACS "energy cost" integrations

**dynamic_energy_cost** (206 stars, active). [README](https://github.com/martinarva/dynamic_energy_cost/blob/53e28904002960fe2f73c70b33dc58ac3cfed292/README.md), [sensor.py](https://github.com/martinarva/dynamic_energy_cost/blob/53e28904002960fe2f73c70b33dc58ac3cfed292/custom_components/dynamic_energy_cost/sensor.py).
- **Energy path:** each energy update adds `Δ × current price`. Each price update charges the ΔE up to the *current meter reading* at the **old** price (`event.old_state`) ([L570-L616](https://github.com/martinarva/dynamic_energy_cost/blob/53e28904002960fe2f73c70b33dc58ac3cfed292/custom_components/dynamic_energy_cost/sensor.py#L570-L616)). This is the same logic as PowerCalc, with the same meter-lag gap.
- **Power path:** `RealTimeCostSensor` computes price × power in currency per hour ([L379-L421](https://github.com/martinarva/dynamic_energy_cost/blob/53e28904002960fe2f73c70b33dc58ac3cfed292/custom_components/dynamic_energy_cost/sensor.py#L379-L421)). `PowerCostSensor` integrates that rate with the **left rule** (`previous_cost × hours_passed`) ([L770-L827](https://github.com/martinarva/dynamic_energy_cost/blob/53e28904002960fe2f73c70b33dc58ac3cfed292/custom_components/dynamic_energy_cost/sensor.py#L770-L827)). The rate is recomputed on price changes too, so this is exact when both price and power are step functions. The README still calls the power path *"an approximation"* and recommends using energy sensors.
- **Units:** price denominators Wh, kWh and MWh are supported. The currency always comes from the HA config, so `ct` is not scaled, as in core ([L162-L176](https://github.com/martinarva/dynamic_energy_cost/blob/53e28904002960fe2f73c70b33dc58ac3cfed292/custom_components/dynamic_energy_cost/sensor.py#L162-L176)) **[Inference]**.

**energy_meter** (zeronounours, 29 stars). An extension of `utility_meter` with `price`/`price_entity` per tariff ([README](https://github.com/zeronounours/HA-custom-component-energy-meter/blob/adb57b1a665c22d7c1540da00d1ceb7904fcd31e/README.md)). Its cost sensor **subclasses core's internal** `homeassistant.components.energy.sensor.EnergyCostSensor` ([sensor.py L8-L9, L69](https://github.com/zeronounours/HA-custom-component-energy-meter/blob/adb57b1a665c22d7c1540da00d1ceb7904fcd31e/custom_components/energy_meter/sensor.py#L69)). It inherits core's behaviour, and the coupling to internal core APIs makes it fragile when core changes.

### 2.5 Overview by input

| Input | Typical solution | Cost logic |
|---|---|---|
| Energy (kWh, `total_increasing`) | Core energy cost sensor, PowerCalc standalone cost sensor, dynamic_energy_cost | ΔE × price on every energy update. PowerCalc and dynamic_energy_cost also settle on price changes, up to the last reported reading. |
| Power (W) | Riemann helper or PowerCalc energy sensor, then as above. Or dynamic_energy_cost: rate = P × price, left rule. | Accuracy depends on sample density and `max_sub_interval`. |
| No measurement | PowerCalc strategy produces a virtual W curve, then Riemann, then cost. | Same as power, but the W curve is modelled. |

---

## 3. What transfers to a single Run with a start and an end?

### 3.1 Basic model

The price is piecewise constant: segments of 15 or 60 minutes, and a fixed price is a single segment. So the exact cost is:

`cost(Run) = Σ_i p_i × E([max(t_start, s_i), min(t_end, e_i)])`

The problem reduces to knowing consumption at arbitrary times: Run start, Run end and every price boundary. Every implementation above makes its error exactly there, because it only settles when a sensor happens to report **[Inference from 1.1, 2.1, 2.3, 2.4]**.

How well each input lets you determine E(t) at a boundary:
- **Energy meter:** you get readings at times t_k. For a boundary between two readings you can interpolate linearly, or use the power in that interval if a power sensor exists. The error is at most one reporting interval's ΔE times the price difference.
- **Power sensor:** HA states behave as steps (each value holds until the next one). The left rule with a split exactly at the boundary is consistent with HA. Remaining errors come from sample density, the gap until the first sample after start, and `unavailable` periods.
- **Estimated** (nominal wattage, standby): Coin-op knows the power curve itself. It is a step function, e.g. driven by device state, so integrating it over the segments is **analytically exact** relative to the model. All the uncertainty sits in the model, not in the accounting.

### 3.2 Options compared

**A. Compute live (event-driven) and settle at price boundaries.** This is the PowerCalc / dynamic_energy_cost pattern, extended with interpolation.
- **Accuracy:** very good with splitting at boundaries. Without interpolation, the meter-lag gap from 2.1 remains.
- **Restarts:** Coin-op must persist the Run state. Core's lesson applies here: restore state is saved every 15 minutes and on stop, so after a crash the snapshot is stale ([energy/sensor.py L742-L757](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/energy/sensor.py#L742-L757)). Persist **absolute data points** (time, meter reading, price) per segment rather than a **running total**. Then the computation is idempotent and never counts twice **[Inference]**.
- **Downtime:** with a hardware meter the energy is known, but not how it splits across price segments, short of assuming it was linear in time. With a power sensor or an estimate, the downtime consumption is unknown or can only be modelled.
- **Effort:** medium. Two listeners (price and consumption), a timer or the `state_reported` event for constant power (see the Riemann helper, 2.2), and persistence.

**B. Compute after the Run ends from the recorder *state* history.**
- **Accuracy:** as good as A. Price states give the exact switch times, and energy or power states give the data points. The computation is deterministic and easy to test.
- **Restarts:** robust against restarts of Coin-op itself. HA downtime is missing from the history just as in A. B is well suited to filling gaps after a restart.
- **Limitations:**
  - The recorder must be enabled and neither entity excluded ([long-term-statistics.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_docs/configuration/long-term-statistics.markdown): *"If you exclude an entity from the recorder…"*).
  - States are purged after `purge_keep_days`, default 10 days ([recorder.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/recorder.markdown)). That is enough for Runs.
  - The recorder commits with a delay, so Coin-op has to wait for a flush before reading **[Inference]**.
  - Long Runs with dense power samples put load on the database **[Inference]**.
  - Estimated consumption has no history unless Coin-op exposes its own power entity.
- **Effort:** medium. A history query in the executor, plus the same calculation function as A.

**C. Short-term or long-term statistics (5 min / 1 h) after the Run ends.**
- **Availability:**
  - Short-term statistics are written every 5 minutes and kept as long as the state history. Long-term statistics are hourly and never purged ([long-term-statistics.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_docs/configuration/long-term-statistics.markdown)).
  - Compilation runs at `:x0:10` and `:x5:10` UTC ([recorder/core.py L710-L712](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/recorder/core.py#L710-L712)). Missed runs are caught up after a restart (`CompileMissingStatisticsTask`).
- **Content:**
  - For total sensors, `sum` comes from the *last state in the bucket* ([sensor/recorder.py L771-L870](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/sensor/recorder.py#L771-L870)).
  - For measurement sensors, `mean` is time-weighted, without interpolation ([L160-L195](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/sensor/recorder.py#L160-L195)).
  - Core Nordpool price sensors are `measurement`, so they have means ([nordpool/sensor.py](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/nordpool/sensor.py)). Other price integrations may not be **[Uncertainty]**.
- **Accuracy:**
  - Mid-Run: 15- and 60-minute price changes fall on 5-minute bucket boundaries, so `Σ ΔE_bucket × mean_price_bucket` is nearly exact. Only the meter lag inside each bucket remains.
  - At the **start and end**, resolution is 5 minutes. Without a correction from states, that can be up to ±5 minutes of consumption in error.
  - The `statistic_during_period` API also works only on 5-minute marks ([long-term-statistics.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_docs/configuration/long-term-statistics.markdown): *"any 5-minute mark"*; [recorder/statistics.py L1844](https://github.com/home-assistant/core/blob/310914243c1bdbd6149f8466ca2c8eb0cdb36d50/homeassistant/components/recorder/statistics.py#L1844)).
- **Restarts:** robust. A hardware meter's downtime energy lands in the first bucket after restart.
- **Limitations:**
  - Sources need a `state_class`.
  - Results are only available after the next compile.
  - Estimated consumption has no statistics.
  - Access goes through recorder internals. Core integrations such as `energy` use them, but they are not a stable, documented API for custom components **[Uncertainty]**.
- **Effort:** low to medium. Suitable as a fallback or plausibility check, not as the primary source.

**D. Energy-meter snapshots at every price change**, plus start and end, without interpolation.
- This is A in its simplest form, and it matches PowerCalc and dynamic_energy_cost one-to-one. With fast-reporting plugs (seconds) the error is negligible. With slow ones (minutes) it is systematic. It only works with an energy sensor.
- **Effort:** low.

### 3.3 Restarts during a Run: key points

- **Persist with timestamps.** Persist the Run boundaries and data points with timestamps, via `helpers.storage.Store` or `RestoreEntity` extra data. Store them so that an older snapshot after a crash cannot double-count, i.e. absolute meter readings instead of increments **[Inference, the lesson from core in 1.5]**.
- **Consumption during downtime:**
  - A hardware meter gives the ΔE, but not how it splits across price segments. The simplest defensible assumption is constant power, i.e. linear in time.
  - A power sensor cannot be integrated across downtime, and core's Riemann helper does not try (2.2).
  - For estimated consumption, it depends on whether the device state across the downtime is known **[Inference]**.
- **Prices during downtime** can sometimes be reconstructed. The recorder has no states for that period, but some price integrations offer queries for past prices, e.g. `nordpool.get_prices_for_date` ([nordpool.markdown](https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/nordpool.markdown)). There is no generic way to do this for "any price entity" **[Uncertainty]**.

### 3.4 Recommendation for Coin-op

1. **A pure core function** `cost(price_timeline, consumption_samples, t_start, t_end)`. It segments by the price timeline, splits consumption at the boundaries and sums the segments. Energy is interpolated linearly in time, power uses the left rule, and estimates are integrated analytically. It can be tested without HA.
2. **Feed it live (option A).** Listen for price `state_changed` and for consumption `state_changed`/`state_reported`, and add a timer for constant power. Persist data points, not totals. This also keeps the live cost of a running Run correct.
3. **Fill gaps afterwards from the recorder state history (option B)**, e.g. after a restart or when data points are missing. Use statistics (C) only as a last fallback.
4. **Units.** Convert the price denominator (Wh/kWh/MWh). **Detect and scale currency sub-units (ct)**, or at least make the scale explicitly configurable. Neither core nor PowerCalc handles this cleanly.
5. **Price outages.** Either "park" the consumption and price it later, as core does, or assume the last valid price for the gap and flag the Run so the outage stays visible. I prefer flagging; the choice is a planning decision.

### 3.5 Open uncertainties

- The `ct/kWh` behaviour in core and PowerCalc is derived from code and not tested.
- PowerCalc's default integration method: the code says `left`, the docs say `trapezoid`.
- I only checked core Nordpool for whether price integrations set `state_class: measurement` and therefore have statistics. Tibber, EPEX Spot and the HACS Nordpool integration are unchecked.
- I found no stability guarantee in the developer docs for the recorder history and statistics functions as an API for custom components.
