#!/usr/bin/env python3
# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. Nothing upstream knows
#   about this repository's backlog files or its GitHub board.


    python scripts/backlog_to_issues.py plan       # build the manifest, create nothing
    python scripts/backlog_to_issues.py create     # create (and close) the issues
    python scripts/backlog_to_issues.py labels     # make the area:* labels and apply them
    python scripts/backlog_to_issues.py link       # append issue numbers to id references
    python scripts/backlog_to_issues.py board      # add every issue to the project
    python scripts/backlog_to_issues.py annotate   # write the numbers back into the files
    python scripts/backlog_to_issues.py sync --dry-run   # comment where a path went stale


issues, this file is the list. After they become issues, this file is the record
of where each one came from." This is the thing that moves it across.


editions of the English originals, so they are never parsed — only annotated, in
the last step, so they stay true to that claim.

EVERY SUBCOMMAND IS IDEMPOTENT. `create` skips an id that already has an issue,
`board` skips one already on the board, `annotate` skips a line already written.
A creation script that is not idempotent has exactly one safe run, and any
interruption after that leaves a board nobody can trust. Re-running is the
recovery procedure, so re-running has to be free.

THE MANIFEST IS NOT COMMITTED. `outputs/` is ignored, and this file stays there
on purpose: it copies every issue body out of the backlog, so committing it would

the exact thing the backlog was written against. It is rebuilt by `plan`, and
`create` refills the issue numbers from GitHub, so losing it costs one command.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parent.parent.resolve()

REPO = "HyunjunA/memstara"
PROJECT_OWNER = "HyunjunA"
PROJECT_TITLE = "Memstara"

#: The two English files that are parsed. Order matters: it is the order the



#: The four files that get issue numbers written back into them. The `_KR`
#: editions are in this list and in no other — they are annotated, never read.


#: Same work, written down twice. Each pair becomes ONE issue, and the id that
#: survives is the one holding more of the record.
#:
#: `MEMO-09` ≡ `H-08` — both "move to motoro v0.5.2", both Done. `H-08` keeps the
#: table of where every name landed and the three that deliberately did not move.
DROP_IDS = {"MEMO-09": "H-08"}


#: 본 것이다. 두 번 하지 말고 거기서 한다"). One issue, but MEMO-08's framing —
#: *the corpus is fine, the bridge is broken* — is not in `A-02` today and is
#: worth keeping, so it is folded in rather than dropped.
FOLD_IDS = {"MEMO-08": "A-02"}

#: THE BOARD HAS TWO LABEL AXES, AND THEY ARE NOT THE SAME KIND OF THING.
#:
#: `KIND_LABELS` says what *sort* of work an item is. It is still five, and the

#: maintain than it explains" — is a statement about this axis only.
#:
#: `AREAS` says which *part of the code* the work is about. It is a different
#: question, so it gets a different axis rather than a sixth kind. Every area
#: reaches GitHub prefixed, `area:matcher`, which is what stops the two sets
#: being read as one: nobody mistakes `area:matcher` for a sibling of `bug`.
#: The convention is Kubernetes' (`kind/`, `area/`, `priority/`), narrowed to
#: the one axis this repository was missing.


#: label outside this set is a bug in the source file, not something to pass
#: through to GitHub.
KIND_LABELS = {"bug", "enhancement", "research-decision", "verification", "housekeeping"}

#: Area -> the sentence that becomes the GitHub label's description, which is the
#: only place a developer opening the label picker can read what it covers.
#:
#: NOT INVENTED. Each one was read off the `**Evidence**` paths the items already
#: carry. An area with no item behind it would be a guess about future work.
#:
#: The area is the subsystem the work is **about**, not the directory the diff
#: lands in. "Document the databases" is `blackboard`, not `docs`; that its
#: deliverable is a document is already said by its `housekeeping` kind label.
#: `docs` is for work whose subject genuinely is the documentation machinery.
#:
#: `viewer-web` and `viewer-api` stay apart rather than one `viewer`, because
#: "is the frontend separable" is a question the board should answer by itself.
AREAS = {
    "blackboard": "The board itself and its MCP surface — rows, DSN, run lock",
    "infra": "compose.yml, .env, .vscode, CI, repo settings, the motoro dependency",
    "pipeline": "src/memstara/pipeline — orchestration, the agents, the waves",
    "docs": "The documentation set itself — the index, build_pdf.sh, the EN/KR mirrors",
    "matcher": "src/memstara/matcher — the afc-forge port, scoring, leakage",
    "okf": "The OKF corpus and its server",
    "data": "src/memstara/prep and the data/ml tool servers",
    "viewer-web": "viewer/web — React, TypeScript, Vite",
    "viewer-api": "viewer/api — the service behind the viewer",
}

