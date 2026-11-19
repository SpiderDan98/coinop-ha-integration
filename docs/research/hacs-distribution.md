# Distributing a custom integration via HACS and the core Marketplace

Research for issue #19 ("What does HACS distribution require, and how does the core marketplace integration change it?").
Research date: 2026-11-19. Sources were read directly from primary repos at these commits:

- `home-assistant/core` `dev` @ [`0ed1ff9`](https://github.com/home-assistant/core/tree/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b) (abbreviated below as **core**). Latest stable release on the research date: **2026.11.2** (2026-11-16); `dev` is 2026.12.0.dev0.
- `home-assistant/contributors.home-assistant.io` `main` @ [`fd27596`](https://github.com/home-assistant/contributors.home-assistant.io/tree/fd27596edec6e32543635e8cea91688ea540bad9) (abbreviated as **contrib**). This is the successor of `developers.home-assistant`, which is archived as of 2026-10-16 @ [`50b5188`](https://github.com/home-assistant/developers.home-assistant/tree/50b518898989b67bb76b69827f227aa6f0acd32a) (abbreviated as **devdocs**).
- `hacs/documentation` `main` @ [`4f06a5b`](https://github.com/hacs/documentation/tree/4f06a5bd11088a21a453fdcb3eda1603353e6c8a) (the source of hacs.xyz, abbreviated as **hacsdocs**).
- `home-assistant/frontend` `dev` @ [`16103b7`](https://github.com/home-assistant/frontend/tree/16103b77595f43bc34c5ff9be876f83fba5db3f9), plus `hacs/default`, `hacs/action`, `home-assistant/actions` and the reference integrations' default branches as of the research date.

## Summary

- **The `marketplace` integration is real and shipped.** It is HACS moved into core, added in [core PR #183502](https://github.com/home-assistant/core/pull/183502) (merged 2026-10-01) and released in **HA 2026.11.0** (2026-11-04). It is a system integration that is set up by default, and its panel lives under Settings > Marketplace. **It replaces HACS** on 2026.11+: the loader blocks the `hacs` custom integration, migrates its config entry, storage, update entities and custom repositories, and deletes its files. HACS on 2026.10 and older keeps working but gets no new features.
- **The publishing contract did not change.** The Marketplace reads the **same catalog** (`hacs/default`, served from `data-v2.hacs.xyz`), the **same `hacs.json`**, and the **same repository layout**. Getting into the catalog is still a PR to `hacs/default`, and the HACS team still reviews it. One repository that meets the HACS rules serves both HACS users (HA ≤ 2026.10) and Marketplace users (HA ≥ 2026.11). Nothing extra is needed to "support the Marketplace". It is stricter at install time, though: `manifest.json` needs a loadable `version`, the domain must be a slug, and `hacs.json` must exist at the installed ref.
- **Repository layout:** one integration per repository, under `custom_components/wattbill/` (everything the integration needs lives in that folder), with `hacs.json` and `README.md` at the repository root. Brand images go in `custom_components/wattbill/brand/` (HA ≥ 2026.3; the Marketplace shows them before install). Translations go in `custom_components/wattbill/translations/<lang>.json` with a complete `en.json`.
- **`hacs.json`:** `name` is required. `homeassistant` sets the minimum HA version and is enforced at install, but only for repositories with releases. `zip_release` + `filename` install from a release asset, and `persistent_directory` keeps a folder across updates. `country` and `hacs` are ignored by the Marketplace.
- **`manifest.json`:** `domain`, `name`, `version`, `documentation`, `issue_tracker` and `codeowners` are required for the catalog. Other keys used here: `config_flow`, `integration_type`, `iot_class`, `dependencies` (`frontend`, `http`, `panel_custom`, `websocket_api`), `requirements`, and the new optional `categories` (one to three; the HACS action warns when it is missing). There is **no minimum-HA key in the manifest**; `hacs.json` `homeassistant` is the only declarative mechanism.
- **Releases:** the version is the tag of the latest **published GitHub release** (a tag alone is not enough). `manifest.json` `version` should equal the tag. The catalog regenerates every 4 h and the Marketplace polls it every 6 h, so a release takes several hours to reach users. The update entity shows the release body as release notes.
- **Validation:** two GitHub Actions on push, PR and nightly: `hacs/action@main` with `category: integration`, and `home-assistant/actions/hassfest@master`. Both must pass, with no ignored checks, before a `hacs/default` PR. The review queue has **409 open non-draft PRs** and takes "months".
- **Restarts (2026.11+):** the first install of a config-flow integration loads without a restart, and the Marketplace invalidates the translation cache for the domain. Updates and removals of an integration that is already loaded still need a restart; the Marketplace raises a repair with a restart button.
- **Translations:** custom integrations do not use `strings.json` and are not on Lokalise. Ship finished `translations/en.json` + `de.json` with no `[%key:...%]` references. hassfest validates only `en.json`. Subentry flows go under `config_subentries.<type>` and need `entry_type` + `initiate_flow.user`. For **panel strings**, the backend translation category `config_panel` (used by KNX and ZHA) is accepted by hassfest for any integration and can be loaded in the panel via `hass.loadBackendTranslation("config_panel", "wattbill")`. Using it for a non-config sidebar panel is an inference, not a documented pattern.
- **Minimum-version window:** among 13 well-maintained HACS integrations, `hacs.json` `homeassistant` lags current stable (2026.11) by between **1 and 31 months**, with a **median of about 8 months**. Actively developed ones (Battery Notes, Spook, Alarmo, Powercalc, Frigate) sit at **2 to 8 months**. Core deprecates APIs used by custom integrations for 12 months.
- **Frontend bundle:** commit the built JS inside `custom_components/wattbill/` (e.g. `frontend/wattbill-panel.js`), or ship it with `zip_release`. Catalog installs come from the repository archive or release asset at that tag, so nothing outside the integration folder reaches the user. A frontend panel cannot be a separate "dashboard" (`plugin`) repository, because each repository has exactly one category. Limit: 100 MiB / 50,000 files per download.
- **pip requirement (fpdf2):** `fpdf2` (latest 2.9.0, requires Pillow and fonttools) is not a dependency of HA. Pin it (`fpdf2==2.9.0`). Do **not** list Pillow: hassfest now rejects custom requirements that HA itself depends on, conflict with HA's pins/constraints, or exactly pin a package HA ships. HA installs requirements with `uv pip install --constraint package_constraints.txt` at integration load time, and core constrains `Pillow==13.0.0`, which fpdf2 (`Pillow>=8.3.2,!=9.2.*`) accepts.

---

## 1. The core Marketplace integration

### 1.1 What it is

- [core PR #183502](https://github.com/home-assistant/core/pull/183502) "Add Marketplace integration" by frenck was merged 2026-10-01. Its description: "This brings HACS into Home Assistant as the Marketplace … The goal of this move is to get HACS into Home Assistant with the least effort possible, and as much as possible as it is … There are many ideas to evolve the Marketplace into something bigger. Those are out of scope for this PR and come later."
- The component is not in the `2026.10.0` tag but is in `2026.11.0` (checked via the GitHub contents API). The [2026.11 release post](https://www.home-assistant.io/blog/2026/11/04/release-202611/) announces it as "Marketplace (HACS)": installs skip the restart, updates still need one, there is a risk notice, brand images show before install, custom repositories need a GitHub device-flow connection, and "The HACS installer stops at Home Assistant 2026.11".
- Manifest: `domain: marketplace`, `integration_type: system`, `single_config_entry`, `dependencies: [frontend, http, lovelace, repairs, websocket_api]`, `requirements: [aiogithubapi==26.0.0]` ([core `marketplace/manifest.json`](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/manifest.json)).
- Constants: `CATALOG_REPOSITORY = "hacs/default"` and `LEGACY_HACS_INTEGRATION_REPOSITORY = "hacs/integration"`, commented "The catalog the Marketplace consumes, and the repository of the integration it replaces". Installed dashboard resources move from `/hacsfiles` to `/local/community`, and `MAX_DOWNLOAD_SIZE = 100 MiB`, `MAX_ARCHIVE_MEMBERS = 50_000` ([core `marketplace/const.py`](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/const.py)).
- Setup: `async_setup` registers a hidden admin-only panel, redirects `/hacs` to `/marketplace`, and starts a system flow when no `marketplace` or `hacs` entry exists ([core `marketplace/__init__.py` L89-121](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/__init__.py#L89-L121)). `async_setup_entry` adopts the legacy HACS install and removes legacy files outside safe and recovery mode (L182-200).
- The loader blocks the HACS custom integration: `"hacs": BlockedIntegration(None, "is now built into Home Assistant as the Marketplace", replaced_by="marketplace")`, commented "Added in 2026.11.0 because HACS ships with Home Assistant now". `MIGRATED_CUSTOM_INTEGRATIONS` rewrites its config entries to the built-in domain ([core `loader.py` L177-191](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/loader.py#L177-L191)).
- HACS's own docs confirm the split: "Starting with Home Assistant 2026.11, HACS ships with Home Assistant itself, as the **Marketplace** integration … the same catalog, the same repositories, and the same `hacs.json`. Development continues in Home Assistant, so HACS itself, the custom integration, doesn't get new features anymore." Publishers are pointed to the contributors site, and "Getting into the catalog still works the same, through hacs/default" ([hacsdocs `marketplace.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/marketplace.md)). The `hacs/integration` repository is not archived; its last release is 2.0.5 (2025-01-28).

### 1.2 Does it replace, complement or affect HACS?

- **Replaces** HACS for users on HA ≥ 2026.11. HACS cannot be installed there, and the Marketplace takes over its data on first start ([hacsdocs `marketplace.md`, "Upgrading to Home Assistant 2026.11"](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/marketplace.md)).
- **Shares infrastructure** with HACS: the catalog (`hacs/default`, `data-v2.hacs.xyz`), the review process, and the HACS action stay with the HACS team ([contrib `marketplace/how-it-works.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/how-it-works.md)): "For you as a publisher, little changes. The catalog, `hacs.json`, the folder structure, and the HACS action are the same."
- **Narrows types:** AppDaemon apps and Python scripts are no longer managed. Integrations, dashboards (`plugin`), themes and templates remain (same source).
- **Links:** My links of type `hacs_repository` still work and open the Marketplace; the new type is `marketplace_repository` (same source; [contrib `marketplace/guides/catalog.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/guides/catalog.md)).

### 1.3 What the Marketplace checks at install time

From [contrib `marketplace/reference/validation.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/reference/validation.md), confirmed in core source:

- `hacs.json` must be present. It is fetched as a raw file from the repository at the ref being installed, not from inside a ZIP asset ([core `repositories/base.py` L1965-1979](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/base.py#L1965-L1979)). It therefore has to exist at the tagged commit.
- Minimum HA version: `_check_minimum_version` refuses a ref whose `hacs.json` `homeassistant` is newer than the running HA ([L2055-2067](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/base.py#L2055-L2067)). `can_install` skips this check when the repository has no releases ([L587-594](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/base.py#L587-L594)).
- Loadable manifest, checked after the files are written: the `domain` must match and `version` must parse under the CalVer/SemVer/SimpleVer/BuildVer/PEP 440 strategies the loader accepts. Otherwise the files are restored ([core `repositories/integration.py` L75-124](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/integration.py#L75-L124)).
- The domain must match `^[a-z0-9_-]+$`. No other installed repository may own the same domain, and a core domain needs explicit user confirmation (same file L45-58, L170-189, L233-241; [`utils/validate.py` L28-30](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/utils/validate.py#L28-L30)).
- Downloads and unpacked ZIPs are capped at 100 MiB and 50,000 members (`const.py`).

### 1.4 Restart-free first install

- `async_post_installation` clears the loader's custom-component cache, mounts `custom_components` if needed, and calls `async_invalidate_translations` for the domain. A restart repair is created only if the domain was already loaded or the scan did not find it ([core `repositories/integration.py` L191-216, L404-421](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/integration.py#L191-L216)).
- Consequence for WattBill: after a first install, `async_setup_entry` runs in a process that has not been restarted. The panel's static path and websocket commands register as usual, but the guard-on-reload advice from `docs/research/ha-custom-panel.md` §1.2 matters more here.

## 2. HACS / catalog publishing requirements (valid for both HACS and the Marketplace)

### 2.1 Repository layout

- One integration per repository. All files live in `custom_components/<domain>/`, and only the first subfolder is used. Alternatively, `content_in_root: true` puts the integration in the repository root ([hacsdocs `publish/integration.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/integration.md); [contrib `marketplace/reference/repository-structure.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/reference/repository-structure.md)).
- Recommended tree ([contrib `marketplace/guides/integrations.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/guides/integrations.md)):

  ```text
  custom_components/my_integration/__init__.py
  custom_components/my_integration/manifest.json
  custom_components/my_integration/translations/en.json
  custom_components/my_integration/brand/icon.png
  hacs.json
  README.md
  ```

- General repository requirements: public GitHub repository, a repository description, topics, issues enabled, a README ([hacsdocs `publish/start.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/start.md)). The catalog review also checks for an OSI-approved license that GitHub can identify (`NOASSERTION` and non-commercial licenses fail) ([hacsdocs `publish/include.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/include.md)).
- Updates replace the whole integration folder. Use `persistent_directory` for user files kept there (contrib integrations guide). This does not affect WattBill, whose data lives in `.storage/` and `/config/wattbill/`.

### 2.2 `hacs.json`

Keys the Marketplace reads, with type coercion for legacy string booleans ([core `utils/validate.py` L89-100](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/utils/validate.py#L89-L100); [core `repositories/base.py` L380-392](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/base.py#L380-L392); [contrib `marketplace/reference/hacs-json.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/reference/hacs-json.md)):

| Key | Meaning | Marketplace |
| --- | --- | --- |
| `name` | Display name; required by the catalog | used |
| `content_in_root` | Integration in the repository root | used |
| `zip_release` + `filename` | Install from the named ZIP release asset (integrations) | used |
| `homeassistant` | Minimum HA version; `b0` suffix also allows betas (e.g. `"2026.11.0b0"`) | enforced, releases only |
| `hide_default_branch` | Don't offer the default branch | used |
| `persistent_directory` | Subfolder kept across updates (integrations) | used |
| `hacs` | Minimum HACS version | read, not compared |
| `country` | ISO country codes; requested by the catalog for country-specific repositories | ignored |

Unknown keys are ignored, and a wrong-typed value is dropped with a warning. Versions are compared with AwesomeVersion.

### 2.3 `manifest.json`

- Catalog-required keys: `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version` ([hacsdocs `publish/integration.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/integration.md)).
- The hassfest custom-integration schema extends the core schema with `version`, `issue_tracker` and `import_executor`, and requires a non-core `documentation` URL. hassfest errors with "No 'version' key in the manifest file" when `version` is missing ([core `script/hassfest/manifest.py` L388-406](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/script/hassfest/manifest.py#L388-L406)). The base schema also has `categories` (one to three, `category` or `category.subcategory`) and `connectivity` (L224-366).
- `categories` is optional for custom integrations. hassfest only warns on an unknown category, the HACS action warns when the key is missing and fails on an unknown category, and the catalog publishes the categories, which the Marketplace will browse by later ([contrib blog 2026-10-20 "Integrations have categories now"](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/blog/2026-10-20-integration-categories.md)). The category list is in [core `generated/integration_categories.json`](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/generated/integration_categories.json). Plausible fits for WattBill are `energy.meters_monitoring` and `computers_network.printers` (the latter's description includes "3D printers"). The choice is open.
- There is **no manifest key for a minimum HA version**. The loader's `Manifest` TypedDict has `version` and `requirements` but nothing like `homeassistant` ([core `loader.py` ~L297-335](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/loader.py#L297-L335)). A manual install on an older HA is therefore not stopped. An integration can check `homeassistant.const.__version__` itself if it wants a hard stop.

### 2.4 Brand images

- Since HA 2026.3, a custom integration can ship `custom_components/<domain>/brand/` with `icon.png`, `dark_icon.png`, `logo.png`, `dark_logo.png` and the `@2x` variants. Local images take precedence over the brands CDN, and all brand images are served via the authenticated `/api/brands/integration/{domain}/{image}` ([devdocs blog 2026-02-24](https://github.com/home-assistant/developers.home-assistant/blob/50b518898989b67bb76b69827f227aa6f0acd32a/blog/2026-02-24-brands-proxy-api.md); [devdocs `core/integration/brand_images.md`](https://github.com/home-assistant/developers.home-assistant/blob/50b518898989b67bb76b69827f227aa6f0acd32a/docs/core/integration/brand_images.md)).
- The catalog "Brands" check requires a `brand` folder with at least `icon.png`, **or** an entry in `home-assistant/brands` ([hacsdocs `publish/include.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/include.md)). The Marketplace shows brand images before install, picked up "from the latest release of every integration in the catalog". Don't use HA-branded images (contrib integrations guide).
- On HA < 2026.3 a local `brand/` folder is not used, so the integration shows a placeholder unless it is also in `home-assistant/brands`. That matters only if WattBill supports versions older than 2026.3.

### 2.5 GitHub releases and versions

- The version is the tag of the latest **published release**; tags alone are not enough. Without releases, users get the default branch's latest commit hash ([hacsdocs `publish/start.md` "Versions"](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/start.md); [contrib `marketplace/guides/releases.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/guides/releases.md)).
- The contrib releases guide adds:
  - `manifest.json` `version` must match the tag.
  - The release body becomes the update entity's release notes.
  - Delivery: the catalog regenerates every 4 h and the Marketplace reads it every 6 h. Custom (non-catalog) repositories update via the GitHub API every 48 h, and only with a GitHub connection.
  - Pre-releases are offered only to users who enable the per-repository pre-release switch, and only while newer than the latest regular release.
  - Users on an older HA than `homeassistant` are offered earlier compatible releases instead.
  - Keep old releases so users can roll back.
- A catalog version installs straight from the repository archive or release asset, without the GitHub API ([contrib `marketplace/how-it-works.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/how-it-works.md)).

### 2.6 Validation actions

- **HACS action** (`.github/workflows/validate.yaml`), from [hacsdocs `publish/action.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/action.md):

  ```yaml
  on:
    push:
    pull_request:
    schedule:
      - cron: "0 0 * * *"
    workflow_dispatch:
  permissions: {}
  jobs:
    validate-hacs:
      runs-on: ubuntu-latest
      steps:
        - uses: hacs/action@main
          with:
            category: integration
  ```

  - Checks you can skip with `ignore`: `archived`, `brands`, `description`, `hacsjson`, `images`, `information`, `issues`, `license`, `topics`, plus `integration_categories` per the contrib validation reference.
  - The catalog accepts no ignores.
  - `hacs/action` last changed 2026-06-08.
- **hassfest** (`home-assistant/actions/hassfest@master`, after `actions/checkout`). It runs the `ghcr.io/home-assistant/hassfest` image ([home-assistant/actions `hassfest/action.yml`](https://github.com/home-assistant/actions/blob/master/hassfest/action.yml)). For a single custom integration it runs the `INTEGRATION_PLUGINS` set: manifest, translations, config_flow, requirements, services, icons, brand_images and others ([core `script/hassfest/plugins.py` L8-61](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/script/hassfest/plugins.py#L8-L61)). I did not read the rules of the `brand_images` and `json` plugins, which are loaded from an external `hassfest` package, not from core's `script/hassfest/`.

### 2.7 Default-repository (catalog) inclusion

From [hacsdocs `publish/include.md`](https://github.com/hacs/documentation/blob/4f06a5bd11088a21a453fdcb3eda1603353e6c8a/source/docs/publish/include.md) and [contrib `marketplace/guides/catalog.md`](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/marketplace/guides/catalog.md):

- **Who can submit:** only the repository owner or a major contributor. Integrations that override a core domain, or that only test a core alpha or beta, are not accepted.
- **Before the PR:** HACS action and hassfest pass, and a full GitHub release exists.
- **The PR:**
  - Add `owner/repo` alphabetically to the JSON list `integration` in [`hacs/default`](https://github.com/hacs/default) (branch `master`).
  - Open it from a personal account (not an organization) on a fresh branch.
  - Fill the template completely, with links to the latest release and to passing HACS and hassfest runs.
- **Automated review checks:** brands, core domain conflict (including the next release), manifest, HACS validation, `hacs.json` name, not archived, releases, owner, license, repository (description, issues, topics), and JSON lint/sort.
- **Timeline:** "new additions still take months to be reviewed". On the research date the backlog was 409 open non-draft PRs (GitHub search `repo:hacs/default is:pr is:open draft:false`). The last merged addition was on 2026-11-17.
- **Until then:** users can add the repository as a custom repository from a My link. On the Marketplace this needs a GitHub connection.
- **Removal:** archiving removes the repository from the catalog. Critical (harmful) repositories are uninstalled from every instance.

## 3. Translations

- Custom integrations don't use `strings.json` and aren't on Lokalise. Ship `translations/<BCP47>.json` with a complete `en.json` (the fallback). **References (`[%key:...%]`) don't work**: users would see the raw text, so write every string out. Placeholders work ([contrib `core/integrations/translations.md` "Custom integrations"](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/core/integrations/translations.md)).
- hassfest validates `translations/en.json` of a custom integration against the same schema as `strings.json`. Other languages are not validated ([core `script/hassfest/translations.py` L764-778](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/script/hassfest/translations.py#L764-L778)).
- **Categories:** `config`, `options` and `config_subentries` share one flow format (`step.<id>.title/description/data/data_description/sections/menu_options/menu_option_descriptions/submit`, `error`, `abort`, `progress`, `create_entry`, `initiate_flow`). Further categories include `entity`, `exceptions`, `issues`, `services`, `selector`, `device`, `system_health`, and `config_panel` "for integrations that bring their own configuration panel, like ZHA and KNX". Leave `title` out for a brand name (same contrib page).
- **Config subentries:** `config_subentries.<subentry_type>` with `entry_type` (what one subentry is called, e.g. "Device") and `initiate_flow.user` (required) / `initiate_flow.reconfigure` (optional), plus the usual `step`/`error`/`abort` ([contrib `core/integrations/subentries.md` "Texts and translations"](https://github.com/home-assistant/contributors.home-assistant.io/blob/fd27596edec6e32543635e8cea91688ea540bad9/src/content/docs/core/integrations/subentries.md)).
- **Frontend panel strings:** there are two options.
  1. Bundle the strings into the panel JS and pick them by `hass.language`. This is self-contained and needs no backend.
  2. Put them under `config_panel` in `translations/*.json` and load them in the panel with `hass.loadBackendTranslation("config_panel", "wattbill")`, which returns a `LocalizeFunc`.
     - `hass.loadBackendTranslation` and `TranslationCategory` (which includes `config_panel`) are in [frontend `src/types.ts` L244-248](https://github.com/home-assistant/frontend/blob/16103b77595f43bc34c5ff9be876f83fba5db3f9/src/types.ts#L244-L248) and [`src/data/translation.ts` L60-79](https://github.com/home-assistant/frontend/blob/16103b77595f43bc34c5ff9be876f83fba5db3f9/src/data/translation.ts#L60-L79).
     - The backend `frontend/get_translations` command accepts any category string ([core `frontend/__init__.py` L808-831](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/frontend/__init__.py#L808-L831)).
     - hassfest's schema accepts nested `config_panel` keys (`[a-z0-9-_]+`) for any integration ([`translations.py` L596-600](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/script/hassfest/translations.py#L596-L600)).
     - KNX uses it for its whole panel (`config_panel` with `dashboard`, `dialogs`, `entities`, …), and ZHA for its options.
     - The same strings could be read in Python for the Cost Statement via `homeassistant.helpers.translation.async_get_translations(hass, language, "config_panel", ["wattbill"])`.
     - **Inference:** using `config_panel` for a sidebar panel that isn't a config panel is not documented for custom integrations. It works mechanically but is undocumented API.
  - `hass.localize` alone covers only the frontend's own strings.

## 4. Minimum HA version

- **How to declare it:** `hacs.json` `homeassistant`, per release (§2.2, §2.5). HACS and the Marketplace then offer older compatible releases to older HA installs. There is no manifest key for this.
- **Policy context:** changes to what custom integrations use from core are "deprecated for 12 months first, and announced on the blog". Test against the beta, and bump `homeassistant` when a release needs newer HA (contrib integrations guide).
- **Survey:** `hacs.json` `homeassistant` on the default branch of well-maintained HACS integrations, against stable 2026.11:

| Repository | `homeassistant` | Lag | Latest release |
| --- | --- | --- | --- |
| thomasloven/hass-browser_mod | 2026.10.0.dev0 | 1 mo | v3.4.2 (2026-11-10) |
| andrew-codechimp/HA-Battery-Notes | 2026.9.0 | 2 mo | 3.8.1 (2026-10-30) |
| frenck/spook | 2026.8.0 | 3 mo | v5.11.1 (2026-10-14) |
| nielsfaber/alarmo | 2026.5.0 | 6 mo | v1.10.19 (2026-08-09) |
| bramstroker/homeassistant-powercalc | 2026.4.0 | 7 mo | v1.27.0 (2026-11-06) |
| blakeblackshear/frigate-hass-integration | 2026.3.0 | 8 mo | v5.15.7 (2026-11-16) |
| BottlecapDave/HomeAssistant-OctopusEnergy | 2025.11.0 | 12 mo | v19.3.0 (2026-11-02) |
| basnijholt/adaptive-lighting | 2025.9.0 | 14 mo | v1.32.0 (2026-09-06) |
| custom-components/alexa_media_player | 2025.2.0 | 21 mo | v5.21.0 (2026-11-15) |
| dummylabs/thewatchman | 2025.2.0 | 21 mo | v0.8.4 (2026-02-14) |
| jjjonesjr33/petlibro | 2025.1.0 | 22 mo | v1.4 (2026-11-05) |
| nielsfaber/scheduler-component | 2024.11.0 | 24 mo | v3.3.9 (2026-11-01) |
| mampfes/hacs_waste_collection_schedule | 2024.4.0 | 31 mo | v2.36.0 (2026-10-25) |

  The median lag is about 8 months. Integrations that track core APIs closely sit at 1 to 8 months, and several long-lived ones keep 1 to 2 years. The value often reflects the newest feature used, not a deliberate support window. The survey reads default branches via the GitHub API and is not exhaustive.
- **Version floors relevant to WattBill** (from this research and the map):
  - Config subentries need ≥ 2025.3, and the hub-to-subentry chaining needs ≥ 2026.5 (issue #17).
  - Local `brand/` images need ≥ 2026.3; older versions show a placeholder unless the integration is also in `home-assistant/brands`.
  - Restart-free first install via the Marketplace needs ≥ 2026.11; HACS is used on ≤ 2026.10.
  - `probatio` replaced voluptuous in 2026.9, but `import voluptuous as vol` keeps working via a `sys.modules` alias, so this sets no floor ([devdocs blog 2026-09-30](https://github.com/home-assistant/developers.home-assistant/blob/50b518898989b67bb76b69827f227aa6f0acd32a/blog/2026-09-30-probatio-validation-engine.md)). This resolves the open `probatio` question from issue #3.

## 5. Shipping the panel JS bundle and fpdf2

### 5.1 Frontend bundle

- Only `custom_components/wattbill/` is installed. Catalog versions come from the GitHub archive of the tag (or the `zip_release` asset), extracted into that folder ([core `repositories/integration.py` L367-402](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/components/marketplace/repositories/integration.py#L367-L402)). Two options:
  1. Commit the built bundle inside the integration folder (Alarmo commits `frontend/dist/alarm-panel.js`) and keep the TypeScript sources outside `custom_components/`.
  2. Build in CI, attach `wattbill.zip` to each release, and set `"zip_release": true, "filename": "wattbill.zip"`. `hacs.json` must still be committed at the tag (§1.3), and the HACS and hassfest checks run against the repository contents, so the committed tree must still validate.
- A panel can't be a separate dashboard (`plugin`) repository in the same repo, because one repository has one category. Dashboard resources would also go to `www/community/` and be served unauthenticated under `/local/community`. The panel belongs inside the integration, served by `async_register_static_paths` (see `docs/research/ha-custom-panel.md` §1.2).
- An update replaces the folder and needs a restart for a loaded integration, so the `?v=<manifest version>` cache-buster on `module_url` changes after each update as intended.
- Size: the 100 MiB / 50,000-file cap is far above a Lit bundle plus a TTF font.

### 5.2 fpdf2 as a pip requirement

- PyPI: `fpdf2` 2.9.0, `requires_python >=3.11`, depends on `Pillow!=9.2.*,>=8.3.2` and `fonttools>=4.34.0` ([PyPI JSON](https://pypi.org/pypi/fpdf2/json)). Neither `fpdf2` nor `fonttools` appears in core's `requirements_all.txt`. `Pillow==13.0.0` is pinned there and in `package_constraints.txt`.
- HA installs manifest requirements when the integration loads, with `uv pip install --quiet <req> --index-strategy unsafe-first-match --upgrade --constraint homeassistant/package_constraints.txt`. Outside a venv (HA OS / container) it installs into the user site-packages via `--target` ([core `util/package.py` L143-186](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/homeassistant/util/package.py#L143-L186)). The comment there notes that `unsafe-first-match` exists "for custom components which can use a different version of a package than the one we have built the wheel for".
- hassfest's `validate_custom_requirements` (new; [core `script/hassfest/requirements.py` L479-568](https://github.com/home-assistant/core/blob/0ed1ff906d0f04d21bf11c0b97ec813c928ff26b/script/hassfest/requirements.py#L479-L568)) rejects a custom requirement that:
  - is a core dependency;
  - is prohibited by constraints;
  - conflicts with HA's pin or constraints;
  - exactly pins a package HA already depends on. The error suggests `pkg>=x` instead "so it can follow along when Home Assistant updates it".

  So `"requirements": ["fpdf2==2.9.0"]` is fine, and Pillow/fonttools must not be listed. fpdf2's Pillow range accepts 13.0.0.
- `requirements` should list only packages HA doesn't already require (contrib integrations guide). The bundled TTF font is a plain file in the integration folder.

## Open points

- **Undocumented panel translations:** `config_panel` for a non-config sidebar panel works mechanically but is undocumented for custom integrations. Bundling strings in the JS is the safe alternative.
- **Catalog category:** `energy.meters_monitoring` and/or `computers_network.printers`.
- **Minimum HA version:** for issue #20. The floor from the settled design is already 2026.5 (subentry chaining). 2026.11 would make HACS-the-integration irrelevant (Marketplace only), and the observed window of maintained integrations is about 2 to 8 months behind stable.
- **Unchecked:**
  - the rules of hassfest's external `brand_images` plugin;
  - whether the catalog review treats the `brand/` folder in the release or on the default branch;
  - the `hassfest` Docker image's release cadence relative to core `dev`.
