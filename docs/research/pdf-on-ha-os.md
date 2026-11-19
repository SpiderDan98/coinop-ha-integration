# How does an HA integration on HA OS produce a PDF? (Issue #4)

Research date: 2026-11-19. Versions and wheel tags were checked directly against the PyPI JSON API, the npm registry, and `raw.githubusercontent.com/home-assistant/core/dev/...`. Terms follow `GLOSSARY.md` (**Run**, **Line Item**, **Cost Statement**).

## Summary

- **Only amd64 and aarch64 matter now.** HA deprecated i386, armhf and armv7 in May 2025. Support ended with 2025.12, and HA no longer builds containers for those architectures. armv7 does not need to be supported. The HA wheels index now carries only `musllinux_1_2_x86_64` and `aarch64` wheels for current versions.
- **Pillow is already an HA core dependency** (`Pillow==13.0.0` in `requirements.txt`, `pyproject.toml` and `package_constraints.txt`). HA core neither ships nor pins any PDF generator (fpdf2, reportlab, borb, WeasyPrint), and it doesn't include `fonttools` either.
- **fpdf2 2.9.0** (LGPL-3.0, released 2026-10-29) is a pure `py3-none-any` wheel. It depends only on Pillow (already in HA) and `fonttools`. fonttools publishes `musllinux_1_2` wheels for x86_64 and aarch64, plus a `py3-none-any` fallback. **Install risk on HA OS: very low.** fpdf2 has a table API with repeated header rows and images in cells. It embeds TTF fonts as subsets and passes JPEGs through unchanged.
- **reportlab 5.1.0** (BSD, released 2026-10-22) also ships only as a `py3-none-any` wheel now. Since 4.0 its C extensions are optional (`rl_accel` is an extra). It depends on Pillow and `charset-normalizer`. HA constrains charset-normalizer to `3.4.3`, which is compatible because reportlab doesn't pin a version. On installation it is as safe as fpdf2, but its API is heavier.
- **borb is AGPL-3.0-or-later**, which rules it out for a public HACS repo: the copyleft could extend to the integration. **WeasyPrint is unsuitable** because it needs Pango and other system libraries (`libpango`, `libharfbuzz`, `libfontconfig`, …), and an integration can't install those through `manifest.json`.
- **Umlauts and €:**
  - fpdf2's core fonts encode as **Latin-1** by default. Umlauts work, but **€ raises an exception**. Setting `core_fonts_encoding = "cp1252"` works around that. The cleaner fix is to ship a TTF font (e.g. DejaVu Sans or Noto Sans) with the integration and load it with `add_font()`.
  - jsPDF's README says its standard fonts are limited to the ASCII codepage, so UTF-8 text needs a custom TTF.
  - pdfmake uses Roboto by default.
- **Browser options:**
  - jsPDF 4.2.1 + jspdf-autotable 5.0.9 (both MIT) are about 130 KB + 10 KB gzipped.
  - pdfmake 0.3.14 (MIT) is about 296 KB gzipped, plus about 468 KB gzipped for `vfs_fonts.js`.
  - Neither needs a Python dependency. Both move layout, fonts and image fetching (authenticated camera and thumbnail URLs) to the client.
  - **`window.print()` is the least reliable option.** Per Chromium and Cordova sources, Android WebView doesn't implement `window.print`, and the HA frontend's sidebar and header would have to be hidden with print CSS.
- **Delivery:** The proven HA pattern works like this:
  1. A `HomeAssistantView` serves the file (`requires_auth = True` is the default).
  2. The frontend gets a short-lived signed URL through the WebSocket command `auth/sign_path`.
  3. The frontend triggers an `<a download>` click on that URL.

  This is exactly how the HA frontend downloads backups. Signed paths only work for GET/HEAD, and the query parameters are part of the signature. The alternative is `fetch` with the bearer token, then a blob download. The Android Companion app demonstrably handles both `blob:` and `https:` downloads.
- **Recommendation: generate the PDF server-side with fpdf2.**
  - Bundle a TTF font (OFL or Bitstream Vera licence) in the integration directory.
  - Run generation in `hass.async_add_executor_job`, since it is CPU-bound and blocking.
  - Fetch images in the backend directly from HA (camera snapshot, thumbnail bytes) and pass them as `bytes`/`BytesIO`.
  - Deliver the PDF through an authenticated `HomeAssistantView` with `Content-Disposition: attachment` and a signed path.
  - Fallback: if fpdf2 causes problems, switch to reportlab. It installs just as easily and has a BSD licence.
  - Browser alternative: pdfmake, but only if Python requirements must be avoided entirely.

