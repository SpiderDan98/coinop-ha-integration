# The panel uses only the HA elements HA always loads

The panel builds buttons and icon buttons from Home Assistant's own `ha-button`, `ha-icon-button` and `ha-svg-icon` (icons from `@mdi/js`, pinned to the frontend's version), used the way HA's own pages use them. Everything else (fields, selects, checkboxes, dialogs, tables, charts) stays native HTML styled with HA's theme variables.

## Why

- `ha-*` elements are not a documented API for custom panels; the only contract is the `hass`, `narrow`, `route` and `panel` properties.
- HA registers most `ha-*` elements only when one of its own pages needs them. Before a custom panel renders, HA has always loaded just its app shell and sidebar, which bring `ha-button`, `ha-icon-button`, `ha-svg-icon`, `ha-tooltip` and `ha-spinner` (checked for frontend 20260429.3, HA 2026.5, and 20261028.4, HA 2026.11). Opening `/coinop` directly must work.
- `ha-input`, `ha-select`, `ha-dialog` and the like can be loaded only through HA's private router (loading the config panel's automation route); a frontend release can break that without notice.
- The elements change between releases: `ha-textfield` is gone, `ha-button`'s `size="small"` became `size="s"` in 2026.11, and `ha-data-table` was largely rewritten in that half year.

## Consequences

- Only attributes and CSS variables that both the minimum and the current frontend understand are used. Small buttons set `--ha-button-height` instead of `size`.
- An icon button's name is its `.label` property (HA uses it as `aria-label` and tooltip), not a `title` attribute.
- In happy-dom the elements don't exist; `frontend/test/ha-elements.ts` stands in for them with just the behaviour the panel relies on.
- Using a lazily loaded element means loading it through HA's private router and checking it on every HA release; that is a decision to revisit, not a quick change.
