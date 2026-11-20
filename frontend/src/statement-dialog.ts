// The browser remembers the options of the last statement made, all but title and note.
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
import "./dialog";
import { shared } from "./styles";

type Options = Omit<Parameters<typeof createStatement>[2], "title" | "note">;

const REMEMBERED = "coinop-statement-options";

const FITS = {
  detail: (value: unknown) => STATEMENT_DETAILS.some((detail) => detail === value),
  images: (value: unknown) => typeof value === "boolean",
  language: (value: unknown) => STATEMENT_LANGUAGES.some((language) => language === value),
  markup: (value: unknown) => typeof value === "number" && value >= 0,
} satisfies Record<keyof Options, (value: unknown) => boolean>;

/** The remembered options that still fit; none where the browser keeps no storage. */
function remembered(): Partial<Options> {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(REMEMBERED) ?? "{}");
    return Object.fromEntries(
      Object.entries(stored ?? {}).filter(
        ([name, value]) => name in FITS && FITS[name as keyof Options](value),
      ),
    );
  } catch {
    return {};
  }
}

function remember(options: Options) {
  try {
    localStorage.setItem(REMEMBERED, JSON.stringify(options));
  } catch {
    // Private mode or storage switched off: next time starts from the defaults.
  }
}

/** Each language by its own name. */
const LANGUAGE_NAMES = { en: "English", de: "Deutsch" } satisfies Record<
  Options["language"],
  string
>;

@customElement("coinop-statement-dialog")
export class StatementDialog extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** The selected final Runs, by start. */
  @property({ attribute: false }) runIds: string[] = [];
  /** The Tag filtered by, when exactly one is: the default title names it. */
  @property({ attribute: false }) tag?: string;

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
    this.options = { detail: "detailed", images: true, language, markup, ...remembered() };
    this.markup = String(this.options.markup);
  }

  /** The Markup typed, if it is one: a number of at least 0. */
  private get typedMarkup() {
    const markup = this.markup.trim() === "" ? NaN : Number(this.markup);
    return markup >= 0 ? markup : undefined;
  }

  /** The default title in the statement's language, not the panel's. */
  private get defaultTitle() {
    const t = this.options
      ? localize({ ...this.hass, language: this.options.language })
      : localize(this.hass);
    return this.tag
      ? t("statement.default_title_tag", { tag: this.tag })
      : t("statement.default_title");
  }

  override render() {
    const t = localize(this.hass);
    const options = this.options;
    const input = (event: Event) => (event.target as HTMLInputElement).value;
    const set = (changes: Partial<Options>) => {
      if (options) this.options = { ...options, ...changes };
    };
    const title =
      this.runIds.length === 1
        ? t("statement.dialog_title_one")
        : t("statement.dialog_title", { count: this.runIds.length });
    return html`<coinop-dialog
      class="statement-dialog dialog"
      .label=${title}
      .closeLabel=${t("dialog.close")}
      @cancel=${this.close}
    >
      <p class="muted small">${t("statement.hint")}</p>
      <label
        >${t("statement.title")}<input
          name="title"
          .value=${this.titleText}
          placeholder=${this.defaultTitle}
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
        <label class="check"
          ><input
            name="images"
            type="checkbox"
            .checked=${options?.images ?? true}
            ?disabled=${options?.detail === "compact"}
            @change=${(event: Event) => set({ images: (event.target as HTMLInputElement).checked })}
          />${t("statement.images")}</label
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
      <div slot="footer" class="row end">
        <ha-button class="cancel" appearance="plain" @click=${this.close}>
          ${t("statement.cancel")}
        </ha-button>
        <ha-button
          class="download"
          ?disabled=${!options || this.typedMarkup === undefined || this.busy}
          .loading=${this.busy}
          @click=${this.download}
        >
          ${t("statement.download")}
        </ha-button>
      </div>
    </coinop-dialog>`;
  }

  private async download() {
    const markup = this.typedMarkup;
    if (!this.options || markup === undefined) return;
    this.busy = true;
    this.failed = false;
    const options = { ...this.options, markup };
    try {
      download(
        await createStatement(this.hass, this.runIds, {
          ...options,
          title: this.titleText.trim() || (this.tag ? this.defaultTitle : null),
          note: this.noteText.trim() || null,
        }),
      );
      remember(options);
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
      coinop-dialog {
        --coinop-dialog-width: 520px;
      }
      .options {
        flex-wrap: wrap;
        align-items: flex-end;
      }
      .options > label {
        flex: 1 1 130px;
      }
      .options > label.check {
        flex: 0 0 auto;
        flex-direction: row;
        align-items: center;
        gap: 6px;
        font-size: 14px;
        color: var(--primary-text-color);
        padding-bottom: 7px;
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-statement-dialog": StatementDialog;
  }
}
