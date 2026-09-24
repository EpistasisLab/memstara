"""The `fields=` filter that lets one branch of the OKF bundle be asked for.

Dictionaries only — no bundle is read and `memstara.mcp_servers.okf` is never imported.
That module imports `yaml` and `motoro.mcp_servers.okf`, neither of which exists on a CI

there and nowhere else. `frontmatter.py` imports the standard library and nothing else,
which is the whole reason it is a separate file; `tests/test_prompts.py` is the same move
made for the same reason.

What is **not** covered here: that `okf_search` calls this on the right list at the right
moment. That is one line in an unimportable module, and it is a `Verified:` line on the
commit instead — counts taken against the real 333-document bundle.
"""

from __future__ import annotations

import pytest

from memstara.mcp_servers.frontmatter import matches, merge_locked, parse_field_filter, values_for

# Three documents standing in for the shape the real bundle has: a structured field per
# axis, and a `tags` list that does not fully agree with them — which is the finding
# this whole argument exists for.
PSYCH = {"terminus_kind": "psychiatric", "mechanism_family": "treatment-toxicity",
         "tags": ["adherence", "cohort"]}
SUD = {"terminus_kind": "sud", "mechanism_family": "treatment-toxicity",
       "tags": ["sud", "cohort"]}
UNFILED = {"tags": ["cohort"]}


# --------------------------------------------------------------------------- #
#  Reading the expression
# --------------------------------------------------------------------------- #


def test_one_constraint():
    assert parse_field_filter("terminus_kind=sud") == {"terminus_kind": "sud"}


def test_two_constraints_are_a_crossing():
    """A branch of the corpus is a terminus and a family together — 26 of them exist,
    and 16 are crossings. Expressing one needs no AND mode: it is two equalities."""
    assert parse_field_filter("mechanism_family=treatment-toxicity,terminus_kind=sud") == {
        "mechanism_family": "treatment-toxicity",
        "terminus_kind": "sud",
    }


def test_whitespace_and_empty_pieces_are_forgiven():
    assert parse_field_filter(" terminus_kind = sud , ") == {"terminus_kind": "sud"}


def test_an_empty_filter_asks_for_nothing():
    assert parse_field_filter("") == {}
    assert parse_field_filter("   ") == {}


def test_a_piece_with_no_equals_raises_and_says_which_piece():
    """`fields="sud"` is the natural mistake — it reads like the `tags` argument. Taking
    it as "no constraints" would return the whole bundle and look like a working call."""
    with pytest.raises(ValueError, match="sud"):
        parse_field_filter("terminus_kind=sud,sud")


def test_an_empty_key_or_value_raises():
    with pytest.raises(ValueError, match="'=sud'"):
        parse_field_filter("=sud")
    with pytest.raises(ValueError, match="'terminus_kind='"):
        parse_field_filter("terminus_kind=")


def test_the_same_key_twice_raises_rather_than_silently_dropping_one():
    """A mapping cannot hold both, so the first would vanish without a word and the
    caller would be shown a narrower slice than the one they wrote."""
    with pytest.raises(ValueError, match="constrained twice"):
        parse_field_filter("terminus_kind=sud,terminus_kind=psychiatric")


# --------------------------------------------------------------------------- #
#  Applying it to a document
# --------------------------------------------------------------------------- #


def test_an_empty_filter_matches_everything():
    """The default. Every call made before this change must keep behaving identically."""
    assert matches(PSYCH, {})
    assert matches(UNFILED, {})


def test_one_equality():
    wanted = parse_field_filter("terminus_kind=sud")
    assert matches(SUD, wanted)
    assert not matches(PSYCH, wanted)


def test_a_crossing_needs_both_keys():
    wanted = parse_field_filter("mechanism_family=treatment-toxicity,terminus_kind=sud")
    assert matches(SUD, wanted)
    # Same family, wrong terminus — this is the document a tag OR filter would return.
    assert not matches(PSYCH, wanted)


def test_a_key_the_document_lacks_is_a_miss_not_a_pass():
    """The filter names a branch. A document filed in no branch is in none of them —
    treating an absent key as "no constraint to fail" would put every unfiled document
    into every skill's reading."""
    assert not matches(UNFILED, parse_field_filter("terminus_kind=sud"))


def test_comparison_is_case_folded():
    wanted = parse_field_filter("terminus_kind=SUD")
    assert matches(SUD, wanted)
    assert matches({"terminus_kind": "SUD"}, parse_field_filter("terminus_kind=sud"))


def test_a_list_valued_field_matches_element_wise():
    """`tags` is a list in this format, and `fields="tags=sud"` is a reasonable thing to
    write. It must mean "carries that tag", not "the whole list equals that string"."""
    assert matches(SUD, parse_field_filter("tags=sud"))
    assert not matches(PSYCH, parse_field_filter("tags=sud"))


def test_a_non_string_value_compares_as_written():
    """Front matter carries numbers and booleans too, and `disable_yaml_timestamps`
    (`src/memstara/mcp_servers/okf.py:131`) is there so a date stays the string it was
    written as. The filter arrives as text either way."""
    assert matches({"n": 240}, parse_field_filter("n=240"))
    assert matches({"published": "2026-08-10"}, parse_field_filter("published=2026-08-10"))


# --------------------------------------------------------------------------- #
#  The branch a run is confined to
# --------------------------------------------------------------------------- #


def test_no_lock_leaves_the_caller_alone():
    """Every run made before the lock existed takes this path."""
    assert merge_locked({}, parse_field_filter("terminus_kind=sud")) == {"terminus_kind": "sud"}
    assert merge_locked({}, {}) == {}


def test_a_caller_asking_for_nothing_still_gets_the_lock():
    """The point of the whole mechanism: the confinement does not depend on the agent
    passing anything, because an agent that passes nothing is the normal case."""
    assert merge_locked({"terminus_kind": "sud"}, {}) == {"terminus_kind": "sud"}


def test_a_caller_may_narrow_further_inside_the_branch():
    merged = merge_locked({"terminus_kind": "sud"},
                          parse_field_filter("mechanism_family=treatment-toxicity"))
    assert merged == {"terminus_kind": "sud", "mechanism_family": "treatment-toxicity"}
    assert matches(SUD, merged)


def test_repeating_the_lock_is_not_an_error():
    """`fields="terminus_kind=sud"` under the same lock is agreement, not conflict."""
    assert merge_locked({"terminus_kind": "sud"}, {"terminus_kind": "SUD"}) == {"terminus_kind": "sud"}


def test_reaching_outside_the_branch_raises_and_names_both_values():
    """Not silently overruled in either direction. Honouring it would leave the branch;
    dropping it would answer a different question and still look like a hit."""
    with pytest.raises(ValueError, match="locked to 'sud'"):
        merge_locked({"terminus_kind": "sud"}, parse_field_filter("terminus_kind=psychiatric"))


# --------------------------------------------------------------------------- #
#  What an empty result is told
# --------------------------------------------------------------------------- #


def test_values_for_lists_what_the_bundle_actually_holds():
    """So a filter matching nothing can say which of the two it is — a query with no
    hits, or a value no document is filed under."""
    assert values_for([PSYCH, SUD, UNFILED], "terminus_kind") == ["psychiatric", "sud"]


def test_values_for_flattens_a_list_field_and_deduplicates():
    assert values_for([PSYCH, SUD, UNFILED], "tags") == ["adherence", "cohort", "sud"]


def test_values_for_a_key_nobody_carries_is_empty():
    """Which is the answer to a misspelled key, and a different message from "that
    value does not occur"."""
    assert values_for([PSYCH, SUD, UNFILED], "terminus_type") == []
