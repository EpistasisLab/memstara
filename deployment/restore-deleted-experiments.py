"""Preview or request restoration of retained experiments through the control API.

This never edits the live workspace file behind the controller, rewrites results,
restarts containers, or starts model calls. The server must include action=restore.
Settings come from the selected execution; later unsaved edits cannot be recovered.
"""

import argparse
import base64
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from memstara.control.restore import definition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Application base URL")
    parser.add_argument("--restore", action="append", required=True, metavar="NUMBER=RUN_TAG")
    parser.add_argument("--apply", action="store_true", help="Restore definitions through the updated control service")
    args = parser.parse_args()
    selected = []
    for specification in args.restore:
        number, separator, tag = specification.partition("=")
        if not separator or not number.isdigit() or not tag:
            parser.error("Use --restore NUMBER=RUN_TAG for each saved experiment")
        selected.append((tag, int(number)))
    entries = [definition(ROOT / "outputs/runs", tag, number) for tag, number in selected]
    print(json.dumps([{k: entry[k] for k in ("id", "number", "name", "restored_from_run_tag")}
                      for entry in entries], indent=2))
    if not args.apply:
        print("Preview only. No changes made. Use --apply after deploying restore support.")
        return
    origin = args.url.rstrip("/")
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Use the application's base URL without a path")
    auth = json.loads((ROOT / ".memstara/web-auth/client.json").read_text())
    token = base64.b64encode((auth["username"] + ":" + auth["password"]).encode()).decode()
    headers = {"Authorization": "Basic " + token, "Origin": origin, "Content-Type": "application/json"}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for entry in entries:
        payload = {"action": "restore", "run_tag": entry["restored_from_run_tag"], "number": entry["number"]}
        request = urllib.request.Request(origin + "/control/pipelines", data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with opener.open(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Restore request rejected (HTTP {error.code}). Deploy restore support before retrying; no direct file rewrite was attempted.") from None
        if result.get("id") != entry["id"]:
            raise RuntimeError("Restored identity did not match the saved experiment")
        print(f"Restored Experiment {entry['number']}: {entry['name']} ({entry['id']})")
    print("Definitions restored with original IDs. Refresh the browser; retained results and costs are included again. No experiment was started.")


if __name__ == "__main__":
    main()
