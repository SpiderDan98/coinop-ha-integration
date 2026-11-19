"""Backend responses recorded as the panel tests' canned responses (seam 2).

A test drives the backend, then hands what the panel would receive to
`assert_recorded`. The JSON under `frontend/test/fixtures/backend/` must match,
so the panel can't be tested against shapes the backend no longer sends.
Re-record after an intended change with:

    UPDATE_FIXTURES=1 uv run pytest tests/test_panel_contract.py
"""

import json
import os
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parents[1] / "frontend" / "test" / "fixtures" / "backend"


def stable_ids(payload: Any, ids: dict[str, str]) -> Any:
    """Replace generated ids (ULIDs, subentry ids) by readable fixed ones."""
    text = json.dumps(payload)
    for generated, fixed in ids.items():
        text = text.replace(generated, fixed)
    return json.loads(text)


def assert_recorded(name: str, payload: Any) -> None:
    path = FIXTURES / f"{name}.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_FIXTURES"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.exists(), f"{path.name} not recorded; run with UPDATE_FIXTURES=1"
    recorded = json.loads(path.read_text(encoding="utf-8"))
    assert payload == recorded, (
        f"{path.name} is out of date; re-record with UPDATE_FIXTURES=1"
    )
