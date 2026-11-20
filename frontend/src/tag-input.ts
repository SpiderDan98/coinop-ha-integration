// Tags as chips plus a field to add one: suggests existing Tags while typing, and Enter
// adds what was typed, as the existing Tag when only the case differs. Fires
// `tags-change` with the new alphabetical list; the owner saves it.
import { mdiClose } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "./hass";
import { localize } from "./localize";
import { shared } from "./styles";

const MAX_LENGTH = 40;
const MAX_SUGGESTIONS = 8;

const same = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "base" }) === 0;

export const sortTags = (tags: string[]) =>
  tags.toSorted((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));

export const tagChip = (tag: string) =>
  html`<span class="tag-chip"><span class="tag-name">${tag}</span></span>`;

@customElement("wattbill-tag-input")
export class TagInput extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) tags: string[] = [];
  @property({ attribute: false }) catalog: string[] = [];
  @property({ attribute: false }) label = "";

  @state() private text = "";
  /** False once focus left the field, so the suggestions close. */
  @state() private open = true;
  /** The suggestion picked with the arrow keys; -1 for none. */
  @state() private active = -1;

  /** What Enter or a click can add: matching Tags, then the typed text as a new one. */
  private options() {
    const typed = this.text.trim();
    if (!typed) return [];
    const suggestions = this.catalog
      .filter(
        (tag) =>
          tag.toLocaleLowerCase().includes(typed.toLocaleLowerCase()) &&
          !this.tags.some((own) => same(own, tag)),
      )
      .slice(0, MAX_SUGGESTIONS)
      .map((tag) => ({ tag, create: false }));
    const known = [...this.catalog, ...this.tags].some((tag) => same(tag, typed));
    return known ? suggestions : [...suggestions, { tag: typed, create: true }];
  }

  override render() {
    const t = localize(this.hass);
    const options = this.open ? this.options() : [];
    return html`<div
      class="tag-input"
      @focusout=${(event: FocusEvent) => {
        if (!this.renderRoot.contains(event.relatedTarget as Node | null)) this.open = false;
      }}
    >
      <div class="row chips">
        ${this.tags.map(
          (tag) =>
            html`<span class="tag-chip"
              ><span class="tag-name">${tag}</span
              ><ha-icon-button
                class="remove"
                .label=${t("tags.remove", { tag })}
                .path=${mdiClose}
                @click=${() => this.change(this.tags.filter((own) => own !== tag))}
              ></ha-icon-button
            ></span>`,
        )}
        <input
          role="combobox"
          aria-autocomplete="list"
          aria-controls="suggestions"
          aria-expanded=${options.length ? "true" : "false"}
          aria-activedescendant=${this.active >= 0 && options[this.active] ? `option-${this.active}` : nothing}
          .value=${this.text}
          maxlength=${MAX_LENGTH}
          placeholder=${t("tags.add")}
          aria-label=${this.label || t("tags.add")}
          @input=${(event: Event) => {
            this.text = (event.target as HTMLInputElement).value;
            this.open = true;
            this.active = -1;
          }}
          @focus=${() => (this.open = true)}
          @keydown=${this.onKeydown}
        />
      </div>
      ${
        options.length
          ? html`<div
              class="suggestions"
              id="suggestions"
              role="listbox"
              @mousedown=${(event: Event) => event.preventDefault()}
            >
              ${options.map(
                ({ tag, create }, index) =>
                  html`<button
                    id="option-${index}"
                    class="suggestion ${create ? "create" : ""} ${index === this.active ? "active" : ""}"
                    role="option"
                    tabindex="-1"
                    aria-selected=${index === this.active ? "true" : "false"}
                    @click=${() => this.add(tag)}
                  >
                    ${create ? t("tags.create", { tag }) : tag}
                  </button>`,
              )}
            </div>`
          : nothing
      }
    </div>`;
  }

  private onKeydown(event: KeyboardEvent) {
    const options = this.options();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!options.length) return;
      event.preventDefault();
      this.open = true;
      const step = event.key === "ArrowDown" ? 1 : -1;
      this.active = Math.max(-1, Math.min(options.length - 1, this.active + step));
    } else if (event.key === "Enter") {
      event.preventDefault();
      this.add(options[this.active]?.tag ?? this.text);
    } else if (event.key === "Escape") {
      this.text = "";
      this.active = -1;
    }
  }

  private add(name: string) {
    const typed = name.trim();
    this.text = "";
    this.active = -1;
    if (!typed || this.tags.some((own) => same(own, typed))) return;
    const tag = this.catalog.find((existing) => same(existing, typed)) ?? typed;
    this.change([...this.tags, tag]);
  }

  private change(tags: string[]) {
    this.dispatchEvent(new CustomEvent("tags-change", { detail: sortTags(tags) }));
  }

  static override styles = [
    shared,
    css`
      .tag-input {
        position: relative;
      }
      /* Looks like the shared text field around its chips and input. */
      .chips {
        gap: 4px;
        min-height: 56px;
        box-sizing: border-box;
        padding: 4px 12px;
        border-bottom: 1px solid var(--input-idle-line-color, rgba(0, 0, 0, 0.42));
        border-radius: 4px 4px 0 0;
        background: var(--ha-color-form-background, var(--secondary-background-color, #ededed));
      }
      .chips:hover {
        border-bottom-color: var(--input-hover-line-color, rgba(0, 0, 0, 0.87));
      }
      .chips:focus-within {
        border-bottom-color: var(--primary-color);
        box-shadow: inset 0 -1px 0 var(--primary-color);
      }
      .tag-chip .remove {
        --ha-icon-button-size: 24px;
        --mdc-icon-size: 16px;
        margin-inline-end: -6px;
      }
      input {
        flex: 1;
        min-width: 120px;
        min-height: 0;
        border: 0;
        box-shadow: none;
        background: transparent;
        padding: 2px 4px;
      }
      .suggestions {
        position: absolute;
        z-index: 3;
        left: 0;
        right: 0;
        display: flex;
        flex-direction: column;
        margin-top: 2px;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
      }
      .suggestion {
        border: 0;
        background: none;
        color: var(--primary-text-color);
        text-align: left;
        font: inherit;
        padding: 6px 10px;
        cursor: pointer;
      }
      .suggestion:hover,
      .suggestion.active {
        background: var(--secondary-background-color, #ededed);
      }
      .create {
        color: var(--primary-color);
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-tag-input": TagInput;
  }
}
