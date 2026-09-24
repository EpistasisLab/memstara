# SOURCE: SANDBOX-ORIGINAL — replay recorded medication identity regressions.
"""Validate current cohort identity without rebuilding caches or reading patient rows.

Historical membership is reported separately: missing historical columns must not
be invented to satisfy an old acceptance expectation.
"""
import argparse

QUERIES = ("Naltrexone", "Acamprosate", "Varenicline", "Buprenorphine", "Citalopram")
HISTORICAL_PRESENT = {"Buprenorphine", "Citalopram"}


def check_results(matcher, columns, queries=QUERIES):
    """Raise on a catalog/header mismatch or a substituted/missing exact drug."""
    rows = []
    for query, result in zip(queries, matcher.match_many(queries, feature_type="medication"), strict=True):
        name = f"MED__{query.upper()}"
        present = name in columns
        catalog_present = any(e.feature_name == name for e in matcher.entries)
        if catalog_present != present:
            raise AssertionError(f"{query}: catalog and dataset header disagree")
        expected = [name] if present else []
        if [m.feature_name for m in result.matches] != expected:
            raise AssertionError(f"{query}: incorrect medication identity result")
        if not present and "No exact medication name" not in (result.note or ""):
            raise AssertionError(f"{query}: absent medication explanation missing")
        rows.append({"query": query, "present": present,
                     "historical_membership_changed": query in QUERIES and present != (query in HISTORICAL_PRESENT)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-historical-catalog", action="store_true",
                        help="Fail if current membership differs from the original five-query fixture.")
    args = parser.parse_args()
    from memstara.env import load_env
    load_env()
    from memstara.matcher.service import dataset_path, get_matcher, read_columns
    rows = check_results(get_matcher(), read_columns(dataset_path()), (*QUERIES, "Naloxone"))
    for row in rows:
        status = "exact name retained" if row["present"] else "no exact name in current cohort"
        changed = " (different from historical expectation)" if row["historical_membership_changed"] else ""
        print(f"{row['query']}: {status}{changed}")
    print("PASS: current-cohort identity checks; no medication substitutions.")
    changed = any(row["historical_membership_changed"] for row in rows)
    if changed:
        print("Historical acceptance differs from current membership; original dataset replay is not claimed.")
        if args.require_historical_catalog:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