#: One colour for all nine, and it is not any of the five kind colours. Two axes
#: that look alike in the label list are two axes nobody keeps apart.
AREA_COLOR = "1d76db"

#: Board vocabulary, copied from the ASAREE Roadmap so the two boards read the

STATUSES = ("Backlog", "Ready", "In progress", "In review", "Done")
SIZES = ("XS", "S", "M", "L", "XL")
PRIORITIES = ("P0", "P1", "P2", "P3")

#: `task.yml:112-116` spells P0 out. The board copies that wording exactly, so a
#: person reading the board and a person filing through the template see one thing.
PRIORITY_OPTIONS = ("P0 — blocks other work", "P1", "P2", "P3")

MANIFEST_PATH = _ROOT / "outputs" / "issues_manifest.json"

#: `### A-02 · title`. The id shape is strict on purpose: `#### Board fields` and
#: the other prose subheadings must not be mistaken for items.
_ITEM_RE = re.compile(r"^### ([A-Z]+-\d+) · (.+)$")

#: The field line under every heading. `Priority` is absent on the `D-*` items,
#: so it is optional here and defaults later.
#:
#: `Area` is optional *in the regex* and required in `parse_file`, which is not a
#: contradiction: the regex has to match a line missing its area in order for the
#: error to be able to name the item. Made mandatory here, the failure would be
#: "H-07 has no readable field line", which sends the reader looking at the wrong
#: thing.
_FIELD_RE = re.compile(
    r"^`Status: ([^`]+)`"
    r"(?: · `Priority: ([^`]+)`)?"
    r" · `Size: ([^`]+)`"
    r"(?: · `Area: ([^`]+)`)?"
    r" · `Labels: ([^`]+)`$"
)

#: A bold field opener at the start of a line — `**What** — text`. Rewritten into
#: a `### What` heading so a scripted issue and one filed through the template
#: look the same.
_BOLD_FIELD_RE = re.compile(r"^\*\*([A-Z][^*]{2,60}?)\*\* — ", re.MULTILINE)

#: Every reference to another item, for the `link` pass.
_ID_REF_RE = re.compile(r"\b([A-Z]+-\d{2})\b")


# --------------------------------------------------------------------------- #
# Reading the files
# --------------------------------------------------------------------------- #


def _to_headings(body: str) -> str:
    """Rewrite `**What** — text` openers into `### What` headings.

    Only the opener moves. Everything else in the body — tables, block quotes,
    the extra sections a few items carry (`H-08`'s "Where everything landed") —
    is left exactly as written, because an issue that drops part of its item is
    worse than one that looks slightly different from the template.

    Args:
        body: The item's markdown, below its field line.

    Returns:
        The same markdown with field openers promoted to headings.
    """
    return _BOLD_FIELD_RE.sub(lambda m: f"### {m.group(1)}\n\n", body)


