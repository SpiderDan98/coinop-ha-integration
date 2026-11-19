# The Cost Statement PDF is rendered in the backend with fpdf2

The Cost Statement is laid out in Python with fpdf2 (`requirements: ["fpdf2==2.9.0"]`), in Noto Sans, which ships in the package with its OFL licence. Rendering runs in the executor on copies of the Runs. The panel never builds the PDF. It asks `wattbill/cost_statement/create` for an export and gets a short-lived signed path back. The browser downloads that path with a plain link from an admin-only view, which renders the PDF from the Runs' current values. The PDF is never stored.

## Why

- fpdf2 is a pure-Python wheel. Its only dependencies are Pillow, which Home Assistant ships, and fontTools, which has musllinux wheels, so it installs on HA OS. reportlab would work just as well; WeasyPrint needs system libraries an integration can't install; borb is AGPL.
- Its tables repeat their headings on a page break, and it embeds TTF fonts as subsets, so umlauts and € work. fpdf2's built-in fonts are Latin-1 and can't print €.
- One renderer in the backend reads the same rounded amounts as the websocket API. A client-side library (jsPDF, pdfmake) would add 140–760 KB to the panel and need its own fonts and authenticated image fetches (#45). `window.print()` does nothing in the Android Companion app.
- A signed path is how Home Assistant's own frontend downloads backups. A plain link sends no auth header. The panel clicks the link the way HA's `fileDownload` does (`download` and `target="_blank"`): the Android Companion app hands `https:` downloads to the system download manager, which fetches the path again; the iOS app downloads it (iOS 17+) or opens it in the browser. The signed path therefore stays valid for several fetches, not one.
- Backend tests can read the PDF's text (pypdf, test-only) and assert on what the recipient sees.

## Consequences

- The export only keeps the Run ids and options in memory, for as long as the signature is valid (five minutes). After a restart or reload, the user exports again.
- The PDF has its own en/de strings (`statement/strings/`) and formats numbers and dates itself, since the backend has no locale library. `tests/test_panel_translations.py` keeps the terms it shares with the panel in step.
- fpdf2 is LGPL-3.0. It is installed by pip and imported, never vendored, so the integration's licence is unaffected.
