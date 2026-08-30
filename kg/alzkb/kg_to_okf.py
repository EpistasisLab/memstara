"""Convert a hypothesis-shaped slice of AlzKB into an OKF bundle.

The bundle is not "AlzKB in OKF form" — it is the part of AlzKB that one
hypothesis asks about. The hypothesis this script implements by default is the
one from Orlenko et al. 2025 (papers/2025_orlenko_gene_drug_targets_alzheimer.pdf):

    "A non-disease gene that interacts with a disease-associated gene and is
     also druggable may be a novel therapeutic target."

which decomposes into three steps, each an argument below:

    1. anchors   genes linked to the anchor disease        --anchor-disease
    2. expand    genes those anchors interact with         --expand-edge
    3. filter    of those, the druggable non-anchor ones    --drug-edges/--min-drugs

Change the three arguments and you get a different bundle from the same graph.
That is deliberate: a bundle is one hypothesis, and there can be many


Mapping onto OKF (see papers/2026_mcveety_okf_introduction.pdf):

    graph node  ->  concept file       one markdown file per gene
    graph edge  ->  markdown link      links are how OKF carries relationships
    node props  ->  YAML frontmatter   only `type` is required by the spec

Usage::

    python kg_to_okf.py --dry-run                 # count only, writes nothing
    python kg_to_okf.py --out ../../outputs/okf_alzkb_druggable_non_ad_targets
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sqlite3
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
DEFAULT_DB = HERE / "alzkb.db"
DEFAULT_OUT = HERE.parent.parent / "outputs" / "okf_alzkb_druggable_non_ad_targets"

DEFAULT_DRUG_EDGES = (
    "CHEMICALBINDSGENE",
    "CHEMICALINCREASESEXPRESSION",
    "CHEMICALDECREASESEXPRESSION",
)

# A gene symbol becomes a filename, so it has to survive as one. Every symbol in
# the current selection already passes; the check is here so a different
# hypothesis cannot introduce a bad one silently.
SAFE_SYMBOL = re.compile(r"[A-Za-z0-9._-]+")

# SQLite has a parameter limit; queries over the selection are chunked.
CHUNK = 900


# --------------------------------------------------------------------------- #
#  Graph selection — the three steps of the hypothesis
# --------------------------------------------------------------------------- #


def _chunks(items: list[Any]) -> list[list[Any]]:
    return [items[i : i + CHUNK] for i in range(0, len(items), CHUNK)]


def select_anchors(conn: sqlite3.Connection, disease: str) -> set[int]:
    """Step 1 — genes with a direct association edge to the anchor disease."""
    rows = conn.execute(
        """SELECT e.src FROM edges e JOIN nodes d ON d.mg_id = e.dst
            WHERE e.type = 'GENEASSOCIATESWITHDISEASE' AND d.common_name = ?""",
        (disease,),
    )
    return {r[0] for r in rows}


def expand_to_partners(
    conn: sqlite3.Connection, anchors: set[int], edge_type: str
) -> set[tuple[int, int]]:
    """Step 2 — (anchor, partner) pairs, keeping only partners outside `anchors`.

    The edge type is undirected in meaning, so both endpoints are considered.
    Excluding anchors is what makes the result *novel* candidates rather than
    a rediscovery of what is already known.
    """
    pairs: set[tuple[int, int]] = set()
    for chunk in _chunks(sorted(anchors)):
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT src, dst FROM edges
                 WHERE type = ? AND (src IN ({placeholders}) OR dst IN ({placeholders}))""",
            (edge_type, *chunk, *chunk),
        )
        for src, dst in rows:
            for a, b in ((src, dst), (dst, src)):
                if a in anchors and b not in anchors:
                    pairs.add((a, b))
    return pairs


