# Small energy meter dips count nothing; large drops are resets

When an energy meter's reading falls, CoinOp looks at how far. A reading below 90% of the previous one is a reset: the meter counts from 0 again, so the new reading is the energy since the reset (what came between the last reading and the reset is lost). A smaller drop is a dip: the stretch counts no energy, and the meter is taken to continue from the lower value. Both flag the Run `meter_reset`, so the user can check it.

## Why

- Home Assistant's `total_increasing` state class draws the same line (a drop below 90% is a new cycle), so Coin-op agrees with the Energy dashboard and long-term statistics about the same meter.
- Smart plugs and meters report small backward jumps from rounding, a resend of an older value or a correction after a reconnect. Counting such a dip as a reset from 0 would book nearly the whole meter reading as this Run's energy, by far the worse error.
- Counting nothing for a dip can only under-count by the size of the dip, which is small by definition; the Flag still asks the user to look.

## Consequences

- The Flag `meter_reset` covers both a real reset and a dip.
- A real reset that the next report already counts back up to 90% of the previous reading (a meter reset while its reading was small) is taken for a dip, and that stretch counts nothing.
