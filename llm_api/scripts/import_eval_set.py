#!/usr/bin/env python3
"""
Merge rated examples into the eval dataset used by eval_rag.py.

The eval set grows from real, already-rated traffic (shadow LLM exports), not from
invented questions. This is the intake: point it at an export, it normalises the
rows and merges them into each project's project_library/{project_id}/casos/eval_questions.json,
keyed by (project_id, question) so re-importing the same export is a no-op.

Usage:
  python scripts/import_eval_set.py --input export.jsonl
  python scripts/import_eval_set.py --input export.json --project bikeanjoall_2026
  python scripts/import_eval_set.py --input export.jsonl --dry-run

Input: JSON array, or JSONL (one object per line). Fields per row:

  project_id         required  str
  question           required  str, non-empty
  expected_keywords  optional  list[str]  all must appear in the answer
  forbidden_keywords optional  list[str]  none may appear in the answer
  max_chars          optional  int        answer length ceiling
  model              optional  str        alias: fast | compact | smart | reasoner
  system_prompt      optional  str        runtime prompt, when the client sends one

Unknown fields are dropped with a warning rather than carried into the dataset:
eval_rag.py ignores them, so keeping them would only make the file drift from what
is actually scored.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LLM_ROOT = SCRIPT_DIR.parent
LIBRARY_ROOT = LLM_ROOT / "project_library"


def cases_path(project_id: str) -> Path:
    """Same place scripts/eval_rag.py reads (docs/27)."""
    return LIBRARY_ROOT / project_id / "casos" / "eval_questions.json"


def _label(path: Path) -> str:
    return str(path.relative_to(LLM_ROOT) if path.is_relative_to(LLM_ROOT) else path)

# Same list as scripts/eval_rag.py BUCKETS (what «good» means for the case).
BUCKETS = ("org_factual", "org_link", "user_system", "silence", "unsorted")
REQUIRED_FIELDS = ("project_id", "question")
# Mirrors what eval_rag.py reads per row; anything else is not scored.
OPTIONAL_FIELDS = (
    "expected_keywords",
    "forbidden_keywords",
    "max_chars",
    "model",
    "system_prompt",
    "bucket",
)
_LIST_FIELDS = ("expected_keywords", "forbidden_keywords")


def load_rows(path: Path) -> list[dict]:
    """Read a JSON array or a JSONL file into a list of dicts."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.lstrip().startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("JSON root must be an array of objects")
        return data
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {lineno} is not valid JSON: {exc}") from exc
    return rows


def normalize_row(raw: object, *, index: int) -> tuple[dict | None, list[str]]:
    """Return (row, problems). A row with problems is skipped, never half-imported."""
    problems: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"row {index}: expected an object, got {type(raw).__name__}"]

    row: dict = {}
    for field in REQUIRED_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"row {index}: missing or empty required field '{field}'")
        else:
            row[field] = value.strip()
    if problems:
        return None, problems

    for field in _LIST_FIELDS:
        if field not in raw or raw[field] is None:
            continue
        value = raw[field]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            problems.append(f"row {index}: '{field}' must be a list of strings")
            continue
        cleaned = [v.strip() for v in value if v and v.strip()]
        if cleaned:
            row[field] = cleaned

    if raw.get("max_chars") is not None:
        value = raw["max_chars"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            problems.append(f"row {index}: 'max_chars' must be a positive integer")
        else:
            row["max_chars"] = value

    if raw.get("bucket") is not None:
        if raw["bucket"] not in BUCKETS:
            problems.append(f"row {index}: 'bucket' must be one of {', '.join(BUCKETS)}")
        else:
            row["bucket"] = raw["bucket"]

    for field in ("model", "system_prompt"):
        value = raw.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            problems.append(f"row {index}: '{field}' must be a non-empty string")
        else:
            row[field] = value.strip()

    if problems:
        return None, problems
    return row, []


def unknown_fields(raw: dict) -> list[str]:
    known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    return sorted(k for k in raw if k not in known)


def row_key(row: dict) -> tuple[str, str]:
    """Identity of an eval row: same project asking the same thing."""
    return row["project_id"], " ".join(row["question"].split()).lower()


def merge_rows(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """Append rows whose key is new; leave existing rows untouched.

    Curation lives in the dataset (a human wrote those keywords), so an incoming row
    never overwrites one already there.
    """
    seen = {row_key(r) for r in existing if isinstance(r, dict) and "question" in r}
    merged = list(existing)
    added = skipped = 0
    for row in incoming:
        key = row_key(row)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        merged.append(row)
        added += 1
    return merged, added, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge rated examples into the eval dataset")
    parser.add_argument("--input", type=Path, required=True, help="JSON array or JSONL export")
    parser.add_argument("--dataset", type=Path, help="One file for every row instead of each project's casos/")
    parser.add_argument("--project", help="Import only rows of this project_id")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    try:
        raw_rows = load_rows(args.input)
    except ValueError as exc:
        print(f"Could not read {args.input}: {exc}", file=sys.stderr)
        return 1

    if not raw_rows:
        print(f"No rows in {args.input}")
        return 0

    incoming: list[dict] = []
    problems: list[str] = []
    for i, raw in enumerate(raw_rows, start=1):
        row, row_problems = normalize_row(raw, index=i)
        if row_problems:
            problems.extend(row_problems)
            continue
        if args.project and row["project_id"] != args.project:
            continue
        if isinstance(raw, dict):
            extra = unknown_fields(raw)
            if extra:
                print(f"  row {i}: dropped unscored field(s): {', '.join(extra)}", file=sys.stderr)
        incoming.append(row)

    for problem in problems:
        print(f"SKIP {problem}", file=sys.stderr)

    if not incoming:
        print("Nothing to import.", file=sys.stderr)
        return 1

    targets: dict[Path, list[dict]] = {}
    for row in incoming:
        path = args.dataset or cases_path(row["project_id"])
        targets.setdefault(path, []).append(row)

    print()
    for path, rows in sorted(targets.items()):
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        merged, added, skipped = merge_rows(existing, rows)
        print(f"{_label(path)}: {added} added, {skipped} already present, {len(merged)} rows")
        by_project: dict[str, int] = {}
        for row in merged:
            by_project[row["project_id"]] = by_project.get(row["project_id"], 0) + 1
        for project, count in sorted(by_project.items()):
            # docs/13 asks for 20-30 real questions per project as a usable baseline.
            note = "" if count >= 20 else "  (below the 20 the baseline needs)"
            print(f"  {project}: {count}{note}")
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(problems)} skipped as invalid")
    print("Dry run: nothing written." if args.dry_run else "Written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