def count_drugs(
    conn: sqlite3.Connection, genes: set[int], drug_edges: tuple[str, ...]
) -> dict[int, int]:
    """How many distinct drugs act on each gene, across the given edge types."""
    counts = dict.fromkeys(genes, 0)
    edge_placeholders = ",".join("?" * len(drug_edges))
    for chunk in _chunks(sorted(genes)):
        gene_placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT dst, COUNT(DISTINCT src) FROM edges
                 WHERE type IN ({edge_placeholders}) AND dst IN ({gene_placeholders})
                 GROUP BY dst""",
            (*drug_edges, *chunk),
        )
        for gene, n in rows:
            counts[gene] = n
    return counts


def resolve_min_drugs(counts: dict[int, int], min_drugs: int | None) -> float:
    """The cutoff. Without an explicit value, use the paper's 75th percentile.

    The percentile is taken over every partner including those with zero drugs,
    which is what the paper did. On AlzKB v2.0.0 that lands at 4.
    """
    if min_drugs is not None:
        return float(min_drugs)
    return statistics.quantiles(sorted(counts.values()), n=4)[2]


# --------------------------------------------------------------------------- #
#  Node facts — everything the concept files need, read once
# --------------------------------------------------------------------------- #


def load_gene_facts(conn: sqlite3.Connection, genes: set[int]) -> dict[int, dict[str, Any]]:
    """Symbol, name and cross-references for each selected gene."""
    facts: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(sorted(genes)):
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT mg_id, common_name, props FROM nodes WHERE mg_id IN ({placeholders})",
            chunk,
        )
        for mg_id, common_name, props in rows:
            p = json.loads(props) if props else {}
            facts[mg_id] = {
                "symbol": p.get("geneSymbol"),
                "name": common_name if common_name not in (None, "-") else None,
                "ncbi": p.get("xrefNcbiGene"),
                "ensembl": p.get("xrefEnsembl"),
                "chromosome": p.get("chromosome"),
                "type_of_gene": p.get("typeOfGene"),
            }
    return facts


def load_anchor_diseases(conn: sqlite3.Connection, anchors: set[int]) -> dict[int, list[str]]:
    """Which disease nodes each anchor is linked to — the evidence for step 1."""
    out: dict[int, list[str]] = defaultdict(list)
    for chunk in _chunks(sorted(anchors)):
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT e.src, d.common_name FROM edges e JOIN nodes d ON d.mg_id = e.dst
                 WHERE e.type = 'GENEASSOCIATESWITHDISEASE' AND e.src IN ({placeholders})""",
            chunk,
        )
        for gene, disease in rows:
            if disease:
                out[gene].append(disease)
    return {g: sorted(v) for g, v in out.items()}


def load_partner_drugs(
    conn: sqlite3.Connection, partners: set[int], drug_edges: tuple[str, ...], limit: int = 8
) -> dict[int, list[str]]:
    """A few drug names per partner — evidence for step 3, not the full list."""
    out: dict[int, list[str]] = defaultdict(list)
    edge_placeholders = ",".join("?" * len(drug_edges))
    for chunk in _chunks(sorted(partners)):
        gene_placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT e.dst, s.common_name FROM edges e JOIN nodes s ON s.mg_id = e.src
                 WHERE e.type IN ({edge_placeholders}) AND e.dst IN ({gene_placeholders})
                 ORDER BY s.common_name""",
            (*drug_edges, *chunk),
        )
        for gene, drug in rows:
            if drug and len(out[gene]) < limit and drug not in out[gene]:
                out[gene].append(drug)
    return dict(out)


# --------------------------------------------------------------------------- #
#  OKF writing
# --------------------------------------------------------------------------- #


def yaml_scalar(value: Any) -> str:
    """Minimal YAML emitter. Quotes anything that could be misread as a number."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or re.fullmatch(r"[-+]?\d+(\.\d+)?", text) or any(c in text for c in ':#"\'\n'):
        return json.dumps(text, ensure_ascii=False)
    return text


