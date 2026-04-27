from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _mesh2cad_default_state_dir(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Avoid writing job state under ~/.mesh2cad during tests unless explicitly configured."""
    if os.environ.get("MESH2CAD_STATE_DIR"):
        return
    state_root = tmp_path_factory.mktemp("mesh2cad_state")
    os.environ["MESH2CAD_STATE_DIR"] = str(state_root)