def parse_file(path: Path) -> list[dict[str, Any]]:
    """Read one backlog file into a list of items.

    An item runs from its `### ID · title` heading to the next heading of the
    same level or higher. Whatever sits in between is the body, verbatim.

    Args:
        path: Repository-relative path of an English backlog file.

    Returns:
        One dict per item, in file order.

    Raises:
        ValueError: If an item's field line is missing or malformed, or if it
            carries a label outside the five, or an area outside the nine. All
            mean the file is wrong, and filing 48 issues off a wrong file is not
            something to do quietly.
    """
    lines = (_ROOT / path).read_text(encoding="utf-8").splitlines()
    items: list[dict[str, Any]] = []
    group = ""

    for i, line in enumerate(lines):


        # so both levels count and the most recent one wins.
        if line.startswith("# ") or line.startswith("## "):
            group = line.lstrip("#").strip()
            continue

        match = _ITEM_RE.match(line)
        if not match:
            continue

        item_id, raw_title = match.group(1), match.group(2).strip()

        # The field line is the next non-blank line. Anything else is a
        # malformed item, and guessing past it is how a board goes wrong.
        cursor = i + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        fields = _FIELD_RE.match(lines[cursor].strip()) if cursor < len(lines) else None
        if not fields:
            raise ValueError(f"{path}:{cursor + 1} — {item_id} has no readable field line")

        # The body ends where the next item or section starts.
        end = cursor + 1
        while end < len(lines) and not (lines[end].startswith("### ") or lines[end].startswith("# ")):
            end += 1
        body = "\n".join(lines[cursor + 1 : end]).strip().rstrip("-").strip()

        status = fields.group(1).strip()
        priority = (fields.group(2) or "P2").strip()
        size = fields.group(3).strip()
        area = (fields.group(4) or "").strip()
        labels = [label.strip() for label in fields.group(5).split(",")]

        bad = set(labels) - KIND_LABELS
        if bad:
            raise ValueError(f"{path} — {item_id} carries {sorted(bad)}, outside the five")
        # An area is required, and checked against the vocabulary. A missing one
        # would file an issue that the area axis cannot see, which is exactly the
        # state this axis was added to end. A typo would be worse than missing:
        # it becomes a real GitHub label with one issue on it, and reads as a
        # tenth area rather than as the mistake it is.
        if not area:
            raise ValueError(f"{path} — {item_id} has no `Area:` in its field line")
        if area not in AREAS:
            raise ValueError(f"{path} — {item_id} has area {area!r}, outside {sorted(AREAS)}")
        if status not in STATUSES:
            raise ValueError(f"{path} — {item_id} has status {status!r}")
        if size not in SIZES:
            raise ValueError(f"{path} — {item_id} has size {size!r}")
        if priority not in PRIORITIES:
            raise ValueError(f"{path} — {item_id} has priority {priority!r}")

        # `— **Done 2026-09-01**` in a heading is the file's own marker; the
        # status field already carries it, so it does not need repeating in an
        # issue title that GitHub will show as closed anyway.
        title = re.sub(r"\s+—\s+\*\*Done [\d-]+\*\*$", "", raw_title)
        title = title.replace("**", "")

        items.append(
            {
                "id": item_id,
                "title": title,
                "source": str(path),
                "group": group,
                "status": status,
                "priority": priority,
                "size": size,
                "area": area,
                "labels": labels,
                "state": "closed" if status == "Done" else "open",
                "body_md": _to_headings(body),
                "heading_line": i + 1,
            }
        )

    return items


def build_manifest() -> list[dict[str, Any]]:
    """Read both English files and resolve the two duplicate pairs.

    Returns:
        The items that become issues, one per piece of work.

    Raises:
        ValueError: If a duplicate's partner is missing, which would mean the
            drop silently lost work rather than de-duplicating it.
    """
    items: list[dict[str, Any]] = []
    for source in SOURCES:
        items.extend(parse_file(Path(source)))

    by_id = {item["id"]: item for item in items}

    for dropped, kept in {**DROP_IDS, **FOLD_IDS}.items():
        if dropped in by_id and kept not in by_id:
            raise ValueError(f"{dropped} would be dropped in favour of {kept}, which does not exist")

    # Fold before dropping, so the folded text is added to a surviving item.
    for folded, kept in FOLD_IDS.items():
        if folded not in by_id:
            continue
        source = by_id[folded]
        by_id[kept]["body_md"] += (
            f"\n\n---\n\n### Also filed here — {folded}\n\n"
            f"`{source['source']}` records the same work seen from the corpus side, and says so "
            f"itself: do it here rather than twice. Its framing is kept because it is not in this "
            f"item otherwise — **the corpus is fine, the bridge is not.** The OKF corpus already "
            f"is the HIV corpus (333 documents, every metapath from an HIV/AIDS anchor); what "
            f"fails is the crossing from a corpus concept to a cohort column.\n\n"
            f"{source['body_md']}"
        )
        by_id[kept].setdefault("folds", []).append(folded)

    dropped_ids = set(DROP_IDS) | set(FOLD_IDS)
    kept = [item for item in items if item["id"] not in dropped_ids]

    for item in kept:
        item["issue_body"] = render_body(item)
    return kept


