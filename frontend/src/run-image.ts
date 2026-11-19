// One Run image. The image views need authentication, which `<img src>` can't
// send, so the image is fetched with `hass.fetchWithAuth` and shown from a blob.
import { LitElement, css, html, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { HomeAssistant } from "./hass";
import { localize } from "./localize";
import { shared } from "./styles";

@customElement("wattbill-run-image")
export class RunImageElement extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  /** The image's backend path; none shows the placeholder. */
  @property({ attribute: false }) src?: string;

  @state() private objectUrl?: string;
  @state() private failed = false;
  private request = 0;

  override connectedCallback() {
    super.connectedCallback();
    // Moved within the page (e.g. reordered tiles): load again what was let go.
    if (this.hasUpdated && !this.objectUrl) void this.load();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    this.request++;
    this.release();
  }

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has("src")) void this.load();
  }

  private release() {
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = undefined;
  }

  private async load() {
    const request = ++this.request;
    this.release();
    this.failed = false;
    if (!this.src) return;
    try {
      const response = await this.hass.fetchWithAuth(this.src);
      if (!response.ok) throw new Error(`${response.status}`);
      const blob = await response.blob();
      if (request === this.request) this.objectUrl = URL.createObjectURL(blob);
    } catch {
      if (request === this.request) this.failed = true;
    }
  }

  override render() {
    if (this.objectUrl) return html`<img src=${this.objectUrl} alt="" />`;
    return html`<div class="no-image">
      ${this.failed || !this.src ? localize(this.hass)("run.no_image") : ""}
    </div>`;
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      img {
        display: block;
        width: 100%;
        aspect-ratio: 4 / 3;
        object-fit: cover;
        border-radius: inherit;
      }
      .no-image {
        border-radius: inherit;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-image": RunImageElement;
  }
}
