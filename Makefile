# Shortcuts for the dev container (scripts/devenv.py, see CONTRIBUTING.md).
SCENARIO ?= few-runs
VERSION ?= 0.0.0

.PHONY: build dev dev-build dev-restart dev-scenario dev-logs dev-down

# Build the panel and the release asset dist/coinop.zip with $(VERSION) as its version.
build: frontend/node_modules/.package-lock.json
	cd frontend && npm run build
	uv run scripts/release.py $(VERSION) custom_components/coinop dist

frontend/node_modules/.package-lock.json: frontend/package-lock.json
	cd frontend && npm ci

# Build the panel, (re)start the container, load the Preset $(SCENARIO) and show the log;
# Ctrl+C stops Home Assistant and removes the container.
dev:
	uv run scripts/devenv.py up $(SCENARIO)

# Rebuild the panel and reload Coin-op.
dev-build:
	uv run scripts/devenv.py build

# Restart Home Assistant, e.g. after a change to the Python code.
dev-restart:
	uv run scripts/devenv.py restart

# Load the Preset $(SCENARIO) into the running container.
dev-scenario:
	uv run scripts/devenv.py scenario $(SCENARIO)

dev-logs:
	uv run scripts/devenv.py logs

dev-down:
	uv run scripts/devenv.py down
