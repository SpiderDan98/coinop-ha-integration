"""A local Home Assistant with WattBill and test data, already logged in.

Usage: uv run scripts/devenv.py <command>

  up [scenario]     build the panel, (re)start the container, load a Scenario
  build             build the panel and reload WattBill
  restart           restart Home Assistant, e.g. after a change to the Python code
  scenario <name>   load a Scenario (also in the panel: the flask button at the bottom left)
  logs              follow Home Assistant's log
  down              stop and remove the container

The container runs the Home Assistant version of the project's .venv, keeps its
config in .dev/ and is reachable on http://localhost:8124 only from this machine.
"""

import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".dev" / "config"
AUTH = ROOT / ".dev" / "auth.json"
CONTAINER = "wattbill-dev"
URL = "http://127.0.0.1:8124"
CLIENT_ID = f"{URL}/"
DEFAULT_SCENARIO = "few-runs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("up").add_argument(
        "scenario", nargs="?", default=DEFAULT_SCENARIO
    )
    commands.add_parser("build")
    commands.add_parser("restart")
    commands.add_parser("scenario").add_argument("name")
    commands.add_parser("logs")
    commands.add_parser("down")
    args = parser.parse_args()
    match args.command:
        case "up":
            build_panel()
            start()
            load(args.scenario)
            print(f"Ready: {URL.replace('127.0.0.1', 'localhost')}/wattbill")
        case "build":
            build_panel()
            reload_wattbill()
        case "restart":
            run("docker", "restart", CONTAINER)
            wait_until_up()
        case "scenario":
            load(args.name)
        case "logs":
            os.execvp("docker", ["docker", "logs", "-f", "--tail", "100", CONTAINER])
        case "down":
            run("docker", "rm", "-f", CONTAINER)


def run(*command: str, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def build_panel() -> None:
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").exists():
        run("npm", "ci", cwd=frontend)
    run("npm", "run", "build", cwd=frontend)


def start() -> None:
    CONFIG.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    mounts = {
        CONFIG: "/config",
        ROOT / "dev" / "configuration.yaml": "/config/configuration.yaml:ro",
        ROOT
        / "custom_components"
        / "wattbill": "/config/custom_components/wattbill:ro",
        ROOT / "dev" / "wattbill_dev": "/config/custom_components/wattbill_dev:ro",
    }
    run(
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER,
        "-p",
        "127.0.0.1:8124:8123",
        "-e",
        f"TZ={host_time_zone()}",
        *(
            arg
            for source, target in mounts.items()
            for arg in ("-v", f"{source}:{target}")
        ),
        f"ghcr.io/home-assistant/home-assistant:{version('homeassistant')}",
    )
    wait_until_up()
    onboard()


def host_time_zone() -> str:
    zone = os.path.realpath("/etc/localtime").partition("zoneinfo/")[2]
    return zone or "UTC"


def wait_until_up() -> None:
    print("Waiting for Home Assistant", end="", flush=True)
    for _ in range(180):
        try:
            urllib.request.urlopen(f"{URL}/api/onboarding", timeout=2)
            print()
            return
        except urllib.error.HTTPError:
            # Answering at all means the HTTP server is up.
            print()
            return
        except OSError:
            print(".", end="", flush=True)
            time.sleep(1)
    sys.exit("\nHome Assistant did not start; see: uv run scripts/devenv.py logs")


def onboard() -> None:
    """Create the owner and finish onboarding, once per config directory."""
    try:
        with urllib.request.urlopen(f"{URL}/api/onboarding") as response:
            steps = {step["step"]: step["done"] for step in json.load(response)}
    except urllib.error.HTTPError:
        # Home Assistant removes the onboarding API once onboarding is done.
        steps = dict.fromkeys(("user", "core_config", "analytics", "integration"), True)
    if not steps["user"]:
        user = {"name": "Dev", "username": "dev", "password": "dev", "language": "en"}
        code = request("POST", "/api/onboarding/users", user | {"client_id": CLIENT_ID})
        tokens = token({"grant_type": "authorization_code", "code": code["auth_code"]})
        AUTH.write_text(json.dumps({"refresh_token": tokens["refresh_token"]}))
    access = access_token()
    for step in ("core_config", "analytics"):
        if not steps.get(step):
            request("POST", f"/api/onboarding/{step}", {}, access)
    if not steps.get("integration"):
        request(
            "POST",
            "/api/onboarding/integration",
            {"client_id": CLIENT_ID, "redirect_uri": f"{URL}/?auth_callback=1"},
            access,
        )
    # Home Assistant's own setup integrations, then wattbill_dev itself.
    wait_for_service("wattbill_dev", access)


def wait_for_service(domain: str, access: str) -> None:
    for _ in range(60):
        if any(
            s["domain"] == domain for s in request("GET", "/api/services", None, access)
        ):
            return
        time.sleep(1)
    sys.exit(f"{domain} did not load; see: uv run scripts/devenv.py logs")


def load(scenario: str) -> None:
    print(f"Loading the Scenario {scenario}")
    request(
        "POST",
        "/api/services/wattbill_dev/load",
        {"scenario": scenario},
        access_token(),
    )


def reload_wattbill() -> None:
    access = access_token()
    for entry in request(
        "GET", "/api/config/config_entries/entry?domain=wattbill", None, access
    ):
        request(
            "POST",
            f"/api/config/config_entries/entry/{entry['entry_id']}/reload",
            {},
            access,
        )
    print("Reloaded WattBill; reload the browser tab.")


def access_token() -> str:
    if not AUTH.exists():
        sys.exit("No login yet; run: uv run scripts/devenv.py up")
    refresh = json.loads(AUTH.read_text())["refresh_token"]
    access: str = token({"grant_type": "refresh_token", "refresh_token": refresh})[
        "access_token"
    ]
    return access


def token(fields: dict[str, str]) -> Any:
    data = urllib.parse.urlencode(fields | {"client_id": CLIENT_ID}).encode()
    with urllib.request.urlopen(f"{URL}/auth/token", data) as response:
        return json.load(response)


def request(method: str, path: str, body: Any = None, access: str | None = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if access:
        headers["Authorization"] = f"Bearer {access}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{URL}{path}", data, headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} {path}: {error.code} {error.read().decode()}")


if __name__ == "__main__":
    main()
