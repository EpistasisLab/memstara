#!/usr/bin/env python3
"""Core's OKF server, plus a reading surface that suits a real literature bundle.

Registered in place of `python -m motoro.mcp_servers.okf`. Core's tools are run
unchanged — nothing here reimplements them, and nothing here removes them. Two things
are added on top:

1. One PyYAML behaviour is turned off so `list_concepts` stops failing (below).
2. Three reading tools — `okf_list_domains`, `okf_search`, `okf_read` — that read the
   same bundle the way a consumer of it needs to. See "The reading surface" further
   down for what core's three read tools do to a 142-paper bundle.

The defect
----------
`list_concepts` fails on any bundle core did not write itself::

    Error executing tool list_concepts: Object of type datetime is not JSON serializable

Three steps get there:

1. A concept file carries a timestamp, unquoted, which is ordinary YAML::

       generated:
         at: 2026-08-10T00:00:00Z

2. YAML has a timestamp type, so `safe_load` returns a `datetime` — not a string.
3. `list_concepts` copies `generated`, `verified` and `status` straight out of the
   frontmatter (okf.py:271-272) and hands the result to `json.dumps` (okf.py:276).
   JSON has no date type and no `default=` was given, so it raises.

`search_concepts` returns only id/type/title/tags (okf.py:305-312), which is why search
works and only the listing breaks — the contrast is what identified the cause.

Core never hits this on its own output: it writes `datetime.now(UTC).isoformat()`, a
*string* (okf.py:373), and `yaml.safe_dump` quotes it (okf.py:136), so it round-trips as
a string. The failure needs a bundle written by somebody else — which is every bundle
that matters here. Measured on the sample bundle: 29 of 31 files carry such a timestamp,
and one is enough, because `json.dumps` serialises the whole result at once.

The fix here
------------
Remove PyYAML's implicit resolver for timestamps, so an unquoted ISO date loads as the
string it was written as. That removes the `datetime` at the source rather than patching
each tool that trips over one, so no core logic is copied and every tool benefits.

Nothing else changes: integers, booleans and quoted strings resolve exactly as before,
and JSON has no date type anyway, so a consumer could not have received one.

Report upstream regardless — `json.dumps(..., default=str)` at okf.py:276 would fix it
for everyone. This only fixes it for us.

==============================================================================
 How to read this file
==============================================================================

 This is the **knowledge-source (OKF) tool server**. It leaves core's own OKF
 server running as it is and lays three reading tools on top. It is the window
 through which a literature bundle (a set of markdown files) is listed, searched,
 and opened one paper at a time.

 The main functions and classes
 ------------------------------
 disable_yaml_timestamps()  Turns off YAML's habit of converting dates into
                            datetimes. Removes at the root what was killing
                            core's `list_concepts`.
 _Doc                       One document: path, domain, address, frontmatter,
                            body, and the tokens used for search.
 _text / _tag_list          Coerce a frontmatter value into a safe string / a
                            list of tags.
 _tokens                    Split text into search "words". Not substrings.
 _sections                  Split a body into sections at each `# heading`.
 _signature                 A cheap stamp (file mtimes) for telling whether the
                            bundle changed.
 _load(root)                Read the whole bundle into a document list plus a
                            list of files that were skipped.
 _idf                       Per-word weight. A word present in every document
                            scores low.
 _index                     Every label one document answers to (address, PMID,
                            filename).
 _split                     Split on commas and strip whitespace.
 okf_list_domains()  [tool]  The domains and how many documents each holds.
                             The first thing to call.
 okf_search()        [tool]  Search title, tags, description and journal.
                             The body is not looked at.
 okf_read()          [tool]  Open a document whole, or one section of it.

 Easy things to miss
 -------------------
 1. Listing walks **only inside the domain folders**. It does not glob the root
    wholesale. That is why reviewer's hiv-suppression bundle comes out as 142 papers
    rather than 152 — the ten that drop out are shelf labels such as `index.md`,
    not evidence documents.
 2. But **flat bundles** exist too (no domain folders, just .md files sitting in
    the root). This project's synthetic bundle and the NHANES bundle are both
    like that. Under a folders-only rule they come out as **zero** documents, and
    no error is raised — they are just silently empty. So a branch was added
    later that reads the root as a single domain when the folders yield nothing
    (`_load`).
 3. Search **does not index the body.** It looks only at title 3.0 · tags 2.0 ·
    description 1.0 · journal 1.0 — meaning it trusts only the fields an author
    filled in on purpose.
 4. `export_safe` is written in the bundle as a quoted `"false"`. In Python a
    non-empty string is **truthy**, so `if export_safe:` always passes. This file
    therefore makes no judgement about it and returns **the string exactly as
    written**.
"""

