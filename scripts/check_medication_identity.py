# SOURCE: SANDBOX-ORIGINAL — replay the five recorded matcher regressions locally.
"""Use the existing catalog/cache; never rebuild it or print cohort rows/columns."""
from memstara.env import load_env
from memstara.matcher.service import get_matcher


def main():
    load_env()
    queries = ["Naltrexone", "Acamprosate", "Varenicline", "Buprenorphine", "Citalopram"]
    results = get_matcher().match_many(queries, feature_type="medication")
    for index, result in enumerate(results):
        if index < 3:
            assert not result.matches, "An absent drug was substituted"
        else:
            assert len(result.matches) == 1, "Expected exact medication is missing"
            assert result.matches[0].feature_name == f"MED__{queries[index].upper()}"
    print("PASS: original five queries — three absent drugs rejected, two exact drug names retained.")


if __name__ == "__main__":
    main()