def write_concept(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Write one OKF concept: `---` YAML `---` then the markdown body."""
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {yaml_scalar(v)}" for v in value)
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"  {k}: {yaml_scalar(v)}" for k, v in value.items())
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines += ["---", "", body.rstrip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def anchor_body(
    symbol: str,
    facts: dict[str, Any],
    diseases: list[str],
    partners: list[tuple[str, int]],
    partner_total: int,
) -> str:
    """Body for an anchor gene. Partner links are the graph's edges."""
    name = facts["name"] or symbol
    lines = [
        f"# {symbol} — {name}",
        "",
        f"`{symbol}` is directly associated with {len(diseases)} disease node(s) in AlzKB:",
        "",
    ]
    lines += [f"- {d}" for d in diseases]
    lines += [
        "",
        "## Druggable non-AD interaction partners",
        "",
        f"{symbol} physically interacts with {partner_total} gene(s). "
        f"{len(partners)} of them are **not** themselves AD-associated and are "
        "druggable, which makes them candidate novel targets.",
        "",
        "Each link below is one `GENEINTERACTSWITHGENE` edge. "
        "The number in parentheses is how many drugs act on that gene.",
        "",
    ]
    lines += [
        f"- [{sym}](../partners/{sym.lower()}) ({n} drugs)"
        for sym, n in sorted(partners, key=lambda kv: (-kv[1], kv[0]))
    ]
    lines += [
        "",
        "## Provenance",
        "",
        "Anchor selected by a `GENEASSOCIATESWITHDISEASE` edge. Partners reached by "
        "`GENEINTERACTSWITHGENE`, then filtered by drug-acting edges. "

        "its unverified assumption.",
    ]
    return "\n".join(lines)


def partner_body(
    symbol: str,
    facts: dict[str, Any],
    drug_count: int,
    drugs: list[str],
    anchors: list[str],
) -> str:
    """Body for a partner gene — the candidate target."""
    name = facts["name"] or symbol
    lines = [
        f"# {symbol} — {name}",
        "",
        f"`{symbol}` is **not** directly associated with Alzheimer's disease in AlzKB, "
        f"but interacts with {len(anchors)} gene(s) that are. "
        f"{drug_count} drug(s) act on it, so it can be modulated.",
        "",
        "## Reached from",
        "",
    ]
    lines += [f"- [{a}](../anchors/{a.lower()})" for a in sorted(anchors)]
    lines += ["", "## Drugs acting on this gene", ""]
    if drugs:
        lines.append(", ".join(drugs) + (" …" if drug_count > len(drugs) else ""))
    else:
        lines.append("_none recorded_")
    lines += [
        "",
        "## Caution",
        "",
        "A high drug count does not by itself mean a good therapeutic target. "
        "Drug-metabolising enzymes and transporters accumulate many binding records "
        "because most drugs pass through them.",
    ]
    return "\n".join(lines)


def root_index(counts: dict[str, int], config: dict[str, Any], stamp: str) -> str:
    """Root index.md — how to navigate, not a listing of 1,162 files."""
    return f"""# {config['bundle_name']}

One hypothesis over AlzKB {config['graph_version']}, expressed as OKF concepts.

## What is in here

| | count |
|---|---:|
| anchor genes (associated with *{config['anchor_disease']}*) | {counts['anchors']} |
| partner genes (not AD-associated, druggable) | {counts['partners']} |
| **concepts total** | **{counts['anchors'] + counts['partners']}** |
| interaction links between them | {counts['pairs']} |

## How to navigate

There is no per-directory index, on purpose: this repository's OKF server
treats only root-level `index`/`log` as reserved, so a nested `index.md` would
appear as a concept. Use tags instead.

- `list_concepts(tags="anchor")` — the {counts['anchors']} AD-associated genes
- `list_concepts(tags="partner")` — the {counts['partners']} candidate targets
- `get_concept("anchors/mapt")` — one gene, with links to its partners

Every concept carries `variables:` holding its gene symbol, which is how a
dataset column is selected once genotype-level data is available.

## How it was selected

1. genes with an edge to *{config['anchor_disease']}* → **{counts['anchors_initial']}**
2. genes those interact with, excluding AD-associated ones → **{counts['partners_initial']}**
3. of those, genes with at least {config['min_drugs']:.0f} acting drugs → **{counts['partners']}**

Anchors with no surviving partner are dropped, leaving {counts['anchors']}.

Reasoning, and the assumption it rests on:


## Provenance

- graph: AlzKB {config['graph_version']}
- generated: {stamp} by `kg/alzkb/kg_to_okf.py`
- edge types used: `GENEASSOCIATESWITHDISEASE`, `{config['expand_edge']}`, {', '.join('`%s`' % e for e in config['drug_edges'])}

Change those arguments and the same script produces a different bundle from the
same graph — see §10 of the design document.
"""


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #


def build(args: argparse.Namespace) -> None:
    """Run the three selection steps, then write the bundle."""
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    anchors = select_anchors(conn, args.anchor_disease)
    if not anchors:
        raise SystemExit(f"no genes associated with {args.anchor_disease!r} — check the name")
    logger.info("step 1  anchors linked to %s: %d", args.anchor_disease, len(anchors))

    pairs = expand_to_partners(conn, anchors, args.expand_edge)
    partners_initial = {p for _, p in pairs}
    logger.info("step 2  non-anchor partners: %d  (pairs %d)", len(partners_initial), len(pairs))

    drug_counts = count_drugs(conn, partners_initial, tuple(args.drug_edges))
    cutoff = resolve_min_drugs(drug_counts, args.min_drugs)
    kept = {g for g, n in drug_counts.items() if n >= cutoff and n > 0}
    final_pairs = {(a, b) for a, b in pairs if b in kept}
    final_anchors = {a for a, _ in final_pairs}
    logger.info(
        "step 3  cutoff %.2f drugs -> partners %d, pairs %d, anchors %d",
        cutoff, len(kept), len(final_pairs), len(final_anchors),
    )

    counts = {
        "anchors": len(final_anchors),
        "partners": len(kept),
        "pairs": len(final_pairs),
        "anchors_initial": len(anchors),
        "partners_initial": len(partners_initial),
    }
    if args.dry_run:
        print(json.dumps({**counts, "cutoff_drugs": cutoff}, indent=2))
        print("dry run — nothing written")
        return

    facts = load_gene_facts(conn, final_anchors | kept)
    missing = [g for g in final_anchors | kept if not facts[g]["symbol"]]
    if missing:
        raise SystemExit(f"{len(missing)} selected genes have no geneSymbol; cannot name files")
    bad = [f["symbol"] for f in facts.values() if not SAFE_SYMBOL.fullmatch(f["symbol"])]
    if bad:
        raise SystemExit(f"gene symbols unusable as filenames: {bad[:5]}")

    diseases = load_anchor_diseases(conn, final_anchors)
    drug_names = load_partner_drugs(conn, kept, tuple(args.drug_edges))
    partner_total = {a: 0 for a in final_anchors}
    for a, _ in pairs:
        if a in partner_total:
            partner_total[a] += 1

    by_anchor: dict[int, list[tuple[str, int]]] = defaultdict(list)
    by_partner: dict[int, list[str]] = defaultdict(list)
    for a, b in final_pairs:
        by_anchor[a].append((facts[b]["symbol"], drug_counts[b]))
        by_partner[b].append(facts[a]["symbol"])

    out: Path = args.out
    if out.exists():
        if not args.force:
            raise SystemExit(f"{out} already exists — pass --force to replace it")
        shutil.rmtree(out)
    (out / "anchors").mkdir(parents=True)
    (out / "partners").mkdir(parents=True)

    stamp = args.stamp or date.today().isoformat()
    generated = {"by": "process:kg_to_okf", "at": f"{stamp}T00:00:00Z"}
    config = {
        "bundle_name": out.name,
        "graph_version": args.graph_version,
        "anchor_disease": args.anchor_disease,
        "expand_edge": args.expand_edge,
        "drug_edges": list(args.drug_edges),
        "min_drugs": cutoff,
    }

    for gene in sorted(final_anchors, key=lambda g: facts[g]["symbol"]):
        f = facts[gene]
        symbol = f["symbol"]
        write_concept(
            out / "anchors" / f"{symbol.lower()}.md",
            {
                "type": "gene",
                "title": f"{symbol} — AD-associated anchor gene",
                "description": f"{symbol} is associated with {args.anchor_disease} and "
                               f"interacts with {len(by_anchor[gene])} druggable non-AD genes.",
                "tags": ["alzheimer", "anchor", "ad-associated", "gene"],
                "variables": [symbol],
                "resource": f"https://www.ncbi.nlm.nih.gov/gene/{f['ncbi']}" if f["ncbi"] else "",
                "source": {
                    "graph": f"AlzKB {args.graph_version}",
                    "role": "anchor",
                    "gene_symbol": symbol,
                    "ncbi_gene": f["ncbi"] or "",
                    "ensembl": f["ensembl"] or "",
                    "chromosome": f["chromosome"] or "",
                    "disease_edges": len(diseases.get(gene, [])),
                    "partners_total": partner_total[gene],
                    "partners_kept": len(by_anchor[gene]),
                },
                "generated": generated,
                "status": "draft",
            },
            anchor_body(symbol, f, diseases.get(gene, []), by_anchor[gene], partner_total[gene]),
        )

    for gene in sorted(kept, key=lambda g: facts[g]["symbol"]):
        f = facts[gene]
        symbol = f["symbol"]
        write_concept(
            out / "partners" / f"{symbol.lower()}.md",
            {
                "type": "gene",
                "title": f"{symbol} — druggable non-AD candidate target",
                "description": f"{symbol} interacts with {len(by_partner[gene])} AD-associated "
                               f"gene(s) and is acted on by {drug_counts[gene]} drugs.",
                "tags": ["alzheimer", "partner", "druggable", "candidate-target", "gene"],
                "variables": [symbol],
                "resource": f"https://www.ncbi.nlm.nih.gov/gene/{f['ncbi']}" if f["ncbi"] else "",
                "source": {
                    "graph": f"AlzKB {args.graph_version}",
                    "role": "partner",
                    "gene_symbol": symbol,
                    "ncbi_gene": f["ncbi"] or "",
                    "ensembl": f["ensembl"] or "",
                    "chromosome": f["chromosome"] or "",
                    "drug_count": drug_counts[gene],
                    "anchor_count": len(by_partner[gene]),
                },
                "generated": generated,
                "status": "draft",
            },
            partner_body(symbol, f, drug_counts[gene], drug_names.get(gene, []), by_partner[gene]),
        )

    (out / "index.md").write_text(root_index(counts, config, stamp), encoding="utf-8")
    (out / "log.md").write_text(
        f"# Change log\n\n- {stamp} — bundle generated by `kg/alzkb/kg_to_okf.py` "
        f"from AlzKB {args.graph_version}. {counts['anchors'] + counts['partners']} concepts.\n",
        encoding="utf-8",
    )

    print(f"wrote {counts['anchors'] + counts['partners']} concepts to {out}")
    print(f"  anchors  {counts['anchors']:>5}")
    print(f"  partners {counts['partners']:>5}")
    print(f"  links    {counts['pairs']:>5}")
    print(f"\nexport AGENTIC_OKF_BUNDLE_DIR=\"{out.resolve()}\"")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--graph-version", default="v2.0.0")
    parser.add_argument("--anchor-disease", default="Alzheimer's Disease",
                        help="step 1: exact common_name of the Disease node")
    parser.add_argument("--expand-edge", default="GENEINTERACTSWITHGENE",
                        help="step 2: edge type followed out of the anchors")
    parser.add_argument("--drug-edges", nargs="+", default=list(DEFAULT_DRUG_EDGES),
                        help="step 3: edge types counted as 'druggable'")
    parser.add_argument("--min-drugs", type=int, default=None,
                        help="step 3 cutoff; default is the 75th percentile (the paper's rule)")
    parser.add_argument("--stamp", default=None, help="date for `generated.at` (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    parser.add_argument("--force", action="store_true", help="replace an existing bundle")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build(args)


if __name__ == "__main__":
    main()
