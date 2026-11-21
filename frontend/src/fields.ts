// The panel's data fields: every input, select and textarea a dialog edits with comes
// from here, wrapped by `field()`, so each takes its dialog's full width (the layout is in
// `src/styles.ts`). ESLint keeps raw controls out of every other module but the view
// controls (filters, pager, selection, upload).
import { html, nothing } from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { live } from "lit/directives/live.js";

const invalidity = (invalid?: boolean) => (invalid ? "true" : "false");

/** `onInput` follows the typing; `onChange` takes the value once the field is left. */
export const input = ({
  type,
  name,
  value = "",
  label,
  placeholder,
  min,
  max,
  step,
  maxlength,
  list,
  required = false,
  disabled = false,
  invalid,
  autofocus = false,
  onInput,
  onChange,
}: {
  type?: "number" | "datetime-local" | "color";
  name?: string;
  value?: string;
  /** The accessible name of a field without a `field()` label. */
  label?: string;
  placeholder?: string;
  min?: string;
  max?: string;
  step?: string;
  maxlength?: number;
  /** Values to suggest. */
  list?: string[];
  required?: boolean;
  disabled?: boolean;
  invalid?: boolean;
  autofocus?: boolean;
  onInput?: (value: string) => void;
  onChange?: (value: string, control: HTMLInputElement) => void;
}) => {
  const control = (event: Event) => event.target as HTMLInputElement;
  return html`<input
      type=${ifDefined(type)}
      name=${ifDefined(name)}
      aria-label=${ifDefined(label)}
      aria-invalid=${invalidity(invalid)}
      placeholder=${ifDefined(placeholder)}
      min=${ifDefined(min)}
      max=${ifDefined(max)}
      step=${ifDefined(step)}
      maxlength=${ifDefined(maxlength)}
      list=${ifDefined(list && `${name}-list`)}
      ?required=${required}
      ?disabled=${disabled}
      ?autofocus=${autofocus}
      .value=${
        // A half-typed number ("-") reads as "": a plain binding would write that back.
        live(value)
      }
      @input=${onInput && ((event: Event) => onInput(control(event).value))}
      @change=${onChange && ((event: Event) => onChange(control(event).value, control(event)))}
      @keydown=${
        // Enter commits such a field (the change event) instead of saving the dialog.
        onChange &&
        ((event: KeyboardEvent) => {
          if (event.key === "Enter") event.stopPropagation();
        })
      }
    />${
      list
        ? html`<datalist id="${name}-list">
            ${list.map((option) => html`<option value=${option}></option>`)}
          </datalist>`
        : nothing
    }`;
};

/** A decimal number, kept as typed. */
export const numberInput = (options: Omit<Parameters<typeof input>[0], "type">) =>
  input({ type: "number", step: "any", min: "0", ...options });

/** `options` are `[value, label]`, a third `true` for one that can't be picked. */
export const select = ({
  name,
  value,
  label,
  options,
  disabled = false,
  invalid,
  autofocus = false,
  onChange,
}: {
  name?: string;
  value?: string | null;
  label?: string;
  options: readonly (readonly [value: string, label: unknown, disabled?: boolean])[];
  disabled?: boolean;
  invalid?: boolean;
  autofocus?: boolean;
  onChange?: (value: string, control: HTMLSelectElement) => void;
}) =>
  html`<select
    name=${ifDefined(name)}
    aria-label=${ifDefined(label)}
    aria-invalid=${invalidity(invalid)}
    ?disabled=${disabled}
    ?autofocus=${autofocus}
    @change=${
      onChange &&
      ((event: Event) => {
        const control = event.target as HTMLSelectElement;
        onChange(control.value, control);
      })
    }
  >
    ${options.map(
      ([option, text, unpickable = false]) =>
        html`<option value=${option} ?disabled=${unpickable} .selected=${option === (value ?? "")}>
          ${text}
        </option>`,
    )}
  </select>`;

export const textarea = ({
  name,
  value = "",
  rows = 3,
  onInput,
}: {
  name?: string;
  value?: string;
  rows?: number;
  onInput?: (value: string) => void;
}) =>
  html`<textarea
    name=${ifDefined(name)}
    rows=${rows}
    .value=${value}
    @input=${onInput && ((event: Event) => onInput((event.target as HTMLTextAreaElement).value))}
  ></textarea>`;

export const checkbox = ({
  name,
  label,
  checked,
  indeterminate = false,
  disabled = false,
  onChange,
}: {
  name?: string;
  label: unknown;
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) =>
  html`<label class="check"
    ><input
      type="checkbox"
      name=${ifDefined(name)}
      .checked=${checked}
      .indeterminate=${indeterminate}
      ?disabled=${disabled}
      @change=${(event: Event) => onChange((event.target as HTMLInputElement).checked)}
    />${label}</label
  >`;

/** A field with its unit inside it, as HA's text field shows a suffix. */
export const withUnit = (control: unknown, unit: unknown) =>
  html`<span class="with-unit">${control}<span class="unit">${unit}</span></span>`;

/** A control under its label, with a hint below. `group` is for several controls, or one
 * that is no form control: its parts name themselves. */
export const field = (
  label: unknown,
  control: unknown,
  { hint, name = "", group = false }: { hint?: unknown; name?: string; group?: boolean } = {},
) =>
  html`<div class="field ${name}">
    ${
      group
        ? html`<span class="label">${label}</span>${control}`
        : html`<label><span class="label">${label}</span>${control}</label>`
    }
    ${hint ? html`<p class="hint">${hint}</p>` : nothing}
  </div>`;
