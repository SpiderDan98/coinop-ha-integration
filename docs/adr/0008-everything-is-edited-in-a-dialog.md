# Everything is edited in a dialog

The panel's pages show what is stored read-only. Whatever the user creates or changes (a Run's fields, a Line Item, a Material, a Tag, a Line Item Template, a Device's settings) is edited in a modal dialog: a draft with Cancel and one saving button. Nothing reaches the backend before that button, and a refused save keeps the dialog open with the draft. What can't be undone (deleting a Run, a Line Item, an image, a Material, a Tag, a template) is confirmed in a dialog too.

## Why

- The panel had four ways to edit: fields that saved on every change (Run page, Line Item Templates), a field swapped into a table row (Tags), a form card above the table (Materials) and a dialog (Devices). One way is easier to learn and to build on.
- Runs are recorded by Coin-op and mostly read; corrections are the exception. A page of always-open fields made every scroll or mis-tap a possible price change, and showed a Run that can't be changed yet as disabled fields.
- Fields that depend on each other (a Material's form, type and Cost Source; a Device's Doses and Program Defaults; a Line Item's quantity, unit price and amount) need a draft anyway: saving each change on its own can't pass through a state that is not valid yet.
- Tables of fields don't fit a phone. Read-only rows do, and a dialog is nearly full-width there.
- With every field in a dialog, one layout rule covers them all: a field is as wide as its dialog, and fields on one line share the width evenly.

## Consequences

- A correction costs one more click than a field that is always open. A Line Item's dialog shows the amount or the unit price following the one typed last, since the Run page no longer re-renders after each field.
- Every `<input>`, `<select>` and `<textarea>` that edits stored data comes from `frontend/src/fields.ts`, inside `formDialog()` of `frontend/src/dialog.ts`. ESLint refuses a raw control in any other module but the view controls listed in `frontend/eslint.config.js`.
- View controls stay on the pages, since they change what is shown, not what is stored: filters, sorting, the pager, the selection of Runs and the image upload button. So do actions of one click: a Material's default star, archive and restore, a Flag marked checked, a Line Item reset to its computed values, End Run now.
- `frontend/test/editing.test.ts` holds the rule: no page renders a control that edits, every dialog's controls sit in a field, and cancelling a dialog sends nothing. It can't measure widths (happy-dom lays nothing out); the width comes from the shared field styles.
- Fields have one size, `ha-input`'s 56px; the compact size for fields in tables is gone.