from __future__ import annotations

import dataclasses  # used to make _Doc a fixed box that only carries values
import json         # every tool returns a JSON string
import math         # the word weight (idf) uses a logarithm
import pathlib      # file paths. Used in place of os.path
import re           # used for splitting words and for frontmatter patterns
from typing import Any

import yaml         # the frontmatter is YAML

#: The name of the tag PyYAML attaches when it decides "this is a date". Below,
#: only the rules that attach this tag are picked out and removed.
_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


def disable_yaml_timestamps() -> int:
    """Stop `yaml.safe_load` from turning ISO dates into datetimes. Returns the count.

    An unquoted date (`2026-08-10T00:00:00Z`) is left as **the string it was
    written as** instead of becoming a Python `datetime`. The number of rules
    removed is returned (usually 2 — a date can begin with several different
    characters, so the rule is registered in several slots).

    PyYAML keeps a table of "first character -> the list of type rules a value
    starting with that character could match". This walks that table slot by slot
    and swaps in a new list with the date rule left out. A new list is built
    rather than the original edited in place, so that nothing being iterated over
    is modified while the loop is running.
    """
    removed = 0
    # Taken as a list(...) snapshot first — the original table is modified while
    # the loop runs.
    for first_char, resolvers in list(yaml.SafeLoader.yaml_implicit_resolvers.items()):
        # Keep every rule that is not the timestamp tag.
        kept = [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP_TAG]
        removed += len(resolvers) - len(kept)  # count how many were dropped
        yaml.SafeLoader.yaml_implicit_resolvers[first_char] = kept
    return removed


# This is a child process, so the parent's debugger cannot reach it. It waits for a
# debugger only when MEMSTARA_DEBUGPY contains "okf" — otherwise it does nothing at
# all. See src/memstara/mcp_servers/debug_hook.py.
#
# The E402 is silenced rather than fixed: this import belongs after
# disable_yaml_timestamps() is defined and before core's server is imported,
# which is the ordering the next comment block describes. Moving it to the top of
# the file would satisfy the linter and break what the ordering is for.
from memstara.mcp_servers.debug_hook import quiet_child, wait_for_debugger  # noqa: E402

quiet_child()          # silences the three startup messages a child prints
wait_for_debugger("okf")

# Before importing core's server: it parses nothing at import time, but ordering this
# way means the resolver is already gone no matter when the first parse happens.
# It amounts to removing the ordering dependency rather than relying on it.
disable_yaml_timestamps()

# Core's own helpers are imported rather than copied. `_bundle_root` reads the same
# environment variable with the same error message, and `_parse_concept_file` uses the
# same frontmatter regex — reimplementing either would let the two drift apart while
# both claim to serve "the bundle".
#
# `mcp` is the server object on which core has already registered its own tools.
# Three more are attached to it below — which is how core's tools and this file's
# tools come out of one server together.
from motoro.mcp_servers.okf import (  # noqa: E402
    OKFError,
    _bundle_root,
    _parse_concept_file,
    mcp,
)

