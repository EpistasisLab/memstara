# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. afc-forge has no MCP
#   data server, so there is no counterpart upstream.
"""`slice_columns` takes a LIST — the regression guard for the comma bug.

158 of this cohort's 1,393 column names carry a comma inside the name
(`LAB__HDL CHOLESTEROL, DIRECT`, `DX__E78.5__Hyperlipidemia, unspecified`).
While `slice_columns` accepted a comma-separated string, every one of those 158
was unreachable: the matcher returned the name correctly, the agent transcribed
it correctly, and the split cut it into two names that exist nowhere.

The reason this file exists rather than the fix standing on its own: a list is
more awkward to type than a string, so the next person to read this signature has
a standing reason to "simplify" it back. `test_comma_name_is_not_split` fails the
moment they do.

These tests build their own two-row CSV. They do not read the EcoXAI cohort — the
behaviour under test is name handling, and a test that needs the real dataset is a
test that stops running the moment the dataset moves.
"""

from __future__ import annotations

import json

import pytest

import tools_data

#: `@mcp.tool()` wraps the function; `.fn` is the undecorated callable.
slice_columns = getattr(tools_data.slice_columns, "fn", tools_data.slice_columns)

#: Two of these three carry a comma. `PLAIN` is here so a test that passes
#: because nothing at all was returned still fails.
COMMA_A = "LAB__HDL CHOLESTEROL, DIRECT"
COMMA_B = "DX__E78.5__Hyperlipidemia, unspecified"
PLAIN = "BMI"
OUTCOME = "HIV_DETECTABLE"


@pytest.fixture()
def cohort(tmp_path, monkeypatch):
    """A minimal CSV whose header holds the two comma names, quoted as CSV requires."""
    csv = tmp_path / "cohort.csv"
    csv.write_text(
        f'"{COMMA_A}","{COMMA_B}","{PLAIN}","{OUTCOME}"\n'
        "1.0,1,22.5,1\n"
        "2.0,0,31.0,0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMSTARA_DATASET_PATH", str(csv))
    monkeypatch.setenv("MEMSTARA_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("MEMSTARA_OUTCOME_COLUMN", raising=False)
    return csv


@pytest.mark.unit
def test_comma_name_is_not_split(cohort):
    """The name arrives whole. This is the bug the file exists for."""
    result = json.loads(slice_columns([COMMA_A, PLAIN], OUTCOME, "t01"))

    assert result.get("columns_missing") == [], result
    assert COMMA_A in result["columns_used"]
    # The failure mode was two phantom halves, so assert against them by name:
    # a length check alone passes if the split produced two entries that happen
    # to be counted.
    assert "LAB__HDL CHOLESTEROL" not in result["columns_used"]
    assert "DIRECT" not in result["columns_used"]


@pytest.mark.unit
def test_written_csv_has_the_comma_column(cohort):
    """The name survives the round trip to disk, not just the JSON reply.

    A CSV writer that did not quote the header would produce a file whose columns
    no longer line up with its data — the reply would look correct and the ml
    stage would read a broken file.
    """
    import csv as csv_mod

    result = json.loads(slice_columns([COMMA_A, COMMA_B], OUTCOME, "t02"))
    with open(result["path"], newline="", encoding="utf-8") as fh:
        header = next(csv_mod.reader(fh))

    assert COMMA_A in header
    assert COMMA_B in header
    assert len(header) == 3  # two features + the outcome, not four or five


@pytest.mark.unit
def test_a_string_is_refused_not_iterated(cohort):
    """A bare string must fail loudly.

    Python iterates a string character by character, so the old contract's own
    input would silently become 30-odd single-letter column names — a failure that
    reads like a naming problem and is not one.
    """
    result = json.loads(slice_columns(f"{PLAIN}, {COMMA_A}", OUTCOME, "t03"))

    assert "error" in result
    assert "list" in result["error"]
    assert "columns_used" not in result


@pytest.mark.unit
def test_a_genuinely_absent_name_is_still_reported(cohort):
    """The fix must not make `columns_missing` useless.

    Accepting a list would be worth nothing if it also stopped distinguishing a
    name the dataset does not have from one it does.
    """
    result = json.loads(slice_columns([PLAIN, "LAB__NO_SUCH_TEST"], OUTCOME, "t04"))

    assert result["columns_missing"] == ["LAB__NO_SUCH_TEST"]
    assert PLAIN in result["columns_used"]


@pytest.mark.unit
def test_surrounding_whitespace_is_stripped_but_the_name_is_not_altered(cohort):
    """Agents indent their JSON. Trimming the ends is safe; touching the middle is not."""
    result = json.loads(slice_columns([f"  {COMMA_A}  "], OUTCOME, "t05"))

    assert result.get("columns_missing") == [], result
    assert COMMA_A in result["columns_used"]
