"""Configuration parity and credential separation for the Docker entrypoints."""

from pathlib import Path
import json

import pytest

from memstara.container_config import derive
from memstara.operational import resolve


def configuration(tmp_path):
    (tmp_path / "outputs").mkdir(exist_ok=True)
    (tmp_path / "cache").mkdir(exist_ok=True)
    (tmp_path / "user-inputs").mkdir(exist_ok=True)
    file = tmp_path / ".env"
    file.write_text("""MEMSTARA_DATABASE_URL=postgresql://boardowner:p%40ss%24%27@127.0.0.1:15541/boarddb
MOTORO_DATABASE_URL=postgresql+asyncpg://runtimeowner:pass@127.0.0.1:15542/runtimedb
MEMSTARA_VIEWER_DSN=postgresql://reader:readpass@127.0.0.1:15541/boarddb
CORE_VIEWER_DSN=postgresql://reader:readpass@127.0.0.1:15542/runtimedb
MOTORO_REDIS_URL=redis://127.0.0.1:15391/2
MEMSTARA_LLM_PROVIDER=openai
MEMSTARA_LLM_MODEL=test-model
OPENAI_API_KEY=TEST_SECRET_SENTINEL
MEMSTARA_WEB_PORT=15999
MEMSTARA_INPUTS_DIR=user-inputs
""")
    return resolve({}, file=file)[0]


def test_container_addresses_and_secret_separation(tmp_path):
    values = configuration(tmp_path)
    groups = derive(values, root=tmp_path)
    assert groups["board"]["POSTGRES_PASSWORD"] == "p@ss$'"
    assert groups["control"]["MEMSTARA_DATABASE_URL"] == "postgresql://boardowner:p%40ss%24%27@board:5432/boarddb"
    assert groups["control"]["MOTORO_REDIS_URL"] == "redis://redis:6379/2"
    assert groups["control"]["MEMSTARA_WEB_PORT"] == "15999"
    assert groups["control"]["MEMSTARA_CONTROL_PORT"] == "8072"
    assert "TEST_SECRET_SENTINEL" not in json.dumps(groups["api"])
    assert "boardowner" not in json.dumps(groups["api"])
    assert groups["api"]["MEMSTARA_VIEWER_DSN"].endswith("@board:5432/boarddb")
    assert values["MEMSTARA_DATABASE_URL"].endswith("@127.0.0.1:15541/boarddb")


@pytest.mark.parametrize(
    "key,value",
    [
        ("MEMSTARA_DATABASE_URL", "postgresql://owner:password@remote.example/db"),
        ("MEMSTARA_VIEWER_DSN", "postgresql://boardowner:pass@localhost/boarddb"),
        ("CORE_VIEWER_DSN", "postgresql://reader:pass@localhost/wrongdb"),
        ("MOTORO_REDIS_URL", "redis://user:pass@localhost/0"),
        ("MEMSTARA_DATASET_PATH", "/private/data.csv"),
    ],
)
def test_invalid_settings_fail_without_credentials(tmp_path, key, value):
    values = configuration(tmp_path)
    values[key] = value
    with pytest.raises(ValueError) as error:
        derive(values, root=tmp_path)
    assert value not in str(error.value)


def test_custom_inputs_and_output_mapping(tmp_path):
    values = configuration(tmp_path)
    csv = tmp_path / "user-inputs/cohort.csv"
    csv.write_text("feature,target\n1,0\n")
    values["MEMSTARA_DATASET_PATH"] = str(csv)
    values["MEMSTARA_OUTPUT_DIR"] = "/host/research-output"
    groups = derive(values, root=tmp_path)
    assert groups["control"]["MEMSTARA_DATASET_PATH"] == str(csv)
    assert groups["control"]["MEMSTARA_OUTPUT_DIR"] == str(tmp_path / "outputs")


def test_example_has_unique_keys_and_covers_core_contract():
    import re

    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    keys = re.findall(r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)=", text, re.M)
    assert len(keys) == len(set(keys))
    assert {"MEMSTARA_VIEWER_DSN", "CORE_VIEWER_DSN", "MEMSTARA_INPUTS_DIR", "MEMSTARA_LLM_MODEL"} <= set(keys)


def test_input_alias_matches_native_and_container_mount(tmp_path):
    values = configuration(tmp_path)
    host = tmp_path / "private-data"
    host.mkdir()
    (host / "study.csv").write_text("x,y\n1,0\n")
    (tmp_path / "user-inputs/study.csv").write_text("x,y\n1,0\n")
    file = tmp_path / ".env"
    file.write_text(
        file.read_text() + "MEMSTARA_INPUTS_DIR=private-data\nMEMSTARA_DATASET_PATH=user-inputs/study.csv\n"
    )
    values, _ = resolve({}, file=file)
    assert values["MEMSTARA_DATASET_PATH"] == str(host / "study.csv")
    mapped = derive(values, root=tmp_path)
    assert mapped["control"]["MEMSTARA_DATASET_PATH"] == str(tmp_path / "user-inputs/study.csv")


def test_conflicting_project_names_fail(tmp_path):
    configuration(tmp_path)
    file = tmp_path / ".env"
    file.write_text(file.read_text() + "COMPOSE_PROJECT_NAME=new\nMEMSTARA_COMPOSE_PROJECT=old\n")
    with pytest.raises(ValueError, match="conflicts"):
        resolve({}, file=file)


def test_inline_settings_cross_native_and_container_without_config_directory(tmp_path):
    configuration(tmp_path)
    file = tmp_path / '.env'
    with file.open('a') as stream:
        stream.write("MEMSTARA_PRICING_JSON='{\"profiles\":[]}'\n")
        stream.write("MEMSTARA_AZURE_PRICING_METERS_JSON='{\"profiles\":[]}'\n")
        stream.write("MEMSTARA_EXPLANATION_SOURCES_JSON='{}'\n")
    values, _ = resolve({}, file=file)
    groups = derive(values, root=tmp_path)
    assert not (tmp_path / 'config').exists()
    for key in ('MEMSTARA_PRICING_JSON', 'MEMSTARA_EXPLANATION_SOURCES_JSON',
                'MEMSTARA_AZURE_PRICING_METERS_JSON'):
        assert groups['control'][key] == values[key]
        assert key not in groups['api']


@pytest.mark.parametrize('setting', [
    "MEMSTARA_PRICING_JSON='private-invalid-json'",
    "MEMSTARA_PRICING_JSON='[]'",
    "MEMSTARA_PRICING_JSON='{}'",
    "MEMSTARA_EXPLANATION_SOURCES_JSON='private-invalid-json'",
    "MEMSTARA_PRICING_JSON='{\"profiles\":[]}'\nMEMSTARA_PRICING_PATH=missing.json",
])
def test_inline_configuration_errors_are_early_and_redacted(tmp_path, setting):
    configuration(tmp_path)
    file = tmp_path / '.env'
    with file.open('a') as stream:
        stream.write(setting + '\n')
    with pytest.raises(ValueError) as error:
        resolve({}, file=file)
    assert 'private-invalid-json' not in str(error.value)


def test_omitted_inputs_path_matches_compose_default(tmp_path):
    configuration(tmp_path)
    file = tmp_path / '.env'
    file.write_text(file.read_text().replace('MEMSTARA_INPUTS_DIR=user-inputs\n', ''))
    values, _ = resolve({}, file=file)
    assert values['MEMSTARA_INPUTS_DIR'] == str(tmp_path / 'user-inputs')
    assert derive(values, root=tmp_path)['control']['MEMSTARA_INPUTS_DIR'] == str(tmp_path / 'user-inputs')