# --------------------------------------------------------------------------- #
#  The reading surface
# --------------------------------------------------------------------------- #
#
# Core's read tools were written against bundles core itself writes. Measured against
# `shared/hiv-suppression/okf` — 142 papers in 8 domain folders, produced by OKF
# Loremaster — three of them do the wrong thing:
#
#   * `list_concepts` enumerates with `root.rglob("*.md")`, so it reports 152 documents.
#     The extra ten are structure: eight per-domain `index.md`, plus `predictors.md` and
#     `search.md` at the root. The agent reads a shelf label as if it were evidence.
#   * `search_concepts` matches a substring against title + description + **body**. On
#     this bundle `"art"` matches 132 of 142 papers, because of `heart`, `start` and
#     `particular`. `"ai"` and `"n"` match all 142. A search that returns everything has
#     not searched.
#   * `get_concept` returns the whole body. Median body here is 6,678 characters and the
#     longest is 37,933; the 142 bodies together are roughly 271,000 tokens. Opening a
#     handful fills the window with paper text when what was wanted was a conclusion.
#
# The three tools below are the same three afc-forge binds for its `basic` agency
# profile. That set is adopted rather than invented: it is already the minimum that
# works, and matching it means a bundle behaves the same on both sides.
#
# afc-forge is deliberately NOT imported. Its own reader says why, about its own
# situation: the bundle is a contract between two programs that must be able to change
# independently, and borrowing the other side's parser can only ever prove that the
# bundle agrees with itself. The approach is taken; the code is written here.

#: Filenames inside a domain folder that are not counted as documents. Such a file
#: is a cover sheet saying what the folder contains, not an evidence document.
_DOMAIN_INDEX = "index.md"

#: Names (without the extension) at the root of a flat bundle that are not counted
#: as documents.
#:
#: These are structure, not evidence. The list follows the convention of bundles
#: Loremaster produces, and adds README, which is common in hand-built bundles.
_ROOT_RESERVED = frozenset({"index", "log", "predictors", "search", "README", "readme"})

#: The curated fields a query is matched against, and what each is worth. These are the
#: fields an author filled in on purpose, so a hit means the bundle says this paper is
#: about that — not that the word appeared once in an abstract. A title match is a
#: stronger statement of aboutness than a journal match, on any bundle.
_FIELD_WEIGHTS = {"title": 3.0, "tags": 2.0, "description": 1.0, "journal": 1.0}

#: What a search returns unasked, and the ceiling it may be raised to. A request above
#: the ceiling is clamped and says so, so breadth can be taken without asking anybody.
#: Clamping silently would leave the caller believing it had seen everything.
_DEFAULT_K = 8
_MAX_K = 20

#: Words, not substrings. A run of letters and digits counts as one word. This is the
#: whole reason `"art"` stops matching `"heart"`.
_TOKEN = re.compile(r"[a-z0-9]+")

#: Common words dropped from a search (the, of, is and so on). Small and closed on
#: purpose. A long stopword list starts deciding what is a concept.
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the their "
    "there these this to was were what when which who will with".split()
)

#: A single-hash heading opens a body section. A `##` inside one belongs to it, which is
#: what lets a section carry sub-structure. Every paper in the HIV bundle carries the
#: same five: Bottom line / Predictors reported / Null or non-significant findings /
#: Vocabulary hints / Caveats.
_HEADING = "# "


@dataclasses.dataclass(frozen=True)
class _Doc:
    """One evidence document: where it is, what it says about itself, and its body.

    `frozen=True` means the values cannot be changed once it is built. These are
    held in a cache and handed out many times over, so this is what stops one of
    them being quietly altered somewhere.

    The fields:
      path         where the file actually sits
      domain       the name of the topic folder this document belongs to
      address      the id these tools hand out. "domain/stem" when there are
                   folders, "stem" in a flat bundle
      fields       everything written in the frontmatter (YAML) — title, tags,
                   journal, PMID and the rest
      body         the whole body below the frontmatter
      field_tokens the words, pre-split for search. Splitting on every search
                   would repeat the work once per document, so it is done once
                   at load time
    """

    path: pathlib.Path
    domain: str
    address: str  # "domain/stem" — the id this surface hands out
    fields: dict[str, Any]
    body: str
    field_tokens: dict[str, frozenset[str]]

    @property
    def summary(self) -> dict[str, Any]:
        """The catalogue row. Scanned many at a time, so it carries no body.

        Dozens of these travel at once, so the body is left out deliberately. When
        the body is wanted, okf_read opens it separately.
        """
        f = self.fields
        return {
            "id": self.address,
            "title": _text(f.get("title")),
            "domain": self.domain,
            "tags": _tag_list(f.get("tags")),
            "journal": _text(f.get("journal")),
            "published": _text(f.get("published")),
            "strength": _text(f.get("strength")),
            "n": _text(f.get("n")),
            "pmid": _text(f.get("pmid")),
        }