def render_body(item: dict[str, Any]) -> str:
    """Render an item's GitHub issue body.

    The footer is the point of the file's own promise — an issue that cannot say
    which line of which file it came from cannot be checked against it.

    Args:
        item: A parsed item.

    Returns:
        Markdown for the issue body.
    """
    folds = "".join(f" · folds **{f}**" for f in item.get("folds", []))
    return (
        f"{item['body_md']}\n\n"
        f"---\n\n"
        f"From `{item['source']}` · **{item['id']}** · {item['group']} · "
        f"Status `{item['status']}` · Priority `{item['priority']}` · Size `{item['size']}`{folds}\n"
    )


# --------------------------------------------------------------------------- #
# Talking to GitHub
# --------------------------------------------------------------------------- #


def gh(*args: str, check: bool = True) -> str:
    """Run a `gh` command and return its stdout.

    Args:
        *args: Arguments after `gh`.
        check: Raise on a non-zero exit.

    Returns:
        Stripped stdout.

    Raises:
        RuntimeError: If the command fails and `check` is set.
    """
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def existing_issues() -> dict[str, dict[str, Any]]:
    """Map item id to the issue that already exists for it.

    The id is read off the title prefix (`A-02 · …`), which is why the prefix is
    part of the title and not only the body: it is what makes a second run safe.

    Returns:
        `{"A-02": {"number": 7, "state": "OPEN", "title": "..."}}`.
    """
    raw = gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "300",
             "--json", "number,title,state")
    found: dict[str, dict[str, Any]] = {}
    for issue in json.loads(raw or "[]"):
        head = issue["title"].split(" · ", 1)[0].strip()
        if re.fullmatch(r"[A-Z]+-\d+", head):
            found[head] = issue
    return found


def cmd_plan(manifest: list[dict[str, Any]]) -> int:
    """Write the manifest and print what a `create` run would do.

    Nothing is created. 45 issues is not a step to take on trust.

    Args:
        manifest: The resolved items.

    Returns:
        Process exit code.
    """
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    opened = [i for i in manifest if i["state"] == "open"]
    closed = [i for i in manifest if i["state"] == "closed"]
    labels: dict[str, int] = {}
    areas: dict[str, int] = {}
    for item in manifest:
        for label in item["labels"]:
            labels[label] = labels.get(label, 0) + 1
        areas[item["area"] or "(none)"] = areas.get(item["area"] or "(none)", 0) + 1

    print(f"manifest  {MANIFEST_PATH.relative_to(_ROOT)}")
    print(f"items     {len(manifest)}  ({len(opened)} open, {len(closed)} closed)")
    print(f"dropped   {', '.join(f'{d} → {k}' for d, k in {**DROP_IDS, **FOLD_IDS}.items())}")
    print(f"labels    {', '.join(f'{k} {v}' for k, v in sorted(labels.items()))}")
    # Printed largest-first, because the question this line answers is "does any
    # one area hold most of the board", and sorting by name hides that.
    print(f"areas     {', '.join(f'{k} {v}' for k, v in sorted(areas.items(), key=lambda kv: -kv[1]))}")
    print(f"first     {manifest[0]['id']} · {manifest[0]['title'][:60]}")
    print()
    for item in manifest:
        mark = "x" if item["state"] == "closed" else " "
        print(f"  [{mark}] {item['id']:<8} {item['priority']} {item['size']:<2} "
              f"{','.join(item['labels']):<18} {item['title'][:64]}")
    return 0


