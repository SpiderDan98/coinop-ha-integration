# Electricity

## Estimating electricity without a meter

Without an energy meter or power sensor, CoinOp estimates electricity from the Device's average power while it runs. A desktop FDM printer with a heated bed typically averages 80–150 W over a whole print. Don't enter the rated power from the label or power supply: it is far higher than what the printer really draws on average. If you can, measure one print with a power-measuring plug and use that.

## Electricity source "None"

The electricity source menu of every Device ends with **None**, after the energy meter, the power sensor and, depending on the Device Type, the estimate from average power or "per Program". Pick it for a Device whose electricity you don't follow: one that only costs water, a Material or a flat amount per Run, or one you have no meter and no honest number for.

- **Runs**: new Runs get no Electricity Line Item and no Flag about electricity, and a Run doesn't wait for an electricity meter when it ends. Water, Doses, Material, Tags and automatic Line Item Templates work as for every Device, so a flat cost per Run is an automatic template. A manual Run gets no Electricity Line Item either.
- **Setup**: Add Device skips the electricity price, and the reconfigure menu offers the electricity source without the price. A Device with nothing else that is computed is a valid Device: its Runs cost nothing until Line Items are added by hand or by automatic templates.
- **Switching**: change the source to or from None in the reconfigure menu at any time. The change applies from the next Run; the open Run keeps the source it started with, and ended Runs never change. Picking a source again asks for the electricity price if the Device has none. A price you entered before is kept while the source is None and used again afterwards; the other settings of the old source (average powers, the meter and its conversion factor) are entered anew.
- **Program Defaults**: the kWh column and the measured kWh suggestions are hidden while the source is None. The kWh you entered are kept and shown again once the Device has a source. The litres and Dose columns stay as they are.
- **Electricity by hand**: on a Run without an Electricity Line Item, the Run page offers **Add electricity**, also while the Run is open. It adds one in kWh with the quantity and unit price you enter, marked as entered by hand. A Run takes one Electricity Line Item, so the button is gone once it has one; an entered one can be edited and deleted.
- **Panel, sensors and statements**: the Device's card shows "None" as its consumption source and no electricity price, and such a Run shows no Electricity card. The Device keeps its Electricity cost and Energy in Runs sensors, which count the electricity its Runs have, the Run event's `ended` reports an `energy_kwh` of 0, and a Cost Statement lists the Run without an electricity row.
- [Quick Start](adding-a-device.md#quick-start) never picks None: choose it in manual setup, or afterwards in the reconfigure menu.

None or an estimate? Estimate (or enter the kWh per Program) when electricity is a real part of what a Run costs and you know roughly how much, as for a printer without a meter. Pick None when it isn't a cost you want to see, as for a battery-driven or hand-operated Device or a negligible draw, or when any number would be made up. An average power of 0 W or a kWh default of 0 leaves a "0.00" Electricity Line Item on every Run; None leaves none.