def _text(value: Any) -> str:
    """A frontmatter value as a string, never a bool and never None.

    Values arrive as whatever YAML made of them. Returning the raw object would put a
    `None` or a `dict` into JSON where callers expect a string, and `str(None)` would
    put the word "None" on screen as if it were data.

    The frontmatter is written by hand, so there is no telling what a value will be
    read as — it may be empty, a list, or a table. Anything absent or of the wrong
    shape therefore comes back as an empty string.
    """
    if value is None:
        return ""          # no value -> blank
    if isinstance(value, (list, dict)):
        return ""          # a list or a table does not belong here -> blank
    return str(value).strip()


def _tag_list(value: Any) -> list[str]:
    """Turn tags into a list.

    Tags are written two ways in the frontmatter — as a YAML list, or as a single
    line like `a, b, c`. Both are accepted and give the same result. Empty pieces
    are dropped.
    """
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value or "").split(",") if p.strip()]


def _tokens(text: str) -> frozenset[str]:
    """Split text into a bag of words for searching.

    Lowercase it, take only the runs of letters and digits, and throw away the
    common words (_STOP) and the single characters. Order and count are discarded
    and only **which words were there** is kept — that is all a search needs, and
    two bags can be compared with a single intersection.
    """
    return frozenset(t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1)


def _sections(body: str) -> list[tuple[str, str]]:
    """`(heading, text)` for each `# ` section, in order. Preamble is not a section.

    The part before the first `#` is not counted as a section — it has no name, so
    there would be no way to point at it with `section=` either.
    """
    out: list[tuple[str, str]] = []
    heading, buf = "", []      # the heading and the lines of the section being gathered
    for line in body.splitlines():
        if line.startswith(_HEADING):
            if heading:
                # A new heading, so close the section gathered up to this point.
                out.append((heading, "\n".join(buf).strip()))
            heading, buf = line[len(_HEADING) :].strip(), []
        else:
            buf.append(line)
    if heading:
        out.append((heading, "\n".join(buf).strip()))  # close the last section
    return out


def _signature(root: pathlib.Path) -> tuple[tuple[str, int], ...]:
    """A cheap stamp of the bundle's current state — stat only, no reads.

    The bundle is re-read on every tool call otherwise, which on this bundle is a
    megabyte of markdown per call. Caching on the path alone would be wrong: core's
    `create_concept` and `update_concept` are still registered on this same server, so
    a bundle CAN change under us mid-run. Watching the path alone, we would not know
    it had changed and would keep handing out the old content.

    Only the names and the last-modified times are looked at; when the stamp is the
    same as last time, nothing is re-read and the cache is used.
    """
    stamps = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith((".", "_")):
            continue   # skip hidden folders and scratch folders beginning with `_`
        for md in sorted(folder.glob("*.md")):
            # st_mtime_ns is the modification time in nanoseconds. Finer than whole
            # seconds, so two edits inside the same second are still told apart.
            stamps.append((str(md), md.stat().st_mtime_ns))
    return tuple(stamps)


#: bundle path -> (stamp, documents, skipped files). A different stamp throws it away
#: and re-reads.
_CACHE: dict[str, Any] = {}


