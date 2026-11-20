// A native modal <dialog> laid out as HA's dialogs: Escape, a click on the backdrop and
// the close button fire `cancel`, focus moves to the content's `[autofocus]` element.
import { mdiClose } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, query } from "lit/decorators.js";
import type { Localize } from "./localize";

let openDialogs = 0;

/** The page behind an open dialog doesn't scroll; the scrollbar's gutter stays, so nothing shifts. */
const lockPageScroll = (lock: boolean) => {
  openDialogs += lock ? 1 : -1;
  if (openDialogs !== (lock ? 1 : 0)) return;
  const { documentElement: page } = document;
  const scrollbar = window.innerWidth - page.clientWidth;
  page.style.overflow = lock ? "hidden" : "";
  page.style.scrollbarGutter = lock && scrollbar > 0 ? "stable" : "";
};

@customElement("coinop-dialog")
export class Dialog extends LitElement {
  /** A confirmation that needs an answer: an `alertdialog` without a close button. */
  @property({ type: Boolean }) alert = false;
  /** The dialog's heading. */
  @property() label = "";
  @property() closeLabel = "";

  @query("dialog") private dialog!: HTMLDialogElement;

  override connectedCallback() {
    super.connectedCallback();
    lockPageScroll(true);
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    lockPageScroll(false);
  }

  protected override firstUpdated() {
    this.dialog.showModal();
    this.querySelector<HTMLElement>("[autofocus]")?.focus();
  }

  override render() {
    return html`<dialog
      role=${this.alert ? "alertdialog" : "dialog"}
      aria-labelledby="heading"
      @cancel=${(event: Event) => {
        event.preventDefault();
        this.cancel();
      }}
      @click=${(event: MouseEvent) => {
        if (event.target === this.dialog) this.cancel();
      }}
    >
      <div class="surface">
        <header>
          ${
            this.alert
              ? nothing
              : html`<ha-icon-button
                  class="close"
                  .label=${this.closeLabel}
                  .path=${mdiClose}
                  @click=${this.cancel}
                ></ha-icon-button>`
          }
          <h2 id="heading">${this.label}</h2>
        </header>
        <div class="content"><slot></slot></div>
        <footer><slot name="footer"></slot></footer>
      </div>
    </dialog>`;
  }

  private cancel() {
    this.dispatchEvent(new Event("cancel"));
  }

  static override styles = css`
    dialog {
      width: min(var(--coinop-dialog-width, 480px), calc(100% - 32px));
      max-height: calc(100% - 32px);
      box-sizing: border-box;
      padding: 0;
      border: 0;
      border-radius: 24px;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color);
      box-shadow:
        0 6px 12px -3px rgba(0, 0, 0, 0.4),
        0 16px 32px -6px rgba(0, 0, 0, 0.55);
      font: inherit;
      overflow: hidden;
    }
    dialog[open] {
      display: flex;
    }
    dialog::backdrop {
      background: rgba(0, 0, 0, 0.5);
    }
    .surface {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
    }
    header {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 16px 24px 8px;
    }
    .close {
      margin: -6px 0 -6px -16px;
    }
    h2 {
      margin: 0;
      font-size: var(--ha-font-size-xl, 20px);
      font-weight: var(--ha-font-weight-medium, 500);
      line-height: 24px;
    }
    .content {
      flex: 1;
      min-height: 0;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 8px 24px;
    }
    footer {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      padding: 8px 16px 16px;
    }
  `;
}

/** The dialog everything is edited in: its fields, what went wrong, then Cancel and the
 * action that saves, which Enter in a field takes too. Nothing is saved before. */
export const formDialog = ({
  t,
  title,
  name = "",
  content,
  error,
  action = "save",
  submit = t("dialog.save"),
  busy = false,
  disabled = false,
  onCancel,
  onSubmit,
}: {
  t: Localize;
  title: string;
  /** Classes of the dialog, e.g. "wide". */
  name?: string;
  content: unknown;
  error?: unknown;
  /** The class of the saving button. */
  action?: string;
  submit?: string;
  busy?: boolean;
  disabled?: boolean;
  onCancel: () => void;
  onSubmit: () => void;
}) =>
  html`<coinop-dialog
    class="dialog ${name}"
    .label=${title}
    .closeLabel=${t("dialog.close")}
    @cancel=${onCancel}
    @keydown=${(event: KeyboardEvent) => {
      const { key, target } = event;
      if (key !== "Enter" || event.defaultPrevented || !(target instanceof HTMLInputElement))
        return;
      if (target.type === "checkbox" || target.type === "color") return;
      event.preventDefault();
      if (!busy && !disabled) onSubmit();
    }}
  >
    ${content} ${error ? html`<p class="error small">${error}</p>` : nothing}
    <div slot="footer" class="row end">
      <ha-button class="cancel" appearance="plain" @click=${onCancel}>
        ${t("dialog.cancel")}
      </ha-button>
      <ha-button class=${action} ?disabled=${busy || disabled} .loading=${busy} @click=${onSubmit}>
        ${submit}
      </ha-button>
    </div>
  </coinop-dialog>`;

/** A confirmation of something that can't be undone; Cancel has the focus. */
export const confirmDialog = ({
  t,
  title,
  name = "",
  content,
  confirm = t("delete.confirm"),
  onCancel,
  onConfirm,
}: {
  t: Localize;
  title: string;
  name?: string;
  content: unknown;
  confirm?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) =>
  html`<coinop-dialog class="dialog ${name}" alert .label=${title} @cancel=${onCancel}>
    ${content}
    <div slot="footer" class="row end">
      <ha-button class="cancel" appearance="plain" autofocus @click=${onCancel}>
        ${t("dialog.cancel")}
      </ha-button>
      <ha-button class="confirm" variant="danger" @click=${onConfirm}>${confirm}</ha-button>
    </div>
  </coinop-dialog>`;

declare global {
  interface HTMLElementTagNameMap {
    "coinop-dialog": Dialog;
  }
}