def cmd_create(manifest: list[dict[str, Any]]) -> int:
    """Create every issue that does not exist yet, and close the finished ones.


    asks for it: "this item stays at the top of the list until it closes."

    Args:
        manifest: The resolved items.

    Returns:
        Process exit code.
    """
    have = existing_issues()
    created = skipped = 0

    ordered = [i for i in manifest if i["state"] == "open"] + [i for i in manifest if i["state"] == "closed"]
    for item in ordered:
        if item["id"] in have:
            skipped += 1
            print(f"  skip   {item['id']:<8} #{have[item['id']]['number']}")
            continue

        args = ["issue", "create", "--repo", REPO,
                "--title", f"{item['id']} · {item['title']}",
                "--body", item["issue_body"]]
        for label in issue_labels(item):
            args += ["--label", label]
        url = gh(*args)
        number = int(url.rstrip("/").rsplit("/", 1)[-1])
        item["issue"] = number
        created += 1
        print(f"  create {item['id']:<8} #{number}")

        if item["state"] == "closed":
            # A closing comment, not a bare close. A board that says "done" and
            # not "done by what" is the thing the backlog was written against.
            gh("issue", "close", str(number), "--repo", REPO, "--reason", "completed",
               "--comment", f"Finished before this board existed. The record is in "
                            f"`{item['source']}` under **{item['id']}**, including how it was "
                            f"checked. Filed and closed together so the month does not read empty.")

    for item in manifest:
        if "issue" not in item and item["id"] in have:
            item["issue"] = have[item["id"]]["number"]

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\ncreated {created}, skipped {skipped}")
    return 0


def cmd_link(manifest: list[dict[str, Any]]) -> int:
    """Append issue numbers to the id references inside issue bodies.

    The number is APPENDED, never substituted — `**A-03** (#7)`. The id is what
    ties an issue back to the file it came from; substituting would break that
    link in both directions.

    Args:
        manifest: The resolved items, with issue numbers.

    Returns:
        Process exit code.
    """
    numbers = {item["id"]: item["issue"] for item in manifest if item.get("issue")}
    numbers.update({dropped: numbers[kept] for dropped, kept in {**DROP_IDS, **FOLD_IDS}.items()
                    if kept in numbers})
    updated = 0

    for item in manifest:
        if not item.get("issue"):
            continue
        body = item["issue_body"]

        def add_number(match: re.Match[str]) -> str:
            ref = match.group(1)
            if ref == item["id"] or ref not in numbers:
                return match.group(0)
            # Already linked on a previous run.
            if body[match.end() : match.end() + 12].lstrip("*` ").startswith("(#"):
                return match.group(0)
            return f"{match.group(0)} (#{numbers[ref]})"

        linked = _ID_REF_RE.sub(add_number, body)
        if linked == body:
            continue
        gh("issue", "edit", str(item["issue"]), "--repo", REPO, "--body", linked)
        item["issue_body"] = linked
        updated += 1
        print(f"  link   {item['id']:<8} #{item['issue']}")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nlinked {updated}")
    return 0


def issue_labels(item: dict[str, Any]) -> list[str]:
    """Every label an issue carries: its kind, and its area if it has one.

    One function so `create` and `labels` cannot disagree about what an issue is
    supposed to have — the two would otherwise drift the first time either grew a
    condition.

    Args:
        item: A manifest entry.

    Returns:
        Label names, kind first.
    """
    return [*item["labels"], *([f"area:{item['area']}"] if item.get("area") else [])]