def _load(root: pathlib.Path) -> tuple[list[_Doc], list[dict[str, str]]]:
    """Every evidence document in the bundle, and every file passed over, by name.

    Enumeration is one level of domain folders — never a glob from the root. A producer
    that drops a root-level sidecar (`predictors.md`, `search.md`) would otherwise be
    read as a document with no domain, and a bundle that is entirely correct would come
    back ten documents too large.

    What was NOT read is returned alongside what was. Silently skipping a malformed file
    is how a bundle comes back short while looking healthy — the caller sees fewer
    documents and no reason to doubt the number. So what was skipped is handed back
    by name, with the reason attached.

    Both layouts are read
    ---------------------
    A bundle that has domain folders (reviewer's `hiv-suppression`, for one) is read by
    the rule above.

    But **the bundles this project produces are flat** — `.md` files sit in the root
    with no domain folder, and there is no `domain` field either. Both the synthetic
    bundle (31 documents) and the NHANES one (21) are like this. Under a folders-only
    rule such a bundle comes back as **0 documents**, and it does so quietly. We
    actually built them that way and did not notice for a while.

    So when nothing at all is found in the folders, **the root is read as a single
    domain.** Only in that case is `domain` dropped from the required fields — with
    no folders there is no name to match it against. `title` is still required. It is
    most of the search surface.
    """
    key = str(root)
    sig = _signature(root)
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == sig:
        return cached[1], cached[2]   # same stamp -> done without touching a file

    docs: list[_Doc] = []                  # the documents accepted as evidence
    skipped: list[dict[str, str]] = []     # files that could not be read, or broke a rule

    # --- Branch 1: bundles with domain folders (reviewer's hiv-suppression, for one) ---
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith((".", "_")):
            continue
        for md in sorted(folder.rglob("*.md")):  # rglob: descends into subfolders too
            rel = md.relative_to(root).as_posix()   # short path, for error messages
            if md.name == _DOMAIN_INDEX:
                continue  # the shelf label, not evidence
            try:
                # core's parser. Splits the file into frontmatter (a dict) and body (a string).
                fields, body = _parse_concept_file(md)
            except (OKFError, OSError, UnicodeDecodeError) as exc:
                # One broken file must not stop the whole bundle. What could not be
                # read, and why, is always recorded instead.
                skipped.append({"path": rel, "why": str(exc)})
                continue
            title = _text(fields.get("title"))
            # domain: with no such field, the top-level folder name is used as the domain
            # (reviewer's OKF writes mechanism_family: instead of a domain: field)
            domain = folder.name
            if not title:
                skipped.append({"path": rel, "why": "no `title` — required field"})
                continue
            docs.append(
                _Doc(
                    path=md,
                    domain=domain,
                    address=md.relative_to(root).with_suffix("").as_posix(),  # full relative path
                    fields=fields,
                    body=body,
                    # The search words are split once, here. Doing it at search time
                    # would repeat the work once per document.
                    field_tokens={
                        "title": _tokens(title),
                        "tags": _tokens(" ".join(_tag_list(fields.get("tags")))),
                        "description": _tokens(_text(fields.get("description"))),
                        "journal": _tokens(_text(fields.get("journal"))),
                    },
                )
            )

    # --- Branch 2: flat bundles — only when the domain folders yielded nothing. ---
    #
    # A bundle that has folders never reaches this branch. So hiv-suppression's 142
    # documents still come out above, and the root's predictors.md and search.md stay
    # excluded.
    #
    # The condition being "nothing was salvaged above" rather than "there are no
    # folders" matters. A bundle whose folders exist but whose every file is broken
    # also lands here, and in that case skipped already holds the reasons, so the
    # response alone shows what happened.
    if not docs:
        for md in sorted(root.glob("*.md")):
            if md.stem in _ROOT_RESERVED:
                continue   # a structure file, not evidence
            rel = md.name
            try:
                fields, body = _parse_concept_file(md)
            except (OKFError, OSError, UnicodeDecodeError) as exc:
                skipped.append({"path": rel, "why": str(exc)})
                continue
            title = _text(fields.get("title"))
            if not title:
                skipped.append({"path": rel, "why": "no `title` — the one required field"})
                continue
            # A flat bundle has no folder name to match against. Use `domain` if it is
            # written, and the bundle name otherwise — so no blank appears in the list.
            domain = _text(fields.get("domain")) or root.name
            docs.append(
                _Doc(
                    path=md,
                    domain=domain,
                    address=md.stem,        # flat, so the plain name, not `domain/name`
                    fields=fields,
                    body=body,
                    field_tokens={
                        "title": _tokens(title),
                        "tags": _tokens(" ".join(_tag_list(fields.get("tags")))),
                        "description": _tokens(_text(fields.get("description"))),
                        "journal": _tokens(_text(fields.get("journal"))),
                    },
                )
            )

    # Stored together with the stamp. The next call compares the stamp and stops there.
    _CACHE[key] = (sig, docs, skipped)
    return docs, skipped


