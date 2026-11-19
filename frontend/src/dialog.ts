// A native modal <dialog> around its content: Escape and a click on the backdrop fire
// `cancel`, focus moves to the content's `[autofocus]` element and stays inside.
import { LitElement, css, html } from "lit";
import { customElement, property, query } from "lit/decorators.js";

@customElement("wattbill-dialog")
export class Dialog extends LitElement {
  /** A confirmation that needs an answer: an `alertdialog`. */
  @property({ type: Boolean }) alert = false;
  @property() label = "";

  @query("dialog") private dialog!: HTMLDialogElement;

  protected override firstUpdated() {
    this.dialog.showModal();
    this.querySelector<HTMLElement>("[autofocus]")?.focus();
  }

  override render() {
    return html`<dialog
      role=${this.alert ? "alertdialog" : "dialog"}
      aria-label=${this.label}
      @cancel=${(event: Event) => {
        event.preventDefault();
        this.cancel();
      }}
      @click=${(event: MouseEvent) => {
        if (event.target === this.dialog) this.cancel();
      }}
    >
      <slot></slot>
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
      background: transparent;
      color: inherit;
      font: inherit;
      overflow: auto;
    }
    ::slotted(*) {
      width: 100%;
      box-sizing: border-box;
    }
    dialog::backdrop {
      background: rgba(0, 0, 0, 0.4);
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-dialog": Dialog;
  }
}
