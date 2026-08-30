"""Load the AlzKB Memgraph CYPHERL dump into a queryable SQLite database.

The dump is a flat list of Cypher statements in exactly three shapes:

    CREATE INDEX ON :`Label`(`nodeID`);
    CREATE (:__mg_vertex__:`Label` {__mg_id__: 123, `key`: "value", ...});
    MATCH (u:__mg_vertex__), (v:__mg_vertex__)
      WHERE u.__mg_id__ = 1 AND v.__mg_id__ = 2
      CREATE (u)-[:`RELTYPE` {`key`: "value"}]->(v);

Running a Memgraph container just to query this is more moving parts than the
pipeline needs, so we parse the statements directly. `__mg_id__` is the internal
vertex id that the MATCH statements join on; it is what we use as the primary key.

Usage:
    python build_sqlite.py [--dump PATH] [--db PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
DEFAULT_DUMP = HERE / "alzkb-v2-0-0_memgraph.cypherl"
DEFAULT_DB = HERE / "alzkb.db"

# CREATE (:__mg_vertex__:`Drug` {__mg_id__: 1486232, `nodeID`: "15602.0", ...});
NODE_RE = re.compile(r"^CREATE \(:__mg_vertex__:`([^`]+)` \{__mg_id__: (\d+), (.*)\}\);$")

# ... WHERE u.__mg_id__ = 1486825 AND v.__mg_id__ = 1671962 CREATE (u)-[:`TYPE` ...]->(v);
EDGE_RE = re.compile(
    r"^MATCH .*u\.__mg_id__ = (\d+) AND v\.__mg_id__ = (\d+) "
    r"CREATE \(u\)-\[:`([^`]+)`(.*)\]->\(v\);$"
)

# `xrefDrugbank`: "DB08747"  ->  "xrefDrugbank": "DB08747"
BACKTICK_KEY_RE = re.compile(r"`([^`]+)`:")

# Cypher escapes an apostrophe inside a double-quoted string as \' , which JSON
# rejects. "Alzheimer\'s Disease" — the main anchor node — is one of these.
CYPHER_ESCAPED_QUOTE_RE = re.compile(r"\\'")


def parse_properties(body: str) -> dict[str, object]:
    """Convert a Cypher property map body into a dict.

    Cypher quotes keys with backticks and values with double quotes. Apart from
    the apostrophe escape, the string escapes match JSON, so rewriting the keys
    and unescaping apostrophes makes the body valid JSON. A property whose
    *value* contains a backtick would still defeat this; we return an empty dict
    in that case rather than lose the whole row.
    """
    body = CYPHER_ESCAPED_QUOTE_RE.sub("'", body)
    try:
        return json.loads("{" + BACKTICK_KEY_RE.sub(r'"\1":', body) + "}")
    except json.JSONDecodeError:
        return {}


def build(dump_path: Path, db_path: Path) -> None:
    """Parse the dump and write nodes and edges into a fresh SQLite database."""
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE nodes (
            mg_id       INTEGER PRIMARY KEY,
            label       TEXT NOT NULL,
            node_id     TEXT,
            common_name TEXT,
            props       TEXT NOT NULL
        );
        CREATE TABLE edges (
            src  INTEGER NOT NULL,
            dst  INTEGER NOT NULL,
            type TEXT NOT NULL
        );
        """
    )

    nodes: list[tuple] = []
    edges: list[tuple] = []
    unparsed = 0

    with dump_path.open(errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.rstrip("\n")

            match = NODE_RE.match(line)
            if match:
                label, mg_id, body = match.group(1), int(match.group(2)), match.group(3)
                props = parse_properties(body)
                nodes.append(
                    (mg_id, label, props.get("nodeID"), props.get("commonName"),
                     json.dumps(props, ensure_ascii=False))
                )
                if len(nodes) >= 50_000:
                    conn.executemany("INSERT INTO nodes VALUES (?,?,?,?,?)", nodes)
                    nodes.clear()
                continue

            match = EDGE_RE.match(line)
            if match:
                edges.append((int(match.group(1)), int(match.group(2)), match.group(3)))
                if len(edges) >= 200_000:
                    conn.executemany("INSERT INTO edges VALUES (?,?,?)", edges)
                    edges.clear()
                continue

            # Index and cleanup statements are expected; anything else is a parse gap.
            if not (line.startswith(("CREATE INDEX", "DROP INDEX", "MATCH (u) REMOVE")) or not line):
                unparsed += 1
                if unparsed <= 5:
                    logger.warning("line %d did not parse: %.120s", line_number, line)

    conn.executemany("INSERT INTO nodes VALUES (?,?,?,?,?)", nodes)
    conn.executemany("INSERT INTO edges VALUES (?,?,?)", edges)

    logger.info("indexing")
    conn.executescript(
        """
        CREATE INDEX idx_nodes_label ON nodes(label);
        CREATE INDEX idx_nodes_name  ON nodes(label, common_name);
        CREATE INDEX idx_edges_src   ON edges(type, src);
        CREATE INDEX idx_edges_dst   ON edges(type, dst);
        """
    )
    conn.commit()

    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    empty_props = conn.execute("SELECT COUNT(*) FROM nodes WHERE props = '{}'").fetchone()[0]

    print(f"nodes {node_count:,}   edges {edge_count:,}   unparsed lines {unparsed}")
    if empty_props:
        print(f"  WARNING: {empty_props:,} nodes had unparseable properties")

    print("\nnode labels")
    for label, count in conn.execute(
        "SELECT label, COUNT(*) FROM nodes GROUP BY label ORDER BY 2 DESC"
    ):
        print(f"  {label:<28} {count:>9,}")

    print("\nedge types")
    for edge_type, count, src_label, dst_label in conn.execute(
        """
        SELECT e.type, COUNT(*), MIN(s.label), MIN(d.label)
          FROM edges e JOIN nodes s ON s.mg_id = e.src JOIN nodes d ON d.mg_id = e.dst
         GROUP BY e.type ORDER BY 2 DESC
        """
    ):
        print(f"  {edge_type:<38} {count:>9,}   {src_label} -> {dst_label}")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build(args.dump, args.db)


if __name__ == "__main__":
    main()
