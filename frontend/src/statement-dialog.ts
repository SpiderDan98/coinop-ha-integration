// The basket's "Cost Statement…" dialog: options for the PDF of the selected Runs, which
// the backend renders and the browser downloads through a signed path. Fires `close`.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  STATEMENT_DETAILS,
  STATEMENT_LANGUAGES,
  createStatement,
  getStatementDefaults,
} from "./api";
import { download, type HomeAssistant } from "./hass";
import { localize, panelLanguage } from "./localize";
import { shared } from "./styles";

type Options = Omit<Parameters<typeof createStatement>[2], "title" | "note">;

/** Each language by its own name. */
const LANGUAGE_NAMES = { en: "English", de: "Deutsch" } satisfies Record<
  Options["language"],
  string
>;

@customElement("wattbill-statement-dialog")
export class StatementDialog extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** The selected final Runs, by start. */
  @property({ attribute: false }) runIds: string[] = [];

  @state() private titleText = "";
  @state() private noteText = "";
  /** Undefined until the hub's default Markup is known. */
  @state() private options?: Options;
  @state() private markup = "";
  @state() private busy = false;
  @state() private failed = false;

  override connectedCallback() {
    super.connectedCallback();
    void this.load();
  }

  private async load() {
    const language = panelLanguage(this.hass) as Options["language"];
    const { markup } = await getStatementDefaults(this.hass).catch(() => ({ markup: 0 }));
    this.options = { detail: "detailed", language, markup };
    this.markup = String(markup);
  }

  /** The Markup typed, if it is one: a number of at least 0. */
  private get typedMarkup() {
    const markup = this.markup.trim() === "" ? NaN : Number(this.markup);
    return markup >= 0 ? markup : undefined;
  }

  override render() {
    const t = localize(this.hass);
    const options = this.options;
    // The default title in the statement's language, not the panel's.
    const statementT = options ? localize({ ...this.hass, language: options.language }) : t;
    const input = (event: Event) => (event.target as HTMLInputElement).value;
    const set = (changes: Partial<Options>) => {
      if (options) this.options = { ...options, ...changes };
    };
    return html`<div class="scrim">
      <div class="statement-dialog card" role="dialog" aria-modal="true">
        <h2>
          ${
            this.runIds.length === 1
              ? t("statement.dialog_title_one")
              : t("statement.dialog_title", { count: this.runIds.length })
          }
        </h2>
        <p class="muted small">${t("statement.hint")}</p>
        <label
          >${t("statement.title")}<input
            name="title"
            .value=${this.titleText}
            placeholder=${statementT("statement.default_title")}
            @input=${(event: Event) => (this.titleText = input(event))}
        /></label>
        <label
          >${t("statement.note")}<textarea
            name="note"
            rows="3"
            .value=${this.noteText}
            @input=${(event: Event) => (this.noteText = input(event))}
          ></textarea>
        </label>
        <div class="row options">
          <label
            >${t("statement.detail")}<select
              name="detail"
              @change=${(event: Event) => set({ detail: input(event) as Options["detail"] })}
            >
              ${STATEMENT_DETAILS.map(
                (detail) =>
                  html`<option value=${detail} ?selected=${options?.detail === detail}>
                    ${t(`statement.${detail}`)}
                  </option>`,
              )}
            </select></label
          >
          <label
            >${t("statement.language")}<select
              name="language"
              @change=${(event: Event) => set({ language: input(event) as Options["language"] })}
            >
              ${STATEMENT_LANGUAGES.map(
                (language) =>
                  html`<option value=${language} ?selected=${options?.language === language}>
                    ${LANGUAGE_NAMES[language]}
                  </option>`,
              )}
            </select></label
          >
          <label
            >${t("statement.markup")}<input
              name="markup"
              type="number"
              min="0"
              step="any"
              inputmode="decimal"
              .value=${this.markup}
              @input=${(event: Event) => (this.markup = input(event))}
          /></label>
        </div>
        ${this.failed ? html`<p class="error small">${t("statement.failed")}</p>` : nothing}
        <div class="row end">
          <button class="btn cancel" @click=${this.close}>${t("statement.cancel")}</button>
          <button
            class="btn download"
            ?disabled=${!options || this.typedMarkup === undefined || this.busy}
            @click=${this.download}
          >
            ${t("statement.download")}
          </button>
        </div>
      </div>
    </div>`;
  }

  private async download() {
    const markup = this.typedMarkup;
    if (!this.options || markup === undefined) return;
    this.busy = true;
    this.failed = false;
    try {
      download(
        await createStatement(this.hass, this.runIds, {
          ...this.options,
          markup,
          title: this.titleText.trim() || null,
          note: this.noteText.trim() || null,
        }),
      );
      this.close();
    } catch {
      this.failed = true;
    } finally {
      this.busy = false;
    }
  }

  private close() {
    this.dispatchEvent(new Event("close"));
  }

  static override styles = [
    shared,
    css`
      .statement-dialog {
        width: min(520px, 100%);
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .statement-dialog p,
      .statement-dialog h2 {
        margin: 0;
      }
      .options {
        flex-wrap: wrap;
        align-items: flex-end;
      }
      .options > label {
        flex: 1 1 130px;
      }
      .error {
        color: var(--error-color, #db4437);
      }
      label {
        display: flex;
        flex-direction: column;
        gap: 3px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      input,
      select,
      textarea {
        font: inherit;
        font-size: 14px;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        border-radius: 6px;
        padding: 6px 8px;
      }
      textarea {
        resize: vertical;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-statement-dialog": StatementDialog;
  }
}
