#!/usr/bin/env python3
"""Sync 9Router combo/alias mappings so Codex App bare model names work."""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path.home() / ".9router" / "db" / "data.sqlite"
ALIAS_SCOPE = "modelAliases"

# Codex App bare name -> source combo to copy model chain from
DEFAULT_COMBO_MIRROR = {
    "gpt-5.5": "cc-pro",
    "gpt-5.4": "cc-normal",
    "gpt-5.4-mini": "cc-lite",
}

# Codex App bare name -> ekti endpoint model id (alias target suffix)
DEFAULT_ALIAS_MODELS = {
    "gpt-5.3-codex": "gpt-5.3-codex",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.5": "gpt-5.5",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror 9Router combos/aliases for Codex App model picker bare names."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--mirror-combos", action="store_true", help="Create/update gpt-5.x combos from cc-* combos")
    parser.add_argument("--fix-aliases", action="store_true", help="Point bare names at ekti compatible endpoint models")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="Show current combos and relevant aliases")
    return parser.parse_args()


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f"Missing 9Router database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def json_load(raw: str | None, fallback):
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def get_combo(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM combos WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "models": json_load(row["models"], []),
    }


def get_aliases(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM kv WHERE scope = ?", (ALIAS_SCOPE,)).fetchall()
    return {row["key"]: json_load(row["value"], row["value"]) for row in rows}


def detect_ekti_storage_prefix(conn: sqlite3.Connection) -> str | None:
    aliases = get_aliases(conn)
    for target in aliases.values():
        if not isinstance(target, str) or not target.startswith("openai-compatible-chat-"):
            continue
        if "/" in target:
            return target.split("/", 1)[0]
    row = conn.execute(
        "SELECT id FROM providerNodes WHERE type = 'openai-compatible' LIMIT 1"
    ).fetchone()
    if row:
        return row["id"]
    return None


def upsert_combo(
    conn: sqlite3.Connection,
    name: str,
    models: list[str],
    *,
    dry_run: bool,
) -> str:
    existing = get_combo(conn, name)
    models_json = json.dumps(models, ensure_ascii=False)
    if existing:
        if existing["models"] == models:
            return "unchanged"
        if dry_run:
            return "would_update"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE combos SET models = ?, updatedAt = ? WHERE id = ?",
            (models_json, now, existing["id"]),
        )
        return "updated"
    if dry_run:
        return "would_create"
    now = datetime.now(timezone.utc).isoformat()
    combo_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO combos(id, name, kind, models, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?)",
        (combo_id, name, None, models_json, now, now),
    )
    return "created"


def upsert_alias(
    conn: sqlite3.Connection,
    alias: str,
    target: str,
    *,
    dry_run: bool,
) -> str:
    aliases = get_aliases(conn)
    current = aliases.get(alias)
    if current == target:
        return "unchanged"
    if dry_run:
        return "would_update" if current else "would_create"
    conn.execute(
        """
        INSERT INTO kv(scope, key, value) VALUES(?, ?, ?)
        ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value
        """,
        (ALIAS_SCOPE, alias, json.dumps(target)),
    )
    return "updated" if current else "created"


def mirror_combos(conn: sqlite3.Connection, mapping: dict[str, str], dry_run: bool) -> list[dict]:
    results: list[dict] = []
    for target_name, source_name in mapping.items():
        source = get_combo(conn, source_name)
        if not source or not source["models"]:
            results.append(
                {
                    "target": target_name,
                    "source": source_name,
                    "action": "skipped",
                    "reason": f"missing source combo: {source_name}",
                }
            )
            continue
        action = upsert_combo(conn, target_name, source["models"], dry_run=dry_run)
        results.append(
            {
                "target": target_name,
                "source": source_name,
                "action": action,
                "models": source["models"],
            }
        )
    return results


def fix_aliases(conn: sqlite3.Connection, mapping: dict[str, str], dry_run: bool) -> list[dict]:
    prefix = detect_ekti_storage_prefix(conn)
    if not prefix:
        raise SystemExit("Could not detect openai-compatible-chat-* provider id in aliases/DB")

    results: list[dict] = []
    for alias, model_id in mapping.items():
        target = f"{prefix}/{model_id}"
        action = upsert_alias(conn, alias, target, dry_run=dry_run)
        results.append({"alias": alias, "target": target, "action": action})
    return results


def list_state(conn: sqlite3.Connection) -> dict:
    combos = conn.execute("SELECT name, models FROM combos ORDER BY name").fetchall()
    aliases = get_aliases(conn)
    relevant_aliases = {
        key: value
        for key, value in sorted(aliases.items())
        if key.startswith("gpt-") or key.startswith("oa-gpt-")
    }
    return {
        "combos": {row["name"]: json_load(row["models"], []) for row in combos},
        "aliases": relevant_aliases,
        "ekti_prefix": detect_ekti_storage_prefix(conn),
    }


def main() -> int:
    args = parse_args()
    if not args.list and not args.mirror_combos and not args.fix_aliases:
        raise SystemExit("Pass --mirror-combos and/or --fix-aliases or --list")

    conn = connect(args.db)
    try:
        output: dict = {"db": str(args.db), "dry_run": args.dry_run}

        if args.list:
            output["state"] = list_state(conn)

        if args.mirror_combos:
            output["combo_mirror"] = mirror_combos(conn, DEFAULT_COMBO_MIRROR, args.dry_run)

        if args.fix_aliases:
            output["alias_fix"] = fix_aliases(conn, DEFAULT_ALIAS_MODELS, args.dry_run)

        if not args.dry_run and (args.mirror_combos or args.fix_aliases):
            conn.commit()

        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