def cmd_labels(manifest: list[dict[str, Any]]) -> int:
    """Make the `area:*` labels exist, then put the right one on every issue.

    This is the step that carries the area axis from the backlog files onto
    GitHub. It exists separately from `create` because `create` skips any id that
    already has an issue, by design (`:22-26`) — so on a board that is already
    filed, `create` would never apply an area to anything.

    IDEMPOTENT, like every other subcommand. `gh label create --force` updates a
    label that exists instead of failing, and an issue that already carries its
    area is left alone rather than edited to the same value.

    Args:
        manifest: The resolved items, with issue numbers.

    Returns:
        Process exit code.
    """
    for name, description in AREAS.items():
        gh("label", "create", f"area:{name}", "--repo", REPO,
           "--color", AREA_COLOR, "--description", description, "--force")
    print(f"labels    {len(AREAS)} area:* labels exist\n")

    # One read of what is already on GitHub, rather than one per issue. 48 issues
    # is 48 round trips otherwise, and the answer is the same for all of them.
    current = {
        issue["title"].split(" · ", 1)[0].strip(): {label["name"] for label in issue["labels"]}
        for issue in json.loads(gh("issue", "list", "--repo", REPO, "--state", "all",
                                   "--limit", "300", "--json", "title,labels") or "[]")
    }

    applied = unchanged = 0
    for item in manifest:
        if not item.get("issue") or not item.get("area"):
            continue
        wanted = f"area:{item['area']}"
        if wanted in current.get(item["id"], set()):
            unchanged += 1
            continue
        gh("issue", "edit", str(item["issue"]), "--repo", REPO, "--add-label", wanted)
        applied += 1
        print(f"  label  {item['id']:<8} #{item['issue']:<3} {wanted}")

    missing = [i["id"] for i in manifest if i.get("issue") and not i.get("area")]
    if missing:
        print(f"\n  !      no area on {len(missing)}: {', '.join(missing)}")
    print(f"\napplied {applied}, already correct {unchanged}")
    return 0


def _project_number() -> str:
    """Find the `Memstara` project's number under the owner.

    Returns:
        The project number as a string.

    Raises:
        RuntimeError: If no project by that title exists yet.
    """
    raw = gh("project", "list", "--owner", PROJECT_OWNER, "--format", "json")
    for project in json.loads(raw)["projects"]:
        if project["title"] == PROJECT_TITLE:
            return str(project["number"])
    raise RuntimeError(f"no project titled {PROJECT_TITLE!r} under {PROJECT_OWNER}")


def cmd_board(manifest: list[dict[str, Any]]) -> int:
    """Add every issue to the project and set `Status`, `Priority`, `Size` and `Area`.

    `Area` is the only one of the four this script creates. The other three came
    with GitHub's project template; nothing else was going to supply an Area
    field, and a board that can filter by area but not group by it does half the
    job the axis exists for.

    Args:
        manifest: The resolved items, with issue numbers.

    Returns:
        Process exit code.
    """
    number = _project_number()

    def read_fields() -> dict[str, Any]:
        return {f["name"]: f for f in json.loads(
            gh("project", "field-list", number, "--owner", PROJECT_OWNER, "--format", "json"))["fields"]}

    fields = read_fields()
    if "Area" not in fields:
        # Created in the vocabulary's own order, which is the order the options
        # appear in on the board. Alphabetical would put `blackboard` first and
        # `viewer-web` last for no reason a reader could recover.
        gh("project", "field-create", number, "--owner", PROJECT_OWNER,
           "--name", "Area", "--data-type", "SINGLE_SELECT",
           "--single-select-options", ",".join(AREAS))
        print(f"field     created Area with {len(AREAS)} options")
        fields = read_fields()

    project_id = json.loads(
        gh("project", "view", number, "--owner", PROJECT_OWNER, "--format", "json"))["id"]

    on_board = {}
    for entry in json.loads(gh("project", "item-list", number, "--owner", PROJECT_OWNER,
                               "--format", "json", "--limit", "300"))["items"]:
        head = entry.get("title", "").split(" · ", 1)[0].strip()
        if re.fullmatch(r"[A-Z]+-\d+", head):
            on_board[head] = entry["id"]

    def option_id(field_name: str, value: str) -> str | None:
        """Resolve a single-select option's id, tolerating the `P0 — …` wording."""
        for option in fields.get(field_name, {}).get("options", []):
            if option["name"] == value or option["name"].startswith(f"{value} "):
                return option["id"]
        return None

    added = 0
    for item in manifest:
        if not item.get("issue"):
            continue
        item_id = on_board.get(item["id"])
        if item_id is None:
            url = f"https://github.com/{REPO}/issues/{item['issue']}"
            item_id = json.loads(gh("project", "item-add", number, "--owner", PROJECT_OWNER,
                                    "--url", url, "--format", "json"))["id"]
            added += 1

        for field_name, value in (("Status", item["status"]),
                                  ("Priority", item["priority"]),
                                  ("Size", item["size"]),
                                  ("Area", item["area"])):
            if not value:
                continue   # an item with no area yet; `labels` reports which
            field = fields.get(field_name)
            option = option_id(field_name, value)
            if field is None or option is None:
                print(f"  !      {item['id']:<8} {field_name} has no option for {value!r}")
                continue
            gh("project", "item-edit", "--id", item_id, "--project-id", project_id,
               "--field-id", field["id"], "--single-select-option-id", option)
        print(f"  board  {item['id']:<8} #{item['issue']}")

    print(f"\nadded {added}, fields set on {sum(1 for i in manifest if i.get('issue'))}")
    return 0


