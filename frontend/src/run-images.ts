// A Run's image column: the Cover Image, every image with "Set as cover" and delete,
// and the photo upload. Hands each Run the backend returns to the page as `run-changed`.
import { mdiDelete, mdiUpload } from "@mdi/js";
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { deleteImage, getRun, setCover, uploadImages, type RunDetail, type RunImage } from "./api";
import type { HomeAssistant } from "./hass";
import { isKey, localize } from "./localize";
import "./dialog";
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
    const { limit, types, max_bytes } = run.uploads;
    const rules = { limit, size: Math.floor(max_bytes / 1024 / 1024) };
    const full = run.images.filter((image) => image.kind === "upload").length >= limit;
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
      <ha-button
        class="small upload"
        appearance="filled"
        ?disabled=${full || this.busy}
        .loading=${this.busy}
        @click=${() => this.renderRoot.querySelector<HTMLInputElement>("input[type=file]")?.click()}
      >
        <ha-svg-icon slot="start" .path=${mdiUpload}></ha-svg-icon>
        ${this.busy ? t("images.uploading") : t("images.upload")}
      </ha-button>
      <input
        type="file"
        multiple
        hidden
        accept=${types.join(",")}
        ?disabled=${full || this.busy}
        @change=${this.onFiles}
      />
      <p class="muted small">${t("images.limit", rules)}</p>
      ${
        this.error
          ? html`<p class="images-error small">
              ${t(isKey(errorKey) ? errorKey : "images.error.failed", rules)}
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
            : html`<ha-button
                class="small set-cover"
                appearance="plain"
                ?disabled=${this.busy}
                @click=${() => this.change(() => setCover(this.hass, this.run.id, image.id))}
              >
                ${t("images.set_cover")}
              </ha-button>`
        }
        <ha-icon-button
          class="delete-image"
          .label=${t("images.delete")}
          .path=${mdiDelete}
          ?disabled=${this.busy}
          @click=${() => (this.deleting = image)}
        ></ha-icon-button>
      </div>
    </figure>`;
  }

  private renderDeleteDialog(image: RunImage) {
    const t = localize(this.hass);
    const cancel = () => (this.deleting = undefined);
    return html`<wattbill-dialog alert .label=${t("images.delete_title")} @cancel=${cancel}>
      <div class="image-dialog dialog card">
        <h2>${t("images.delete_title")}</h2>
        <wattbill-run-image .hass=${this.hass} .src=${image.tile_url}></wattbill-run-image>
        <p class="muted small">${t("images.delete_warning")}</p>
        <div class="row end">
          <ha-button class="cancel" appearance="plain" autofocus @click=${cancel}>
            ${t("delete.cancel")}
          </ha-button>
          <ha-button class="confirm" variant="danger" @click=${() => this.delete(image)}>
            ${t("delete.confirm")}
          </ha-button>
        </div>
      </div>
    </wattbill-dialog>`;
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
      .delete-image {
        --ha-icon-button-size: 32px;
        --mdc-icon-size: 20px;
        color: var(--secondary-text-color);
      }
      p {
        margin: 6px 0 12px;
      }
      .images-error {
        color: var(--error-color, #db4437);
      }
      wattbill-dialog {
        --wattbill-dialog-width: 360px;
      }
    `,
  ];
}

declare global {
  interface HTMLElementTagNameMap {
    "wattbill-run-images": RunImages;
  }
}
