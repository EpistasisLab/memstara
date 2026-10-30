"""Contracts shared by the complete specialist-pilot driver and numerical worker."""

from __future__ import annotations

from itertools import product
import random

STAGES = ("hypothesis", "data", "ml", "interpreter", "report")


def schedule(config: dict) -> list[dict]:
    """One execution per unique condition; never pad a design to its requested count."""
    choices = config["choices"]
    if set(choices) != set(STAGES) or config.get("repetitions") != 1:
        raise ValueError("Specify all five factors and exactly one repetition")
    for stage, entries in choices.items():
        if not isinstance(entries, list) or not entries or len(set(entries)) != len(entries):
            raise ValueError(f"{stage}: provide nonempty, unique skill IDs")
    rows = [dict(zip(STAGES, values, strict=True)) for values in product(*(choices[s] for s in STAGES))]
    if len(rows) != config["expected_combinations"]:
        raise ValueError(f"Design has {len(rows)} distinct combinations, not {config['expected_combinations']}")
    return [{"combination_id": i, **row} for i, row in enumerate(rows, 1)]


def feature_input(columns: list[str], *, seed: int, random_selection: bool) -> dict:
    if len(columns) < 4 or len(columns) != len(set(columns)):
        raise ValueError("At least four unique eligible predictors are required")
    rng = random.Random(seed)
    selected = rng.sample(columns, rng.randint(4, min(20, len(columns)))) if random_selection else None
    return {
        "feature_size": {"minimum": 4, "maximum": 20},
        "eligible_features": columns,
        "required_features": selected,
        "selection": "seeded_uniform_without_replacement" if random_selection else "llm",
        "seed": seed,
    }


def validate_hypothesis(value: dict, context: dict) -> dict:
    features = value.get("features")
    if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
        raise ValueError("features must be a list of exact column names")
    if not 4 <= len(features) <= 20 or len(set(features)) != len(features):
        raise ValueError("Select 4–20 distinct predictors")
    if not set(features) <= set(context["eligible_features"]):
        raise ValueError("Selected predictors are not in the eligible input")
    if context["required_features"] is not None and features != context["required_features"]:
        raise ValueError("Random hypothesis must preserve the sampled predictors and their order")
    if any(
        not isinstance(value.get(key), str) or not value[key].strip() for key in ("question", "hypothesis", "rationale")
    ):
        raise ValueError("Question, hypothesis and rationale are required")
    return value


def validate_data_plan(value: dict, skill: str) -> dict:
    if set(value) != {"test_size", "seed", "stratify"} or value["stratify"] is not True:
        raise ValueError("Data plan requires test_size, seed and stratify=true")
    if type(value["seed"]) is not int or not 0 <= value["seed"] <= 2147483647:
        raise ValueError("Data split seed is outside the supported range")
    fraction = value["test_size"]
    if type(fraction) not in (int, float):
        raise ValueError("test_size must be numeric")
    if skill == "data_training_heavy" and not 0.1 <= fraction <= 0.3:
        raise ValueError("Training-heavy requires 70–90% training rows")
    if skill == "data_balanced_stratified" and fraction != 0.5:
        raise ValueError("Balanced train/test allocation requires test_size=0.5")
    if skill not in ("data_training_heavy", "data_balanced_stratified"):
        raise ValueError("Unsupported data skill")
    return value
