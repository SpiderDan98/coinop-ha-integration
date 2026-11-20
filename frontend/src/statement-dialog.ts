// The browser remembers the options of the last statement made, all but title and note.
import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  STATEMENT_DETAILS,
  STATEMENT_LANGUAGES,
  createStatement,
  getStatementDefaults,
} from "./api";
import { download, type HomeAssistant } from "./hass";
import { localize, panelLanguage } from "./localize";
import { formDialog } from "./dialog";
import { checkbox, field, input, numberInput, select, textarea, withUnit } from "./fields";
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
    const set = (changes: Partial<Options>) => {
      if (options) this.options = { ...options, ...changes };
    };
    return formDialog({
      t,
      title:
        this.runIds.length === 1
          ? t("statement.dialog_title_one")
          : t("statement.dialog_title", { count: this.runIds.length }),
      name: "statement-dialog",
      action: "download",
      submit: t("statement.download"),
      busy: this.busy,
      disabled: !options || this.typedMarkup === undefined,
      error: this.failed && t("statement.failed"),
      onCancel: () => this.close(),
      onSubmit: () => this.download(),
      content: html`<p class="muted small">${t("statement.hint")}</p>
        ${field(
          t("statement.title"),
          input({
            name: "title",
            value: this.titleText,
            placeholder: this.defaultTitle,
            onInput: (title) => (this.titleText = title),
          }),
        )}
        ${field(
          t("statement.note"),
          textarea({
            name: "note",
            value: this.noteText,
            onInput: (note) => (this.noteText = note),
          }),
        )}
        <div class="field-row">
          ${field(
            t("statement.detail"),
            select({
              name: "detail",
              value: options?.detail,
              options: STATEMENT_DETAILS.map((detail) => [detail, t(`statement.${detail}`)]),
              onChange: (detail) => set({ detail: detail as Options["detail"] }),
            }),
          )}
          ${field(
            t("statement.language"),
            select({
              name: "language",
              value: options?.language,
              options: STATEMENT_LANGUAGES.map((language) => [language, LANGUAGE_NAMES[language]]),
              onChange: (language) => set({ language: language as Options["language"] }),
            }),
          )}
          ${field(
            t("statement.markup"),
            withUnit(
              numberInput({
                name: "markup",
                value: this.markup,
                onInput: (markup) => (this.markup = markup),
              }),
              "%",
            ),
          )}
        </div>
        ${checkbox({
          name: "images",
          label: t("statement.images"),
          checked: options?.images ?? true,
          disabled: options?.detail === "compact",
          onChange: (images) => set({ images }),
        })}`,
    });
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
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "coinop-statement-dialog": StatementDialog;
  }
}