def _idf(docs: list[_Doc]) -> dict[str, float]:
    """How much each word is worth. A word in every paper distinguishes nothing.

    The principle is simple. Count how many papers a word appears in, and give **the
    rarer word the higher value.** In the HIV bundle, for instance, 'hiv' is in almost
    every paper, so matching on it has singled out nothing — a low value. 'tenofovir',
    on the other hand, is in only a few, so matching on it really has pointed at those
    few — a high value.

    This is the common method known in information retrieval as idf (inverse document
    frequency).
    """
    n = len(docs) or 1          # at least 1, so as never to divide by zero
    df: dict[str, int] = {}     # word -> how many documents it appeared in
    for doc in docs:
        # The words of the four fields (title, tags, description, journal) are merged
        # and then counted. A word in several fields of one document still counts as
        # "one document".
        for token in frozenset().union(*doc.field_tokens.values()):
            df[token] = df.get(token, 0) + 1
    # A logarithm keeps the values from spreading too far apart.
    return {t: math.log(1.0 + n / c) for t, c in df.items()}


def _index(docs: list[_Doc]) -> dict[str, list[_Doc]]:
    """Every name a document answers to, lowercased.

    A paper is referred to by its PMID in one breath and its filename in the next. One
    id would be tidier and would send the agent back to look it up again.

    A phone book of **every name** a document goes by: the address, the filename, the
    filename without its extension, the `id` in the frontmatter, and the PMID — all of
    them work.

    The value is a list because two documents can answer to the same name. When that
    happens okf_read does not pick one at random; it says "ambiguous" and names the
    candidates.
    """
    by_ref: dict[str, list[_Doc]] = {}
    for doc in docs:
        # Wrapped in a set so that a name occurring twice is registered only once
        # (in a flat bundle, for instance, address and stem are the same).
        for key in {
            doc.address.lower(),
            doc.path.name.lower(),
            doc.path.stem.lower(),
            _text(doc.fields.get("id")).lower(),
            _text(doc.fields.get("pmid")).lower(),
        }:
            if key:   # no id or pmid in the frontmatter gives "", which is filtered out
                by_ref.setdefault(key, []).append(doc)
    return by_ref


def _split(raw: str) -> list[str]:
    """Split on commas, trim each piece, drop the empties.

    Used for okf queries, tags and document references — none of which contain a
    comma, which is the only reason splitting on one is safe here.

    This used to say it was deliberately aligned with `slice_columns`, so that
    both tools took input the same way. It is not aligned any more, on purpose:
    158 of the cohort's 1,393 column names carry a comma *inside* the name
    (`LAB__HDL CHOLESTEROL, DIRECT`), so `slice_columns` now takes a JSON list
    and splits nothing. Do not "make these consistent" again — the two tools
    differ because their values differ.
    """
    return [p.strip() for p in raw.split(",") if p.strip()]


# --------------------------------------------------------------------------- #
#  Tools — reading
# --------------------------------------------------------------------------- #


