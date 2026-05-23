#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SESSION_DIR_NAMES = ("sessions", "archived_sessions")
CONFIG_FILE_NAME = "config.toml"
STATE_DB_FILE = "state_5.sqlite"
SESSION_INDEX_FILE = "session_index.jsonl"
AUTH_FILE_NAMES = ("auth.json", "auth.json.bak")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Switch Codex provider config and repair chat visibility metadata."
    )
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--codex-root", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--base-url")
    parser.add_argument("--wire-api", default="responses")
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--subagent-model")
    parser.add_argument("--requires-openai-auth", action="store_true")
    parser.add_argument("--disable-response-storage", action="store_true")
    parser.add_argument("--backup-only", action="store_true")
    parser.add_argument("--repair-only", action="store_true")
    parser.add_argument("--repair-session-times-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.repair_session_times_only:
        return args
    if not args.provider:
        parser.error("--provider is required unless --repair-session-times-only is set")
    if not args.repair_only and not args.model:
        parser.error("--model is required unless --repair-only is set")
    return args


def read_current_provider(config_path: Path) -> str:
    if not config_path.exists():
        return "openai"
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("model_provider") and "=" in stripped:
            value = stripped.split("=", 1)[1].strip().strip('"')
            if value:
                return value
    return "openai"


def toml_section_header(section: str) -> str:
    parts = section.split(".")
    if any(part and not (part[0].isalpha() or part[0] == "_") for part in parts):
        return f'["{section}"]'
    return f"[{section}]"


def is_section_header(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def section_names_match(header: str, section: str) -> bool:
    stripped = header.strip()
    if stripped.startswith('["') and stripped.endswith('"]'):
        return stripped[2:-2] == section
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1] == section
    return False


def find_section_range(lines: list[str], section: str) -> tuple[int, int] | None:
    start: int | None = None
    for index, line in enumerate(lines):
        if is_section_header(line) and section_names_match(line, section):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if is_section_header(lines[index]):
            end = index
            break
    return start, end


def first_section_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if is_section_header(line):
            return index
    return len(lines)


def set_top_level_key(lines: list[str], key: str, rendered: str | None) -> list[str]:
    prefix = f"{key} ="
    updated = False
    result: list[str] = []
    for line in lines:
        if not updated and line.strip().startswith(prefix):
            if rendered is not None:
                result.append(rendered)
            updated = True
            continue
        result.append(line)
    if rendered is None:
        return result
    if updated:
        return result
    insert_at = first_section_index(result)
    result[insert_at:insert_at] = [rendered]
    return result


def provider_display_name(provider: str) -> str:
    if provider == "9router":
        return "9Router"
    return provider


def build_provider_section_lines(args: argparse.Namespace) -> list[str]:
    section = f"model_providers.{args.provider}"
    lines = [
        toml_section_header(section),
        f'name = "{provider_display_name(args.provider)}"',
    ]
    if args.base_url:
        lines.append(f'base_url = "{args.base_url}"')
    if args.wire_api:
        lines.append(f'wire_api = "{args.wire_api}"')
    if args.requires_openai_auth:
        lines.append("requires_openai_auth = true")
    return lines


def build_subagent_section_lines(args: argparse.Namespace) -> list[str]:
    if not args.subagent_model:
        return []
    return [
        toml_section_header("agents.subagent"),
        f'model = "{args.subagent_model}"',
    ]


def replace_section(lines: list[str], section: str, new_section_lines: list[str]) -> list[str]:
    if not new_section_lines:
        return lines
    found = find_section_range(lines, section)
    if found is None:
        if lines and lines[-1].strip():
            lines = [*lines, ""]
        return [*lines, *new_section_lines]
    start, end = found
    return [*lines[:start], *new_section_lines, *lines[end:]]


def patch_config_text(existing: str, args: argparse.Namespace) -> str:
    lines = existing.splitlines()
    lines = set_top_level_key(lines, "model", f'model = "{args.model}"')
    lines = set_top_level_key(lines, "model_provider", f'model_provider = "{args.provider}"')
    if args.reasoning_effort:
        lines = set_top_level_key(
            lines,
            "model_reasoning_effort",
            f'model_reasoning_effort = "{args.reasoning_effort}"',
        )
    if args.disable_response_storage:
        lines = set_top_level_key(lines, "disable_response_storage", "disable_response_storage = true")
    lines = replace_section(
        lines,
        f"model_providers.{args.provider}",
        build_provider_section_lines(args),
    )
    lines = replace_section(lines, "agents.subagent", build_subagent_section_lines(args))
    return "\n".join(lines).rstrip() + "\n"


def build_config_text(args: argparse.Namespace) -> str:
    lines: list[str] = [
        f'model = "{args.model}"',
        f'model_provider = "{args.provider}"',
    ]
    if args.reasoning_effort:
        lines.append(f'model_reasoning_effort = "{args.reasoning_effort}"')
    if args.disable_response_storage:
        lines.append("disable_response_storage = true")
    lines.append("")
    lines.extend(build_provider_section_lines(args))
    if args.subagent_model:
        lines.append("")
        lines.extend(build_subagent_section_lines(args))
    lines.append("")
    return "\n".join(lines)


def collect_rollouts(codex_root: Path) -> list[Path]:
    result: list[Path] = []
    for dir_name in SESSION_DIR_NAMES:
        root = codex_root / dir_name
        if root.exists():
            result.extend(root.rglob("rollout-*.jsonl"))
    return sorted(result)


def parse_first_line(path: Path) -> tuple[dict, str, str] | None:
    raw = path.read_text(encoding="utf-8")
    line_end = raw.find("\n")
    if line_end < 0:
        first_line = raw
        rest = ""
        newline = ""
    else:
        first_line = raw[:line_end]
        rest = raw[line_end + 1 :]
        newline = "\n"
        if first_line.endswith("\r"):
            first_line = first_line[:-1]
            newline = "\r\n"
    if not first_line.strip():
        return None
    try:
        parsed = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    if parsed.get("type") != "session_meta":
        return None
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        return None
    return parsed, rest, newline


def create_backup(codex_root: Path, target_provider: str, rollout_paths: Iterable[Path]) -> Path:
    backup_dir = codex_root / f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}-provider-switch-{target_provider}"
    files_dir = backup_dir / "files"
    rollouts_dir = backup_dir / "rollouts"
    files_dir.mkdir(parents=True, exist_ok=False)
    rollouts_dir.mkdir(parents=True, exist_ok=False)

    for name in (CONFIG_FILE_NAME, SESSION_INDEX_FILE, STATE_DB_FILE, *AUTH_FILE_NAMES):
        src = codex_root / name
        if src.exists():
            shutil.copy2(src, files_dir / name)

    saved_rollouts: list[str] = []
    for rollout in rollout_paths:
        rel = rollout.relative_to(codex_root)
        dst = rollouts_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rollout, dst)
        saved_rollouts.append(str(rel))

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "codex_root": str(codex_root),
        "target_provider": target_provider,
        "rollout_backup_count": len(saved_rollouts),
        "rollout_paths": saved_rollouts,
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return backup_dir


