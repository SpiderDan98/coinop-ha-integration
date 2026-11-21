# Adding a Device

## Quick Start

Add Device always starts with **Quick Start**. It lists the devices of the integrations Coin-op has an Integration Profile for (see [Supported integrations](supported-integrations.md)), and picking one sets the Device up in two forms.

1. Pick the device. Its Device Type, its name and every Device Input the profile finds are taken over without further questions. Where the integration doesn't say what kind of device it is, Coin-op asks you for the Device Type instead of guessing, among those the integration is named for in the [Device Types](../README.md#device-types) table.
2. Check the Device Type the Device will be added as and the list of entities Coin-op found, then fill in what no profile knows:
   - the **energy meter or power sensor**, such as a metering plug's (its unit tells Coin-op which of the two it is). A washing machine, dishwasher, tumble dryer, coffee machine or oven may leave it empty and takes its kWh per Program from the Program Defaults; a printer without one is set up manually, where electricity can be estimated. A Miele washing machine, washer-dryer, dishwasher or tumble dryer and an EV charger with an energy counter bring their own meter and aren't asked, and neither is a SmartThings appliance that reports its energy.
   - the **electricity price**, fixed per kWh or from a price entity, pre-filled from the Device you added last.
   - for a Device Type with water (washing machine, dishwasher, coffee machine), optionally the **water price** per m³. With it, water comes from the Device's own meter or per Program from the Program Defaults; without it, no water is recorded.

The Device Type can't be changed once the Device is added. If the second form names the wrong one, choose **Pick another device** in it and then **Set up manually**, where you choose the Device Type yourself; the steps still come pre-filled.

How each integration tells which Device Type a device becomes is under [Which Device Type a device becomes](supported-integrations.md#which-device-type-a-device-becomes).

Everything Quick Start filled in can be checked and changed afterwards in the Device's reconfigure menu; the Doses and Program Defaults of a Device that has them are set on its card in the panel's Devices tab.

Choose **Set up manually** to walk every step yourself, for a device of any other integration or to map different entities. Devices Coin-op already follows aren't offered again. When Quick Start has nothing to offer, it says why: either it found no device of an integration it has an Integration Profile for, and names those integrations, or every device it found is already a Device or has its Status used by one. [Why isn't my device offered?](supported-integrations.md#why-isnt-my-device-offered) lists every reason a device is left out.

### Going back

Add Device lets you go back instead of closing the dialog and starting over. Nothing you entered before going back is kept.

- **Pick another device**, in Quick Start's Device Type step and its meter and prices step, shows the list of devices again. The meter and the prices may stay empty for it.
- **Back to Quick Start**, among the Device Types of manual setup, shows Quick Start again.
- **Change Device Type**, on the Home Assistant device step and on an Other Device's Type Name and what it has, returns to the Device Type choice. Reconfigure doesn't offer it: the Device Type is fixed once the Device is added.