@mcp.tool()
def okf_list_domains() -> str:
    """List the bundle's domains and how many documents each holds.

    Call this first. It is the cheapest possible picture of what the knowledge source
    covers, before a single search is spent finding out.

    Returns:
        JSON with domains (slug, title, documents), total, and — if any file was passed
        over — skipped, naming each one and why. A non-empty skipped list means the
        bundle holds files this surface did not read; report it rather than assuming the
        total is the whole bundle.
    """
    try:
        root = _bundle_root()          # the bundle location the env var points at
        docs, skipped = _load(root)
    except OKFError as e:
        # The bundle is not configured, and the like. Reported as JSON rather than
        # dying on an exception.
        return json.dumps({"error": str(e)})

    # Count the documents per domain.
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc.domain] = counts.get(doc.domain, 0) + 1

    domains = []
    for slug in sorted(counts):
        # If the domain folder's index.md carries a human-readable title, take it.
        # A flat bundle has no such file, so the folder name (the slug) is used.
        title = ""
        index = root / slug / _DOMAIN_INDEX
        if index.is_file():
            try:
                fields, _ = _parse_concept_file(index)
                title = _text(fields.get("domain_title")) or _text(fields.get("title"))
            except (OKFError, OSError, UnicodeDecodeError):
                title = ""   # an unreadable cover still leaves the list itself usable
        domains.append({"slug": slug, "title": title or slug, "documents": counts[slug]})

    out: dict[str, Any] = {"domains": domains, "total": len(docs)}
    if skipped:
        out["skipped"] = skipped   # included only when something was passed over
    return json.dumps(out)


@mcp.tool()
def okf_search(queries: str, k: int = _DEFAULT_K, domain: str = "", tags: str = "") -> str:
    """Search the bundle by what its authors said each document is about.

    Titles, tags, descriptions and journals are searched. **Bodies are not.** A hit
    therefore means the bundle says this document is about your query — not that the
    word appears somewhere inside it. Search by idea, not by column name — a column
    name lives in the body or in the data, never in the title of a paper.

    The score is the sum of (the field's weight) x (the worth of the word that
    matched). It carries no absolute meaning and is used **only to order the results
    within one search.**

    Args:
        queries: comma-separated; each is searched separately and results are merged.
            e.g. "adherence to therapy, viral load monitoring"
        k: results per query. Default 8, raised to at most 20.
        domain: restrict to one domain slug; "" = all. See okf_list_domains.
        tags: comma-separated; keep only documents carrying ANY of these tags.

    Returns:
        JSON with one entry per query: its hits as catalogue rows (id, title, domain,
        tags, journal, published, strength, n, pmid) with a score, ordered best first.
        Open the promising ones with okf_read.
    """
    try:
        root = _bundle_root()
        docs, _ = _load(root)
    except OKFError as e:
        return json.dumps({"error": str(e)})

    wanted = _split(queries)
    if not wanted:
        return json.dumps({"error": "queries must not be empty"})

    # Anything below 1 is pushed up to 1, anything above 20 is pushed down to 20.
    limit = max(1, min(int(k), _MAX_K))
    notes = []
    if int(k) > _MAX_K:
        # Not trimmed silently. Saying so in the response is what tells the caller
        # that this is not all of it.
        notes.append(f"k={k} was clamped to the ceiling {_MAX_K}.")

    # Narrowing what gets searched — by domain, and by tags.
    pool = docs
    if domain:
        pool = [d for d in pool if d.domain == domain]
        if not pool:
            # When the domain name was mistyped, hand back the list of real names too.
            return json.dumps(
                {"error": f"no domain {domain!r}", "domains": sorted({d.domain for d in docs})}
            )
    keep_tags = {t.lower() for t in _split(tags)}
    if keep_tags:
        # Kept when the intersection is not empty = ANY one tag in common passes (not AND).
        pool = [d for d in pool if keep_tags & {t.lower() for t in _tag_list(d.fields.get("tags"))}]

    idf = _idf(docs)  # weights come from the whole bundle, not the filtered slice
                      # Taken from the filtered slice instead, the same word would be
                      # worth something different on every narrowing, and the scores of
                      # two searches could no longer be compared.
    results = []
    for query in wanted:
        q = _tokens(query)   # the query is split into words exactly as a document is
        scored = []
        for doc in pool:
            score = 0.0
            for field, weight in _FIELD_WEIGHTS.items():
                hits = q & doc.field_tokens[field]   # the words in common
                if hits:
                    score += weight * sum(idf.get(t, 0.0) for t in hits)
            if score > 0.0:
                scored.append((score, doc))
        # Highest score first. Ties break on the address — a second criterion, so that
        # the same input always comes out in the same order (reproducibly).
        scored.sort(key=lambda pair: (-pair[0], pair[1].address))
        results.append(
            {
                "query": query,
                # How many matched (matched) and how many are actually shown (hits) are
                # different numbers. A large matched is a sign the query is too broad.
                "matched": len(scored),
                "hits": [{**doc.summary, "score": round(score, 3)} for score, doc in scored[:limit]],
            }
        )

    # searched = how many documents were actually swept this time (the count after
    # narrowing by domain and tags).
    out: dict[str, Any] = {"results": results, "searched": len(pool)}
    if notes:
        out["notes"] = notes
    return json.dumps(out)


