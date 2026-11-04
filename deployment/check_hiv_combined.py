"""Validate combined HIV inputs in the runtime image, without model calls."""
import json
import os
import tempfile
from pathlib import Path

from memstara import research_inputs
from memstara.corpus_skills import corpus_profile
from memstara.mcp_servers import okf


def main():
    deployment = Path(__file__).resolve().parent
    config = json.loads((deployment / "hiv-combined-research.json").read_text())
    root = Path(config["knowledge_path"])
    os.environ["AGENTIC_OKF_BUNDLE_DIR"] = str(root)
    os.environ.pop("MEMSTARA_OKF_FIELDS", None)
    os.environ.pop("MEMSTARA_RUN_CONFIG", None)
    assert corpus_profile() == "hiv", "Combined corpus must retain the HIV skill profile"
    docs, skipped = okf._load(root)
    assert not skipped, f"Unreadable documents: {skipped}"
    assert any(doc.address.startswith("addiction-kb/mechanisms/") for doc in docs)
    papers = [doc for doc in docs if doc.address.startswith("hiv-suppression/")
              and doc.path.name.split("_", 1)[0].isdigit()]
    assert len(papers) == 142, f"Expected 142 literature documents; found {len(papers)}"
    result = json.loads(okf.okf_search("housing food insecurity stigma", domain="hiv-suppression"))
    assert not result.get("error"), result
    assert any(row.get("hits") for row in result.get("results", [])), "SDOH literature search returned no hits"
    read = json.loads(okf._read_documents("hiv-suppression/social-structural-determinants/36449782_Harp"))
    assert read.get("documents") and not read["documents"][0].get("error"), read
    with tempfile.TemporaryDirectory() as directory:
        Path(directory, "app-selection.json").write_bytes((deployment / "hiv-combined-selection.json").read_bytes())
        os.environ["MEMSTARA_INPUTS_DIR"] = directory
        checked = research_inputs.inspect(config)
    assert checked["input_checks_passed"], checked.get("issues")
    print(json.dumps({"input_checks_passed": True, "literature_papers": len(papers),
                      "readable_documents": len(docs), "fingerprint": checked["fingerprint"],
                      "model_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
