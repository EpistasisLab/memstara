import json

import pytest

from memstara.installation import prepare, read
from memstara.operational import resolve


def test_new_installation_is_private_stable_and_resolvable(tmp_path):
    (tmp_path / ".env").write_text(
        "MEMSTARA_LLM_PROVIDER=openai\nMEMSTARA_LLM_MODEL=example\nMEMSTARA_LLM_API_KEY=test\n"
    )
    prepare(tmp_path)
    first = read(tmp_path)
    prepare(tmp_path)
    assert first == read(tmp_path)
    assert (tmp_path / ".memstara/installation.json").stat().st_mode & 0o777 == 0o600
    values, _ = resolve({}, file=tmp_path / ".env")
    assert values["MEMSTARA_DATABASE_URL"] == first["MEMSTARA_DATABASE_URL"]
    other = tmp_path / "another"
    other.mkdir()
    (other / ".env").write_text("")
    prepare(other)
    assert read(other)["COMPOSE_PROJECT_NAME"] != first["COMPOSE_PROJECT_NAME"]


def test_legacy_identity_survives_env_cleanup(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "COMPOSE_PROJECT_NAME=old-project\nMEMSTARA_DATABASE_URL=postgresql://old:password@localhost:5432/db\nMEMSTARA_BOARD_VOLUME_NAME=old-volume\n"
    )
    prepare(tmp_path)
    before = read(tmp_path)
    env.write_text("")
    prepare(tmp_path)
    assert read(tmp_path) == before
    config = json.loads((tmp_path / "compose.override.yaml").read_text())
    assert config["volumes"]["board-data"] == {"external": True, "name": "old-volume"}
    assert config["name"] == "old-project"


def test_existing_override_is_never_replaced(tmp_path):
    (tmp_path / ".env").write_text("")
    path = tmp_path / "compose.override.yaml"
    path.write_text("services: {}")
    with pytest.raises(ValueError):
        prepare(tmp_path)
    assert path.read_text() == "services: {}"


def test_conflicting_credentials_and_corrupt_state_fail_closed(tmp_path):
    (tmp_path / ".env").write_text("")
    prepare(tmp_path)
    path = tmp_path / ".memstara/installation.json"
    before = path.read_text()
    (tmp_path / ".env").write_text("COMPOSE_PROJECT_NAME=changed\n")
    with pytest.raises(ValueError):
        prepare(tmp_path)
    assert path.read_text() == before
    path.write_text("{}")
    with pytest.raises(ValueError):
        prepare(tmp_path)


def test_missing_state_never_creates_replacement_identity(tmp_path):
    (tmp_path / ".env").write_text("")
    prepare(tmp_path)
    (tmp_path / ".memstara/installation.json").unlink()
    with pytest.raises(ValueError, match="Missing installation state"):
        prepare(tmp_path)