@mcp.tool()
def okf_read(refs: str, section: str = "", max_chars: int = 0) -> str:
    """Open one or several documents — whole, or one section of each.

    Every document in a Loremaster bundle is written in the same sections. Ask for the
    one you need instead of the whole paper: `section="Bottom line"` is usually what a
    hypothesis is built from, and a full body here runs to several thousand characters.

    Args:
        refs: comma-separated. A document answers to its id, its PMID, its filename and
            its filename without the suffix — whichever you have.
        section: exact section heading; "" = the whole body. Each result lists the
            headings that document actually has, so a wrong guess is recoverable in one
            call rather than a search.
        max_chars: truncate the returned text; 0 = no limit. Truncation is reported.

    Returns:
        JSON with one entry per ref: its frontmatter fields, the text asked for, the
        available section headings, and export_safe as the STRING the bundle wrote.
    """
    try:
        root = _bundle_root()
        docs, _ = _load(root)
    except OKFError as e:
        return json.dumps({"error": str(e)})

    by_ref = _index(docs)      # the phone book of names
    wanted = _split(refs)
    if not wanted:
        return json.dumps({"error": "refs must not be empty"})

    out = []
    for ref in wanted:
        # One failure does not stop the rest from opening. Only the one that failed
        # gets its reason written in place.
        found = by_ref.get(ref.strip().lower(), [])
        if not found:
            out.append({"ref": ref, "error": "no document answers to that reference"})
            continue
        if len(found) > 1:
            # Two or more documents answer to the same name. Rather than pick one at
            # random, show the candidates.
            out.append(
                {"ref": ref, "error": "ambiguous", "candidates": [d.address for d in found]}
            )
            continue
        doc = found[0]
        sections = _sections(doc.body)
        headings = [name for name, _ in sections]   # the section names this document has

        if section:
            # Look for an exactly equal section heading. None if there is none.
            text = next((body for name, body in sections if name == section), None)
            if text is None:
                out.append(
                    {
                        "ref": ref,
                        "id": doc.address,
                        "error": f"no section {section!r}",
                        "sections": headings,
                    }
                )
                continue
        else:
            text = doc.body          # no section named -> the whole body

        truncated = False
        if max_chars and len(text) > max_chars:
            text, truncated = text[:max_chars], True

        entry = {
            **doc.summary,           # the catalogue row (title, tags, journal, PMID ...) laid on as is
            "ref": ref,              # exactly the name the caller used — easy to pair an answer to its request
            "section": section or None,
            "text": text,
            "sections": headings,
            # As a STRING, on purpose. The bundle writes `export_safe: "false"` quoted,
            # and a non-empty string is truthy in Python — anything that tests this
            # value for truth redistributes every document while reporting it filtered.
            # 102 of this bundle's 142 papers say "false". The judgement is not made
            # here; the value is passed through as it stands and the caller is left to
            # compare it as a string.
            "export_safe": _text(doc.fields.get("export_safe")),
        }
        if truncated:
            entry["truncated"] = True   # a truncation is always announced
        out.append(entry)

    # default=str is the last safety net. Even with a value in the frontmatter that
    # JSON does not know, this turns it into text rather than blowing up wholesale.
    return json.dumps({"documents": out}, default=str)


if __name__ == "__main__":
    # Running this file directly brings it up as an MCP server. core's tools and the
    # three tools above come out of the one server together.
    mcp.run()