---

## 1. Constraints on HA OS / HA Container

### 1.1 Architectures
- The HA blog post of 2025-05-22 deprecates i386, armhf and armv7, giving usage below 1 % as the reason. Support ended with **2025.12**, after which HA stops building distributions and containers for these platforms. Going forward "only the currently supported 64-bit architectures (aarch64 and amd64)" are used. Source: [Deprecating Core and Supervised installation methods, and 32-bit systems](https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/)
- The HA wheels index has `armv6l`, `armv7l` and `i686` wheels for Pillow only up to 9.5.0. Current versions (12.x, 13.0.0) are built only for `musllinux_1_2_x86_64` and `aarch64`. Source: <https://wheels.home-assistant.io/musllinux-index/pillow/> (listing fetched 2026-11-19)
- **Uncertainty:** A community thread about 2026.02.3 indicates the Supervisor removed the deprecated architectures in stages. I did not verify the exact dates ([thread](https://community.home-assistant.io/t/update-2026-02-3-dropping-most-pi-support/995473)). It doesn't matter for a new integration.

### 1.2 How `manifest.json` `requirements` are installed
- `requirements` is a list of pip specifiers pinned to an exact version. If installation fails, the integration does not load. Custom integrations should list only packages HA does not already depend on. Source: [Integration manifest](https://contributors.home-assistant.io/core/integrations/manifest/) (formerly developers.home-assistant.io/docs/creating_integration_manifest)
- At runtime HA installs with **`uv pip install --index-strategy unsafe-first-match --constraint package_constraints.txt`**. Sources: [`homeassistant/util/package.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/util/package.py) (`install_package`) and [`homeassistant/requirements.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/requirements.py) (`CONSTRAINT_FILE = "package_constraints.txt"`)
- The Docker base image sets `UV_EXTRA_INDEX_URL=https://wheels.home-assistant.io/musllinux-index/`, so uv tries the HA wheels index first and then PyPI. If the extra index fails, `package.py` retries with only the healthy indexes. Sources: [`home-assistant/docker-base` `alpine/Dockerfile`](https://github.com/home-assistant/docker-base/blob/master/alpine/Dockerfile), [`package.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/util/package.py)
- **What this means:** The HA wheels index only matters for packages HA itself uses. It has no fpdf2 or reportlab, and only old fonttools versions (up to 4.41.0, `py3-none-any`). A custom integration therefore effectively relies on **PyPI wheels**.
  - Pure `py3-none-any` packages are no problem.
  - Packages with C extensions need `musllinux` wheels. Without them uv builds from the sdist, and the HA container usually has no compiler for that.
  - **Uncertainty:** I did not check the runtime image itself for build tools. HA builds its own image with `uv pip install --no-build` ([`Dockerfile`](https://github.com/home-assistant/core/blob/dev/Dockerfile)), which strongly suggests HA relies on prebuilt wheels.
- HA core requires `requires-python = ">=3.14.2"` ([`pyproject.toml`](https://github.com/home-assistant/core/blob/dev/pyproject.toml)). Any compiled package therefore needs `cp314` musllinux wheels.

### 1.3 What HA core already pins or ships
Checked in [`requirements.txt`](https://github.com/home-assistant/core/blob/dev/requirements.txt), [`requirements_all.txt`](https://github.com/home-assistant/core/blob/dev/requirements_all.txt), [`package_constraints.txt`](https://github.com/home-assistant/core/blob/dev/homeassistant/package_constraints.txt) and [`pyproject.toml`](https://github.com/home-assistant/core/blob/dev/pyproject.toml) (branch `dev`, 2026-11-19):

| Package | In HA? |
|---|---|
| Pillow | **Yes, core dependency**: `Pillow==13.0.0` (requirements.txt, pyproject.toml, package_constraints.txt) |
| charset-normalizer | **Constraint `==3.4.3`** in package_constraints.txt (comment: its mypyc binary wheels cause issues with HA's wheel builder) |
| defusedxml | `==0.7.1` in requirements_all.txt (used by some integrations) |
| lxml | `==6.1.3` in requirements_all.txt |
| fonttools, fpdf2, reportlab, borb, weasyprint, pypdf | **Not present** |

The HA Docker image pre-installs `requirements_all.txt` ([`Dockerfile`](https://github.com/home-assistant/core/blob/dev/Dockerfile)), which doesn't list transitive dependencies. **Uncertainty:** I did not verify whether `fonttools` is already in the image as a transitive dependency. It doesn't change the assessment, because fonttools has suitable wheels.

---

## 2. Backend options (Python)

### 2.1 fpdf2 (recommended)
- **Version, licence, maintenance:** 2.9.0, released 2026-10-29, licence `LGPL-3.0-only`, `requires_python >=3.11`. The 2.9.1 changelog is active with many fixes. Releases in 2026: 2.8.7 (Feb), 2.8.8 (Aug), 2.8.9 (Sep), 2.9.0 (Oct). Sources: [PyPI fpdf2](https://pypi.org/project/fpdf2/), [Releases](https://github.com/py-pdf/fpdf2/releases), [CHANGELOG](https://github.com/py-pdf/fpdf2/blob/master/CHANGELOG.md)
- **Wheel:** only `fpdf2-2.9.0-py3-none-any.whl`, so it is pure Python ([PyPI JSON](https://pypi.org/pypi/fpdf2/json)).
- **Dependencies:** `Pillow!=9.2.*,>=8.3.2` and `fonttools>=4.34.0`. HA's Pillow 13.0.0 satisfies the first. `fonttools` 4.68.0 ships `musllinux_1_2_x86_64` and `aarch64` wheels for cp311 to cp315, plus `py3-none-any` ([PyPI JSON fonttools](https://pypi.org/pypi/fonttools/json)).
- **Unicode, umlauts, €:**
  - Core fonts (Helvetica, Times, Courier, …) "only support latin characters" ([Unicode docs](https://py-pdf.github.io/fpdf2/Unicode.html)).
  - The code sets `self.core_fonts_encoding = "latin-1"`, and `normalize_text()` raises `FPDFUnicodeEncodingException` for characters it can't encode. The `set_font()` docstring says `core_fonts_encoding` can be switched to `cp1252` ([`fpdf/fpdf.py`](https://github.com/py-pdf/fpdf2/blob/master/fpdf/fpdf.py)).
  - **€ (U+20AC) is not in Latin-1**, so it fails with a core font on default settings.
  - With `add_font()` and a TTF file, fpdf2 handles full Unicode and embeds "only the subset of each font that is actually used" ([Unicode docs](https://py-pdf.github.io/fpdf2/Unicode.html)). Text shaping (uharfbuzz) is only needed for complex scripts, not for German.
- **Tables:** `pdf.table()` has existed since 2.7.0 ([Tables docs](https://py-pdf.github.io/fpdf2/Tables.html)). This fits Line Items per Run directly. It supports:
  - `col_widths` and per-column `text_align`
  - page breaks with repeated headings (since 2.7.9)
  - images in cells via `row.cell(img=...)`
- **Images:**
  - `image()` accepts a path, URL, `bytes`, `io.BytesIO` or `PIL.Image` (docstring in [`fpdf.py`](https://github.com/py-pdf/fpdf2/blob/master/fpdf/fpdf.py)).
  - JPEG and TIFF bytes are reused unchanged "when possible", and oversized images can optionally be downscaled with `oversized_images = "DOWNSCALE"` ([Images docs](https://py-pdf.github.io/fpdf2/Images.html)).
  - Loading a URL in `image()` would be blocking network I/O. Fetch images from HA asynchronously first and pass them as bytes.
- **Licence assessment:** fpdf2 is LGPL-3.0, but it is installed separately via pip and only imported, so the integration does not become LGPL. That would only change if fpdf2 were copied (vendored) into the repo. **Uncertainty:** this is my reading of the LGPL, not legal advice.

### 2.2 reportlab (technically equivalent alternative)
- **Version, licence:** 5.1.0, released 2026-10-22, "BSD license", `requires_python >=3.9,<4` ([PyPI](https://pypi.org/project/reportlab/)).
- **C extensions:**
  - The 4.0 release notes state the goal "increase portability by removing C dependencies or making them optional". The `_rl_accel` C module "is generally not necessary any more", and renderPM uses PyCairo ([What's new in 4.0](https://docs.reportlab.com/releases/notes/whats-new-40/)).
  - The release notes don't mention wheels, but **PyPI lists only `reportlab-5.1.0-py3-none-any.whl` for 5.1.0** ([PyPI JSON](https://pypi.org/pypi/reportlab/json)). No musllinux wheels are needed.
  - The accelerators come only through extras (`rl_accel`, `rlPyCairo`, `freetype-py`, `uharfbuzz`), and a Cost Statement doesn't need them.
- **Dependencies:** `pillow>=9.0.0` (present in HA) and `charset-normalizer` without a version bound. HA's constraint of `3.4.3` is compatible ([package_constraints.txt](https://github.com/home-assistant/core/blob/dev/homeassistant/package_constraints.txt)).
- **Unicode:** input must be UTF-8 or a Python `str`. The default encoding of the 14 standard fonts is WinAnsi. TrueType fonts are registered with `TTFont` and `pdfmetrics.registerFont`, and they "work in Unicode/UTF8" ([User Guide ch. 3 Fonts](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/)). **Uncertainty:** the page doesn't mention € explicitly. WinAnsiEncoding should include the euro sign per the PDF specification (Annex D), but I didn't check that against the spec here. With an embedded TTF the question doesn't arise.
- **Assessment:** Platypus (flowables, `Table`) is very capable and the output quality is high. The API is larger than fpdf2's, and parts of the documentation point to commercial products (rlextra). Pick reportlab if a permissive licence (BSD rather than LGPL) is preferred.

### 2.3 borb (not recommended)
- 3.0.9 (2026-08-03), `py3-none-any`, but **`AGPL-3.0-or-later`** ([PyPI JSON](https://pypi.org/pypi/borb/json)). Under the common reading, a publicly distributed integration that imports borb would have to be AGPL-compatible. For a public HACS repo that wants its own licence choice, that is an unnecessary risk. **Uncertainty:** whether importing creates a derivative work is disputed; not legal advice.

### 2.4 WeasyPrint (unsuitable)
- Version 70.0 has a `py3-none-any` wheel ([PyPI JSON](https://pypi.org/pypi/weasyprint/json)), but it calls the **Pango system library** through `cffi`.
- WeasyPrint 70.0 requires Pango ≥ 1.44.0. On Alpine it needs `so:libgobject-2.0.so.0 so:libpango-1.0.so.0` and more (libharfbuzz, libfontconfig, libpangoft2) ([First Steps](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)).
- `manifest.json` can only install Python packages, not `apk` packages ([manifest docs](https://contributors.home-assistant.io/core/integrations/manifest/)). Whether Pango is in the HA image is outside the integration's control and could change with any base image update.
- The same argument applies to other HTML-to-PDF approaches with native engines (wkhtmltopdf, Chromium/Playwright).

### 2.5 Others, briefly
- **xhtml2pdf** builds on reportlab and adds further dependencies. I see no benefit over using reportlab or fpdf2 directly (not examined in depth).
- **pypdf** manipulates existing PDFs and has no layout engine, so it doesn't fit.

### 2.6 Runtime notes for the backend
- PDF generation is CPU-bound and does I/O (reading the font file, decoding images). The HA docs say a blocking call in the event loop "stalls all of Home Assistant until it returns". The work belongs in `hass.async_add_executor_job`, including `open()` and any reads ([Blocking operations](https://contributors.home-assistant.io/core/internals/blocking-operations/)).
- Importing `fpdf` at module level is fine: the same page says HA performs module-level imports before the event loop starts.

---

## 3. Browser options (panel)

| | jsPDF + jspdf-autotable | pdfmake | `window.print()` + print CSS |
|---|---|---|---|
| Version | jsPDF 4.2.1 (2026-03-17), autotable 5.0.9 (2026-10-15) | 0.3.14 (2026-11-08) | Browser API |
| Licence | MIT / MIT | MIT | – |
| Size (min + gzip, measured from jsDelivr) | `jspdf.umd.min.js` ~130 KB, autotable ~10 KB | `pdfmake.min.js` ~296 KB **+ `vfs_fonts.js` ~468 KB** | 0 |
| Unicode / € | Standard fonts are "limited to the ASCII-codepage" per README; a TTF via `addFileToVFS`/`addFont` is needed | Roboto by default; custom fonts via VFS or URL | Browser fonts, works |
| Images | `addImage` (data URL or bytes) | JPEG/PNG as data URI or URL, **including custom headers** | `<img>` |
| Tables | autotable plugin | built in | HTML tables |
| Deterministic output | high | high | low (depends on browser, print dialog, margins) |

Sources:
- npm registry: [jspdf](https://www.npmjs.com/package/jspdf), [jspdf-autotable](https://www.npmjs.com/package/jspdf-autotable), [pdfmake](https://www.npmjs.com/package/pdfmake)
- Bundle sizes: measured from `cdn.jsdelivr.net/npm/<pkg>/dist|build/*.min.js` with `gzip -c` on 2026-11-19. Bundlephobia reports similar gzipped sizes: jspdf 129.8 KB, autotable 9.7 KB, pdfmake 287.7 KB.
- jsPDF: [README "Use of Unicode Characters / UTF-8"](https://github.com/parallax/jsPDF#use-of-unicode-characters--utf-8), [Releases](https://github.com/parallax/jsPDF/releases)
- pdfmake: [Custom fonts (client-side)](https://pdfmake.github.io/docs/0.3/fonts/custom-fonts-client-side/), [Images](https://pdfmake.github.io/docs/0.3/document-definition-object/images/)

Notes:
- **jsPDF 4.0.0** (2026-01-03) fixed a critical path traversal vulnerability in the Node.js build only ([release v4.0.0](https://github.com/parallax/jsPDF/releases/tag/v4.0.0)). It doesn't affect browser use, but it shows the project is maintained.
- **Font weight in the client:** for € and umlauts, jsPDF needs a TTF either bundled into the panel or loaded at runtime. **Uncertainty:** I did not verify from primary sources whether jsPDF embeds TTF fonts as a subset or in full. If it embeds the full font, every PDF grows by the font's size.
- **Images in the browser** (camera snapshots, thumbnails) need authenticated requests to HA, e.g. `/api/camera_proxy/...`.
  - pdfmake explicitly supports image URLs with custom headers ([Images](https://pdfmake.github.io/docs/0.3/document-definition-object/images/)).
  - With jsPDF you must `fetch` the image with the token and convert it to a data URL yourself.
  - Server-side generation avoids this step entirely.
- **`window.print()`:**
  - Android WebView does not implement `window.print`, according to a Cordova PR that cites Chromium issue 322303 ([Cordova PR](https://www.mail-archive.com/issues@cordova.apache.org/msg123247.html), [Chromium issue thread](https://groups.google.com/a/chromium.org/g/chromium-bugs/c/yHP04n0qBbA)).
  - A GitHub code search in `home-assistant/android` found neither `PrintManager` nor `createPrintDocumentAdapter`, so `window.print()` is very likely a no-op in the Companion app. **Uncertainty:** not tested on a device; iOS WKWebView not checked.
  - The panel would also have to hide the HA sidebar and header with print CSS, or print a separate window or iframe.
  - The user must pick "Save as PDF" in the print dialog, so it isn't a one-click PDF.

---

## 4. Delivering the file to the user

### 4.1 Backend PDF through an authenticated HTTP view (recommended)
- `HomeAssistantView` has `requires_auth = True` by default ([`homeassistant/helpers/http.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/http.py)). The view returns an aiohttp `Response` with `Content-Type: application/pdf` and `Content-Disposition: attachment; filename=...`. HA serves backups the same way (`DownloadBackupView`, `/api/backup/download/{backup_id}`; [`components/backup/http.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/components/backup/http.py)).
- **The catch:** a plain browser download through `<a href>` sends no bearer token. HA solves this with **signed paths**:
  - The WebSocket command `auth/sign_path` (parameter `path`, optional `expires`, default 30 s) returns a URL carrying an `authSig` JWT ([`components/auth/__init__.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/components/auth/__init__.py)).
  - The auth middleware accepts signed requests **only for `GET`/`HEAD`**.
  - The path and all query parameters except `height`/`width` are part of the signature and must match exactly ([`components/http/auth.py`](https://github.com/home-assistant/core/blob/dev/homeassistant/components/http/auth.py)).
- The HA frontend uses exactly this pattern: `getSignedPath(hass, url)` followed by `fileDownload(signedUrl.path)`, which clicks a hidden `<a download>` ([`download_backup.ts`](https://github.com/home-assistant/frontend/blob/dev/src/panels/config/backup/helper/download_backup.ts), [`src/data/auth.ts`](https://github.com/home-assistant/frontend/blob/dev/src/data/auth.ts), [`src/util/file_download.ts`](https://github.com/home-assistant/frontend/blob/dev/src/util/file_download.ts)).
- **For WattBill:** the selected Runs must reach the server in one of two ways:
  1. In the GET query, where they become part of the signature (e.g. `?runs=1,2,3`).
  2. Stored server-side first: a "create Cost Statement" WebSocket command returns an ID, followed by GET `/api/wattbill/statement/{id}`. This keeps the URL short and avoids long query strings.

### 4.2 Blob in the browser
- How it works:
  1. `fetch` with `Authorization: Bearer <hass.auth.data.access_token>`, or use `hass.fetchWithAuth`.
  2. `URL.createObjectURL(blob)`.
  3. `fileDownload(blobUrl)`.
- This also allows `POST` with a JSON body. The HA frontend's `fileDownload` handles `blob:` URLs explicitly, including a delayed revoke for Android ([`file_download.ts`](https://github.com/home-assistant/frontend/blob/dev/src/util/file_download.ts)). The client-side libraries use the same mechanism (jsPDF `doc.output("blob")`, pdfmake `getBlob`).
- The Android Companion app handles three URL schemes ([`FrontendDownloadManager.kt`](https://github.com/home-assistant/android/blob/main/app/src/main/kotlin/io/homeassistant/companion/android/frontend/download/FrontendDownloadManager.kt)):
  - `blob:` URLs are read back into the app as a data URI via injected JavaScript.
  - `http/https` URLs go through the system DownloadManager with auth headers and cookies.
  - `data:` URLs are saved directly.

  **Uncertainty:** the iOS Companion app was not checked.

---

## 5. Comparison matrix

| Criterion | fpdf2 | reportlab | borb | WeasyPrint | jsPDF+autotable | pdfmake | window.print |
|---|---|---|---|---|---|---|---|
| Install risk on HA OS | very low (pure, Pillow in HA, fonttools wheels) | very low (pure, Pillow in HA) | low | **high** (Pango) | none (bundled) | none (bundled) | none |
| Shipped by HA core | no (Pillow yes) | no | no | no | – | – | – |
| €/umlauts | fine with TTF; Latin-1 core font fails on € | fine with TTF | – | yes | TTF needed | Roboto default | yes |
| Images | JPEG passthrough, PIL, bytes | yes (Pillow) | yes | yes | yes | JPEG/PNG, URL+headers | yes |
| Output quality | good | very good | good | very good (CSS) | good | good | variable |
| Bundle / footprint | Python package only | Python package only | – | system libs | ~140 KB gz | ~760 KB gz incl. fonts | 0 |
| Licence | LGPL-3.0 | BSD | **AGPL-3.0+** | BSD | MIT | MIT | – |
| Maintenance 2026 | active (2.9.0 Oct) | active (5.1.0 Oct) | active (Aug) | active | active (4.2.1 Mar) | active (0.3.14 Nov) | – |
| Testable with pytest | yes | yes | yes | yes | JS tests only | JS tests only | barely |

Licences and release dates come from PyPI and npm metadata (see above). **Uncertainty:** WeasyPrint's PyPI JSON licence field is empty; "BSD" comes from prior knowledge and was not verified here.

## 6. Open points to verify while prototyping
1. Smoke-test `fpdf2==2.9.0` in a `ghcr.io/home-assistant/home-assistant` container on both aarch64 and amd64 to confirm that uv picks the musllinux wheel for fonttools. PyPI suggests it will.
2. Choose the font and ship its licence file in the repo, e.g. Noto Sans (OFL-1.1) or DejaVu Sans. The font licences were not checked here.
3. Measure Cost Statement size with many Runs and camera snapshots, and test `oversized_images = "DOWNSCALE"`.
4. Check download behaviour in the iOS Companion app.
