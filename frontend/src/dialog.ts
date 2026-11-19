// A native modal <dialog> laid out as HA's dialogs: Escape, a click on the backdrop and
// the close button fire `cancel`, focus moves to the content's `[autofocus]` element.
import { mdiClose } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, query } from "lit/decorators.js";

@customElement("wattbill-dialog")
export class Dialog extends LitElement {
  /** A confirmation that needs an answer: an `alertdialog` without a close button. */
  @property({ type: Boolean }) alert = false;
  /** The dialog's heading. */
  @property() label = "";
  @property() closeLabel = "";

  @query("dialog") private dialog!: HTMLDialogElement;

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
      width: min(var(--wattbill-dialog-width, 480px), calc(100% - 32px));
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

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-dialog": Dialog;
  }
}
