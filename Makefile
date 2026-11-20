# Shortcuts for the dev container (scripts/devenv.py, see CONTRIBUTING.md).
SCENARIO ?= few-runs

.PHONY: dev dev-build dev-restart dev-scenario dev-logs dev-down

# Build the panel, (re)start the container, load $(SCENARIO) and show the log;
# Ctrl+C stops Home Assistant and removes the container.
dev:
	uv run scripts/devenv.py up $(SCENARIO)

# Rebuild the panel and reload WattBill.
dev-build:
	uv run scripts/devenv.py build

# Restart Home Assistant, e.g. after a change to the Python code.
dev-restart:
	uv run scripts/devenv.py restart

# Load $(SCENARIO) into the running container.
dev-scenario:
	uv run scripts/devenv.py scenario $(SCENARIO)

dev-logs:
	uv run scripts/devenv.py logs

dev-down:
	uv run scripts/devenv.py down
