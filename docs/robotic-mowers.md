# Robotic mowers

Choose **Robotic mower** as the Device Type when you add a Device. A Run is one mowing trip together with the recharge it causes. The mower runs on its battery, so its electricity is what the charging station draws: put a metering plug in front of the charging station and pick its energy meter (or its power sensor) as the electricity source. The setup asks for the Status, its mapping, the electricity source and the electricity price, and nothing else. No integration is pre-filled, so pick the entities yourself.

Map the mower's Status like this:

| The mower is | Status mapping |
|---|---|
| mowing, returning to the charging station | Running |
| charging | Paused |
| parked (in the station, charged) | Ended |

- The Run stays open while the mower charges, so the electricity the charging station draws after mowing lands in the Run that caused it. Pauses don't count as running time, so the Run's running time is the mowing time without the charging.
- While the mower charges, its open Run is paused: its running time stands still and its electricity keeps counting.
- A mower that leaves again right after charging continues the same Run, so a day of mowing in several trips can be one Run. The Run ends once the mower is parked.
- Map a stop by hand to Paused and an error to Fault, as for a printer. Ended gives the Run the Outcome Unknown; map parked to Finished instead if you want these Runs to end as Completed.

This needs a Status that tells charging from parked. Many integrations report one value for both, such as `docked`: the Run would then end the moment the mower docks, without the electricity of its recharge. Give Coin-op a Status of your own in that case, in one of two ways:

- A **template helper** that combines the mower's state with what tells you it is charging, such as its battery level or a charging sensor: `charging` while it is docked and not full, `parked` once it is.
- **Following the charging station's plug**: the station draws clearly more power while it charges than while the mower is parked. The template sensor below reports `charging` while the mower is docked and the plug draws more than 5 W (set the threshold above your station's standby power). The first five minutes after docking count as charging too, so the Run doesn't end before the plug has reported the higher power:

```yaml
template:
  - sensor:
      - name: Mower status
        state: >
          {% if is_state('lawn_mower.my_mower', 'docked') %}
            {% set just_docked = now() - states.lawn_mower.my_mower.last_changed < timedelta(minutes=5) %}
            {{ 'charging' if just_docked or states('sensor.mower_station_power') | float(0) > 5 else 'parked' }}
          {% else %}
            {{ states('lawn_mower.my_mower') }}
          {% endif %}
```

Pick that sensor as the Device's Status. Line Item Templates per running hour, such as blade wear, then count the mowing time only, and Tags for new Runs work as for every Device. A robotic mower's sensors are those of a printer without Material used, and its Run event's `ended` carries neither Program, litres nor Part Count.
