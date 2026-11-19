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

  override render() {
    const t = localize(this.hass);
    const typed = this.text.trim();
    const suggestions = typed
      ? this.catalog
          .filter(
            (tag) =>
              tag.toLocaleLowerCase().includes(typed.toLocaleLowerCase()) &&
              !this.tags.some((own) => same(own, tag)),
          )
          .slice(0, MAX_SUGGESTIONS)
      : [];
    const known = [...this.catalog, ...this.tags].some((tag) => same(tag, typed));
    return html`<div class="tag-input">
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
          .value=${this.text}
          maxlength=${MAX_LENGTH}
          placeholder=${t("tags.add")}
          aria-label=${this.label || t("tags.add")}
          @input=${(event: Event) => (this.text = (event.target as HTMLInputElement).value)}
          @keydown=${this.onKeydown}
        />
      </div>
      ${
        suggestions.length || (typed && !known)
          ? html`<div class="suggestions" role="listbox">
              ${suggestions.map(
                (tag) =>
                  html`<button class="suggestion" @click=${() => this.add(tag)}>${tag}</button>`,
              )}
              ${
                typed && !known
                  ? html`<button class="suggestion create" @click=${() => this.add(typed)}>
                      ${t("tags.create", { tag: typed })}
                    </button>`
                  : nothing
              }
            </div>`
          : nothing
      }
    </div>`;
  }

  private onKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      this.add(this.text);
    } else if (event.key === "Escape") this.text = "";
  }

  private add(name: string) {
    const typed = name.trim();
    this.text = "";
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
      .chips {
        gap: 4px;
        padding: 4px;
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        background: var(--card-background-color, #fff);
      }
      .tag-chip .remove {
        --ha-icon-button-size: 24px;
        --mdc-icon-size: 16px;
        margin-inline-end: -6px;
      }
      input {
        flex: 1;
        min-width: 120px;
        border: 0;
        outline: none;
        font: inherit;
        font-size: 14px;
        color: var(--primary-text-color);
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
      .suggestion:focus-visible {
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