#: `sync` writes this into every comment it leaves and reads it back to decide
#: whether an issue has already been told. A marker in the text, not a record kept
#: on this side, so the answer survives losing `outputs/` and cannot drift from
#: what is actually on GitHub.
SYNC_MARKER = "<!-- memstara: memo-05-path-sync -->"

#: The commit that repaired the paths in the tracked documents.
SYNC_COMMIT = "c888120"


def _moves() -> dict[str, str]:
    """Load `repair_citations.py`'s move table — old path -> new path.

    Read from that file rather than copied, because two copies of a move table
    is the same failure this whole item was about.

    Returns:
        The `MOVES` mapping.
    """
    import importlib.util

    path = Path(__file__).with_name("repair_citations.py")
    spec = importlib.util.spec_from_file_location("_repair_citations", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MOVES


def cmd_sync(manifest: list[dict[str, Any]], only: str = "", dry_run: bool = False) -> int:
    """Comment on every issue whose text names a file the restructure moved.

    ONE comment per issue, and the issue itself is never edited. The 45 issues
    are the record of what was true when they were filed — rewriting them is the

    records. A comment adds today's answer without touching that record.

    Args:
        manifest: The resolved items, with issue numbers.
        only: Comma-separated ids to restrict to, e.g. `MEMO-05`. Empty means all.
        dry_run: Print what would be posted and post nothing.

    Returns:
        Process exit code.
    """
    moves = _moves()
    wanted = {i.strip() for i in only.split(",") if i.strip()}
    posted = clean = already = 0

    # The manifest on disk is whatever `plan` last wrote, and `plan` does not know
    # any issue numbers — only `create` fills them in. Asking GitHub costs one call
    # and means `sync` works off a freshly planned manifest as well as a created one.
    on_github = existing_issues()

    for item in manifest:
        number = item.get("issue") or on_github.get(item["id"], {}).get("number")
        if not number or (wanted and item["id"] not in wanted):
            continue

        raw = gh("issue", "view", str(number), "--repo", REPO, "--json", "body,comments")
        issue = json.loads(raw)
        if any(SYNC_MARKER in (c.get("body") or "") for c in issue.get("comments", [])):
            already += 1
            continue

        # A name counts as found only where it is written as a path — with a line
        # number, or with the directory it used to sit in. A bare `blackboard.py`
        # is still the file's name and says nothing stale.
        body = issue.get("body") or ""
        found = {old: new for old, new in moves.items()
                 if re.search(rf"(?<![\w/.-]){re.escape(old)}(?=:\d|[^\w.]|$)", body)
                 and (f"{old}:" in body or "/" in old or old not in
                      {"blackboard.py", "logging_setup.py", "preflight.py", "debug_harness.py"})}
        if not found:
            clean += 1
            continue

        rows = "\n".join(f"| `{old}` | `{new}` |" for old, new in sorted(found.items()))
        comment = (
            f"{SYNC_MARKER}\n"
            f"**The paths in this issue are from before the 2026-09-01 restructure.**\n\n"
            f"Every module that sat at the repository root now lives under "
            f"`src/memstara/`. Commit `{SYNC_COMMIT}` repaired the citations in the "
            f"tracked documents; the full table of where each file landed is in "

            f"What this issue names, and where it is now:\n\n"
            f"| Written here | Now |\n|---|---|\n{rows}\n\n"
            f"Line numbers still hold for the files that moved untouched. The issue "
            f"text is left exactly as filed — it is the record of what was true then, "
            f"and this comment is the only thing that dates."
        )

        if dry_run:
            print(f"\n──── #{number} · {item['id']} ────\n{comment}")
        else:
            gh("issue", "comment", str(number), "--repo", REPO, "--body", comment)
            print(f"  sync   {item['id']:<8} #{number}  ({len(found)} names)")
        posted += 1

    verb = "would comment on" if dry_run else "commented on"
    print(f"\n{verb} {posted}; {clean} name nothing that moved; {already} already done")
    return 0


def cmd_annotate(manifest: list[dict[str, Any]]) -> int:
    """Write `**Issue** — #N` under every item's field line, in all four files.

    The `_KR` editions are annotated too. They declare themselves full editions —
    same items, same ids, same order — and an edition missing the issue numbers
    its original carries is no longer that.

    Args:
        manifest: The resolved items, with issue numbers.

    Returns:
        Process exit code.
    """
    numbers = {item["id"]: item["issue"] for item in manifest if item.get("issue")}
    lines_by_id = {item_id: f"**Issue** — #{number}" for item_id, number in numbers.items()}
    # The two duplicates point at the issue that survived them, and say whose it
    # is — a bare number under `MEMO-08` would read as MEMO-08's own issue.
    for dropped, kept in {**DROP_IDS, **FOLD_IDS}.items():
        if kept in numbers:
            numbers[dropped] = numbers[kept]
            lines_by_id[dropped] = f"**Issue** — #{numbers[kept]}, filed as **{kept}**"

    for name in ANNOTATE_FILES:
        path = _ROOT / name
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        written = 0
        current: str | None = None

        for i, line in enumerate(lines):
            out.append(line)
            match = _ITEM_RE.match(line)
            if match:
                current = match.group(1)
                continue
            if current and line.startswith("`Status:"):
                # The line written below is preceded by a blank one, so looking
                # only at `i + 1` would see the blank and write a second copy.
                ahead = i + 1
                while ahead < len(lines) and not lines[ahead].strip():
                    ahead += 1
                already = ahead < len(lines) and lines[ahead].startswith("**Issue** — ")
                if not already and current in numbers:
                    out.append("")
                    out.append(lines_by_id[current])
                    written += 1
                current = None

        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"  {name:<20} {written} written")
    return 0


