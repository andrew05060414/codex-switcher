#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
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
    parser.add_argument("--provider", required=True)
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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
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


def rewrite_rollouts(codex_root: Path, target_provider: str, dry_run: bool) -> tuple[int, int, list[Path]]:
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
        if current_provider == target_provider:
            continue
        changed += 1
        changed_paths.append(rollout)
        if dry_run:
            continue
        parsed["payload"]["model_provider"] = target_provider
        new_first_line = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        new_text = new_first_line if newline == "" else new_first_line + newline + rest
        rollout.write_text(new_text, encoding="utf-8", newline="")
    return seen, changed, changed_paths


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

    config_path = codex_root / CONFIG_FILE_NAME
    current_provider = read_current_provider(config_path)
    rollout_seen, rollout_changed, rollout_paths = rewrite_rollouts(
        codex_root, args.provider, dry_run=True
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
        codex_root, args.provider, dry_run=args.dry_run
    )
    sqlite_updated = update_sqlite_provider(codex_root, args.provider, dry_run=args.dry_run)

    print(
        json.dumps(
            {
                "codex_root": str(codex_root),
                "current_provider": current_provider,
                "target_provider": args.provider,
                "backup_dir": str(backup_dir) if backup_dir else None,
                "rollout_seen": rollout_seen,
                "rollout_changed": rollout_changed,
                "sqlite_updated": sqlite_updated,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
