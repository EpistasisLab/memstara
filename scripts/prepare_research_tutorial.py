"""Register tutorial inputs and separate user skills; never start an execution."""
import argparse
import json
from pathlib import Path
import shlex

from memstara import research_inputs
from memstara.control import catalog

ROOT = Path(__file__).resolve().parents[1]


def prepare(configuration):
    checked = research_inputs.inspect(configuration)
    if not checked["input_checks_passed"]:
        raise ValueError(json.dumps(checked["issues"]))
    skills = {}
    for stage, filename in (("hypothesis", "hypothesis.md"), ("report", "explanation.md")):
        skills[stage] = catalog.register({
            "stage": stage, "name": "research-tutorial",
            "content": (ROOT / "examples/research-inputs/skills" / filename).read_text(),
        })["id"]
    books = {"hypothesis": [skills["hypothesis"]], "report": [skills["report"]]}
    research_inputs.validate_skills(books)
    selection = {
        "playbook_hypothesis": skills["hypothesis"],
        "playbook_data": "data_training_heavy", "playbook_ml": "ml_logistic_regression",
        "playbook_interpreter": "shared-shap", "playbook_report": skills["report"],
    }
    catalog.validate_selection(selection)
    record = research_inputs.register(configuration)
    if not record["input_checks_passed"]:
        raise ValueError("Inputs changed during registration; inspect the saved record before continuing")
    argv = ["python", "-m", "memstara.pipeline.board", "--research-input-id", record["id"]]
    for key, value in selection.items():
        argv.extend(["--" + key.replace("_", "-"), value])
    argv.extend(["--trials", "1", "--waves", "1"])
    return {"research_input_id": record["id"], "skills": skills,
            "execution_started": False, "execution_ready": False,
            "next_command": shlex.join(argv),
            "note": ("Configure models, databases, Redis and embeddings before executing. "
                     "Model calls can incur charges.")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", type=Path)
    args = parser.parse_args()
    from memstara.env import load_env
    load_env()
    print(json.dumps(prepare(json.loads(args.configuration.read_text())), indent=2))


if __name__ == "__main__":
    main()
