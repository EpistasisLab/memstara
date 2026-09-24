# SOURCE: SANDBOX-ORIGINAL — verification around the unchanged ported matcher.
import json

import numpy as np
import pytest

from memstara.matcher.catalog import CatalogEntry
from memstara.matcher.matcher import Matcher
from memstara.matcher.service import VerifiedMatcher


def fixture_matcher(cls=VerifiedMatcher):
    names = ["NALOXONE", "VALACYCLOVIR", "BUPRENORPHINE", "METHADONE"]
    entries = [CatalogEntry(f"MED__{n}", "medication", n, "wide_passthrough", f"MED__{n}") for n in names]
    # Every drug gets identical similarity: identity must not depend on a threshold.
    return cls.build(entries, encoder=lambda texts: np.ones((len(texts), 2)))


@pytest.mark.parametrize("query", ["Naltrexone", "Varenicline", "Acamprosate"])
def test_absent_drug_cannot_be_replaced_by_close_spelling(query):
    assert fixture_matcher(Matcher).match(query).matches
    result = fixture_matcher().match(query)
    assert result.matches == ()
    assert "No exact medication name" in result.note


@pytest.mark.parametrize("query,column", [
    ("Buprenorphine", "MED__BUPRENORPHINE"), ("methadone", "MED__METHADONE"),
    ("MED__METHADONE", "MED__METHADONE"),
])
def test_exact_identity_survives_ranking_budget(query, column):
    result = fixture_matcher().match(query, top_k=1)
    assert [m.feature_name for m in result.matches] == [column]


def test_both_mcp_surfaces_use_verified_matcher(monkeypatch):
    from memstara.matcher import service
    from memstara.mcp_servers import matcher as server
    monkeypatch.setattr(service, "get_matcher", fixture_matcher)
    single = json.loads(server.match_concept("Naltrexone", feature_type="medication"))
    batch = json.loads(server.match_concepts(["Naltrexone", "Methadone"]))["results"]
    assert single["candidates"] == batch[0]["candidates"] == []
    assert batch[1]["candidates"][0]["feature_name"] == "MED__METHADONE"


def test_diagnosis_ranking_is_unchanged():
    entry = CatalogEntry("DX__I10", "diagnosis", "hypertension", "wide_passthrough", "DX__I10")
    def encode(texts):
        return np.ones((len(texts), 2))
    assert VerifiedMatcher.build([entry], encoder=encode).match("hypertension") == Matcher.build(
        [entry], encoder=encode,
    ).match("hypertension")