def main() -> int:
    """Parse arguments and dispatch.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command",
                        choices=("plan", "create", "labels", "link", "board", "annotate", "sync"))
    parser.add_argument("--only", default="",
                        help="sync: restrict to these ids, comma-separated")
    parser.add_argument("--dry-run", action="store_true",
                        help="sync: print the comments and post nothing")
    args = parser.parse_args()

    if args.command in ("plan", "create"):
        manifest = build_manifest()
        if args.command == "create" and MANIFEST_PATH.exists():
            # Carry forward the numbers a previous run recorded, so `create`
            # after an interruption knows what it already made.
            previous = {i["id"]: i.get("issue") for i in json.loads(MANIFEST_PATH.read_text())}
            for item in manifest:
                if previous.get(item["id"]):
                    item["issue"] = previous[item["id"]]
    else:
        if not MANIFEST_PATH.exists():
            print(f"no manifest at {MANIFEST_PATH} — run `plan` first", file=sys.stderr)
            return 1
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    if args.command == "sync":
        return cmd_sync(manifest, only=args.only, dry_run=args.dry_run)

    return {"plan": cmd_plan, "create": cmd_create, "labels": cmd_labels, "link": cmd_link,
            "board": cmd_board, "annotate": cmd_annotate}[args.command](manifest)


if __name__ == "__main__":
    raise SystemExit(main())