def planned_backup_dir(codex_root: Path, target_provider: str) -> Path:
    return codex_root / f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}-provider-switch-{target_provider}"


SESSION_INDEX_TIME_KEYS = ("updated_at", "updatedAt", "last_updated_at", "lastUpdatedAt")
ROLLOUT_TIME_KEYS = ("timestamp", "time", "created_at", "createdAt")


def normalize_timestamp_seconds(value: int | float) -> int:
    timestamp = int(value)
    if timestamp > 10_000_000_000_000:
        return timestamp // 1_000
    if timestamp > 10_000_000_000:
        return timestamp
    return timestamp


def parse_json_timestamp_seconds(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return normalize_timestamp_seconds(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return normalize_timestamp_seconds(int(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    return None


def read_session_index_map(codex_root: Path) -> dict[str, dict]:
    index_path = codex_root / SESSION_INDEX_FILE
    if not index_path.exists():
        return {}
    entries: dict[str, dict] = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        session_id = parsed.get("id")
        if isinstance(session_id, str) and session_id:
            entries[session_id] = parsed
    return entries


def session_index_updated_at_seconds(entry: dict) -> int | None:
    for key in SESSION_INDEX_TIME_KEYS:
        if key in entry:
            parsed = parse_json_timestamp_seconds(entry[key])
            if parsed is not None:
                return parsed
    return None


def session_meta_id(parsed: dict) -> str | None:
    payload = parsed.get("payload")
    if isinstance(payload, dict):
        for key in ("id", "session_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("id", "session_id"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def rollout_line_timestamp_seconds(record: dict) -> int | None:
    for key in ROLLOUT_TIME_KEYS:
        parsed = parse_json_timestamp_seconds(record.get(key))
        if parsed is not None:
            return parsed
    payload = record.get("payload")
    if isinstance(payload, dict):
        for key in ROLLOUT_TIME_KEYS:
            parsed = parse_json_timestamp_seconds(payload.get(key))
            if parsed is not None:
                return parsed
    return None


def rollout_file_activity_seconds(path: Path) -> int | None:
    latest: int | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        parsed = rollout_line_timestamp_seconds(record)
        if parsed is not None:
            latest = parsed if latest is None else max(latest, parsed)
    return latest


def resolve_target_modified_seconds(
    session_id: str | None,
    session_index_map: dict[str, dict],
    rollout_path: Path,
    fallback_seconds: int | None,
) -> int | None:
    indexed: int | None = None
    if session_id and session_id in session_index_map:
        indexed = session_index_updated_at_seconds(session_index_map[session_id])
    activity = rollout_file_activity_seconds(rollout_path)
    if indexed is not None and activity is not None:
        if abs(indexed - activity) > 3600:
            return activity
        return indexed
    if indexed is not None:
        return indexed
    if activity is not None:
        return activity
    return fallback_seconds


def read_modified_seconds(path: Path) -> int | None:
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return None


def restore_modified_seconds(path: Path, modified_seconds: int | None) -> None:
    if modified_seconds is None:
        return
    os.utime(path, (modified_seconds, modified_seconds))


def same_modified_seconds(left: int | None, right: int | None) -> bool:
    return left == right


def write_rollout_text(path: Path, text: str, target_modified_seconds: int | None) -> None:
    original_modified = read_modified_seconds(path)
    path.write_text(text, encoding="utf-8", newline="")
    restore_modified_seconds(path, target_modified_seconds if target_modified_seconds is not None else original_modified)


def restore_rollout_timestamps(
    codex_root: Path,
    session_index_map: dict[str, dict],
    dry_run: bool,
) -> tuple[int, int]:
    seen = 0
    restored = 0
    for rollout in collect_rollouts(codex_root):
        parsed_bundle = parse_first_line(rollout)
        if parsed_bundle is None:
            continue
        parsed, _, _ = parsed_bundle
        seen += 1
        current_modified = read_modified_seconds(rollout)
        target_modified = resolve_target_modified_seconds(
            session_meta_id(parsed),
            session_index_map,
            rollout,
            current_modified,
        )
        if target_modified is None or same_modified_seconds(current_modified, target_modified):
            continue
        restored += 1
        if not dry_run:
            restore_modified_seconds(rollout, target_modified)
    return seen, restored


def rewrite_rollouts(
    codex_root: Path,
    target_provider: str,
    session_index_map: dict[str, dict],
    dry_run: bool,
) -> tuple[int, int, list[Path]]:
    seen = 0
    changed = 0
    changed_paths: list[Path] = []
    for rollout in collect_rollouts(codex_root):
        parsed_bundle = parse_first_line(rollout)
        if parsed_bundle is None:
            continue
        parsed, rest, newline = parsed_bundle
        seen += 1
        current_provider = str(parsed["payload"].get("model_provider") or "")
        current_modified = read_modified_seconds(rollout)
        target_modified = resolve_target_modified_seconds(
            session_meta_id(parsed),
            session_index_map,
            rollout,
            current_modified,
        )
        provider_matches = current_provider == target_provider
        modified_matches = target_modified is None or same_modified_seconds(
            current_modified, target_modified
        )
        if provider_matches and modified_matches:
            continue
        changed += 1
        changed_paths.append(rollout)
        if dry_run:
            continue
        if not provider_matches:
            parsed["payload"]["model_provider"] = target_provider
            new_first_line = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
            new_text = new_first_line if newline == "" else new_first_line + newline + rest
            write_rollout_text(rollout, new_text, target_modified)
        elif target_modified is not None:
            restore_modified_seconds(rollout, target_modified)
    return seen, changed, changed_paths


def repair_sqlite_thread_timestamps(codex_root: Path, dry_run: bool) -> int:
    db_path = codex_root / STATE_DB_FILE
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, rollout_path, updated_at FROM threads WHERE rollout_path IS NOT NULL AND rollout_path <> ''"
        ).fetchall()
        updated = 0
        for thread_id, rollout_path, updated_at in rows:
            rollout = codex_root / rollout_path
            if not rollout.exists():
                continue
            activity = rollout_file_activity_seconds(rollout)
            if activity is None:
                continue
            current = int(updated_at or 0)
            if abs(current - activity) <= 1:
                continue
            updated += 1
            if dry_run:
                continue
            cur.execute(
                "UPDATE threads SET updated_at = ?, updated_at_ms = ? WHERE id = ?",
                (activity, activity * 1000, thread_id),
            )
        if not dry_run:
            conn.commit()
        return updated
    finally:
        conn.close()


def update_sqlite_provider(codex_root: Path, target_provider: str, dry_run: bool) -> int:
    db_path = codex_root / STATE_DB_FILE
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        if dry_run:
            row = cur.execute(
                "SELECT COUNT(*) FROM threads WHERE COALESCE(model_provider, '') <> ?",
                (target_provider,),
            ).fetchone()
            return int(row[0] if row else 0)
        cur.execute(
            "UPDATE threads SET model_provider = ? WHERE COALESCE(model_provider, '') <> ?",
            (target_provider, target_provider),
        )
        updated = int(cur.rowcount)
        conn.commit()
        return updated
    finally:
        conn.close()


def write_config(codex_root: Path, args: argparse.Namespace, dry_run: bool) -> None:
    if dry_run:
        return
    config_path = codex_root / CONFIG_FILE_NAME
    if config_path.exists():
        content = patch_config_text(config_path.read_text(encoding="utf-8"), args)
    else:
        content = build_config_text(args)
    config_path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    args = parse_args()
    codex_root = args.codex_root
    if not codex_root.exists():
        raise SystemExit(f"Missing Codex root: {codex_root}")

    session_index_map = read_session_index_map(codex_root)

    if args.repair_session_times_only:
        rollout_seen, rollout_mtime_restored = restore_rollout_timestamps(
            codex_root, session_index_map, dry_run=args.dry_run
        )
        sqlite_timestamps_updated = repair_sqlite_thread_timestamps(codex_root, dry_run=args.dry_run)
        print(
            json.dumps(
                {
                    "codex_root": str(codex_root),
                    "rollout_seen": rollout_seen,
                    "rollout_mtime_restored": rollout_mtime_restored,
                    "sqlite_timestamps_updated": sqlite_timestamps_updated,
                    "dry_run": args.dry_run,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    config_path = codex_root / CONFIG_FILE_NAME
    current_provider = read_current_provider(config_path)
    rollout_seen, rollout_changed, rollout_paths = rewrite_rollouts(
        codex_root, args.provider, session_index_map, dry_run=True
    )
    backup_dir: Path | None = None

    if rollout_changed > 0 or (not args.repair_only and current_provider != args.provider):
        if args.dry_run:
            backup_dir = planned_backup_dir(codex_root, args.provider)
        else:
            backup_dir = create_backup(codex_root, args.provider, rollout_paths)

    if args.backup_only:
        print(
            json.dumps(
                {
                    "backup_dir": str(backup_dir) if backup_dir else None,
                    "current_provider": current_provider,
                    "target_provider": args.provider,
                    "rollout_seen": rollout_seen,
                    "rollout_to_change": rollout_changed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not args.repair_only:
        write_config(codex_root, args, args.dry_run)

    rollout_seen, rollout_changed, _ = rewrite_rollouts(
        codex_root, args.provider, session_index_map, dry_run=args.dry_run
    )
    rollout_mtime_restored_seen, rollout_mtime_restored = restore_rollout_timestamps(
        codex_root, session_index_map, dry_run=args.dry_run
    )
    sqlite_updated = update_sqlite_provider(codex_root, args.provider, dry_run=args.dry_run)
    sqlite_timestamps_updated = repair_sqlite_thread_timestamps(codex_root, dry_run=args.dry_run)

    print(
        json.dumps(
            {
                "codex_root": str(codex_root),
                "current_provider": current_provider,
                "target_provider": args.provider,
                "backup_dir": str(backup_dir) if backup_dir else None,
                "rollout_seen": rollout_seen,
                "rollout_changed": rollout_changed,
                "rollout_mtime_restored_seen": rollout_mtime_restored_seen,
                "rollout_mtime_restored": rollout_mtime_restored,
                "sqlite_updated": sqlite_updated,
                "sqlite_timestamps_updated": sqlite_timestamps_updated,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
