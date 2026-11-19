// A Run's image column: the Cover Image, every image with "Set as cover" and delete,
// and the photo upload. Hands each Run the backend returns to the page as `run-changed`.
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  UPLOAD_LIMIT,
  UPLOAD_TYPES,
  deleteImage,
  getRun,
  setCover,
  uploadImages,
  type RunDetail,
  type RunImage,
} from "./api";
import type { HomeAssistant } from "./hass";
import { isKey, localize } from "./localize";
import "./run-image";
import { shared } from "./styles";

@customElement("wattbill-run-images")
export class RunImages extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) run!: RunDetail;

  @state() private busy = false;
  /** Why the last change failed: an upload's refusal code, else "failed". */
  @state() private error?: string;
  /** Set while its delete confirmation is open. */
  @state() private deleting?: RunImage;

  private async change(work: () => Promise<RunDetail>) {
    this.busy = true;
    this.error = undefined;
    try {
      const run = await work();
      this.dispatchEvent(new CustomEvent("run-changed", { detail: run }));
    } catch (error) {
      this.error = error instanceof Error ? error.message : "failed";
    }
    this.busy = false;
  }

  private onFiles(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = [...(input.files ?? [])];
    input.value = "";
    if (!files.length) return;
    const runId = this.run.id;
    void this.change(async () => {
      await uploadImages(this.hass, runId, files);
      return getRun(this.hass, runId);
    });
  }

  private delete(image: RunImage) {
    this.deleting = undefined;
    void this.change(() => deleteImage(this.hass, this.run.id, image.id));
  }

  override render() {
    const t = localize(this.hass);
    const run = this.run;
    const full = run.images.filter((image) => image.kind === "upload").length >= UPLOAD_LIMIT;
    const errorKey = `images.error.${this.error}`;
    return html`
      <wattbill-run-image
        class="cover"
        .hass=${this.hass}
        .src=${run.cover?.url}
      ></wattbill-run-image>
      ${
        run.images.length
          ? html`<div class="strip">
              ${run.images.map((image) => this.renderImage(image, image.id === run.cover?.id))}
            </div>`
          : nothing
      }
      <label class="btn small upload" aria-disabled=${String(full || this.busy)}>
        ${this.busy ? t("images.uploading") : `+ ${t("images.upload")}`}
        <input
          type="file"
          multiple
          accept=${UPLOAD_TYPES.join(",")}
          ?disabled=${full || this.busy}
          @change=${this.onFiles}
        />
      </label>
      <p class="muted small">${t("images.limit", { limit: UPLOAD_LIMIT })}</p>
      ${
        this.error
          ? html`<p class="images-error small">
              ${t(isKey(errorKey) ? errorKey : "images.error.failed", { limit: UPLOAD_LIMIT })}
            </p>`
          : nothing
      }
      ${this.deleting ? this.renderDeleteDialog(this.deleting) : nothing}
    `;
  }

  private renderImage(image: RunImage, isCover: boolean) {
    const t = localize(this.hass);
    return html`<figure>
      <wattbill-run-image .hass=${this.hass} .src=${image.tile_url}></wattbill-run-image>
      <figcaption>${t(`image.${image.kind}`)}</figcaption>
      <div class="actions">
        ${
          isCover
            ? html`<span class="is-cover">${t("images.is_cover")}</span>`
            : html`<button
                class="link set-cover"
                ?disabled=${this.busy}
                @click=${() => this.change(() => setCover(this.hass, this.run.id, image.id))}
              >
                ${t("images.set_cover")}
              </button>`
        }
        <button
          class="link delete-image"
          title=${t("images.delete")}
          aria-label=${t("images.delete")}
          ?disabled=${this.busy}
          @click=${() => (this.deleting = image)}
        >
          ✕
        </button>
      </div>
    </figure>`;
  }

  private renderDeleteDialog(image: RunImage) {
    const t = localize(this.hass);
    return html`<div class="scrim">
      <div class="image-dialog card" role="alertdialog" aria-modal="true">
        <h2>${t("images.delete_title")}</h2>
        <wattbill-run-image .hass=${this.hass} .src=${image.tile_url}></wattbill-run-image>
        <p class="muted small">${t("images.delete_warning")}</p>
        <div class="row end">
          <button class="btn cancel" @click=${() => (this.deleting = undefined)}>
            ${t("delete.cancel")}
          </button>
          <button class="btn danger confirm" @click=${() => this.delete(image)}>
            ${t("delete.confirm")}
          </button>
        </div>
      </div>
    </div>`;
  }

  static override styles = [
    shared,
    css`
      :host {
        display: block;
      }
      .cover {
        border-radius: 10px;
        overflow: hidden;
        margin-bottom: 12px;
      }
      .strip {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 8px;
      }
      figure {
        margin: 0;
        width: 96px;
        text-align: center;
        font-size: 11px;
        color: var(--secondary-text-color);
      }
      figure wattbill-run-image {
        border-radius: 6px;
        overflow: hidden;
        margin-bottom: 2px;
      }
      .actions {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 4px;
        min-height: 20px;
      }
      .is-cover {
        color: var(--primary-color);
        font-weight: 600;
      }
      .link {
        font: inherit;
        color: var(--primary-color);
        background: none;
        border: 0;
        padding: 2px 0;
        cursor: pointer;
        text-align: left;
      }
      .delete-image {
        color: var(--secondary-text-color);
      }
      .link:disabled {
        opacity: 0.5;
        cursor: default;
      }
      .upload {
        position: relative;
        display: inline-flex;
        cursor: pointer;
      }
      .upload[aria-disabled="true"] {
        opacity: 0.5;
        cursor: default;
      }
      .upload input {
        position: absolute;
        width: 1px;
        height: 1px;
        opacity: 0;
        pointer-events: none;
      }
      p {
        margin: 6px 0 12px;
      }
      .images-error {
        color: var(--error-color, #db4437);
      }
      .scrim {
        position: fixed;
        inset: 0;
        z-index: 5;
        display: grid;
        place-items: center;
        padding: 16px;
        background: rgba(0, 0, 0, 0.4);
      }
      .image-dialog {
        width: min(360px, 100%);
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .image-dialog p {
        margin: 0;
      }
      .end {
        justify-content: flex-end;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-images": RunImages;
  }
}
