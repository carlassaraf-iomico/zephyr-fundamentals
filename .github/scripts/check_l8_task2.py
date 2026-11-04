#!/usr/bin/env python3
"""Check l8-task2: coverage of the ring_buf module.

CI runs the tests with coverage itself, so the student does not need to commit
the report:

    west twister -T tests/ring_buf -p native_sim --outdir twister-out \\
        --coverage --coverage-tool gcovr --coverage-basedir app/modules/ring_buf
    python3 .github/scripts/check_l8_task2.py --twister-out twister-out

Checks:
  1. The l8-task1 checks: the 7 stubs are implemented and all 8 tests pass.
  2. gcovr's summary of app/modules/ring_buf meets the targets in tasks.md:
     lines >= 81%, functions 100%, branches >= 64%. When a target is missed, the
     message names the functions never called or the first lines never run.

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import json
import os
import sys

from homework_report import Report
from check_l8_task1 import run_checks, static_checks

MODULE_DIR = "app/modules/ring_buf"
TARGETS = (  # (summary key, label, minimum %), most actionable first
    ("function_percent", "Function", 100.0),
    ("line_percent", "Line", 81.0),
    ("branch_percent", "Branch", 64.0),
)
MAX_LISTED = 5


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def module_files(report_json):
    """gcovr --json files, keyed by path relative to the module directory."""
    return {f["file"]: f for f in (report_json or {}).get("files", [])}


def source_path(rel):
    """'src/ring_buf.c' (relative to the coverage basedir) -> repo-relative path."""
    return f"{MODULE_DIR}/{rel}"


def uncovered_functions(files):
    out = []
    for rel, f in sorted(files.items()):
        for fn in f.get("functions", []):
            if not fn.get("execution_count"):
                name = fn.get("demangled_name") or fn.get("name")
                out.append((name, source_path(rel), fn.get("lineno")))
    return out


def merged_lines(f):
    """gcovr 8 may list a source line once per function; merge them by line number."""
    merged = {}
    for ln in f.get("lines", []):
        if ln.get("gcovr/noncode") or ln.get("gcovr/excluded"):
            continue
        m = merged.setdefault(ln["line_number"], {"count": 0, "branches": []})
        m["count"] += ln.get("count") or 0
        m["branches"] += [b for b in ln.get("branches") or [] if not b.get("gcovr/excluded")]
    return sorted(merged.items())


def uncovered_lines(files):
    return [(source_path(rel), n) for rel, f in sorted(files.items())
            for n, m in merged_lines(f) if not m["count"]]


def partial_branch_lines(files):
    """Lines that ran but where some branch outcome never happened."""
    return [(source_path(rel), n) for rel, f in sorted(files.items())
            for n, m in merged_lines(f)
            if m["count"] and any(not b.get("count") for b in m["branches"])]


def lines_text(items):
    """[(path, 12), (path, 40)] -> '12, 40' (single file) for a short message."""
    nums = sorted({n for _, n in items})
    shown = ", ".join(str(n) for n in nums[:MAX_LISTED])
    return shown + (f" and {len(nums) - MAX_LISTED} more" if len(nums) > MAX_LISTED else "")


def coverage_checks(report, twister_out):
    summary = load(os.path.join(twister_out, "coverage_summary.json"))
    if not report.check(summary is not None, "the coverage report was generated",
                        fix="Make the tests build and run with `west twister -T tests/ring_buf -p native_sim "
                            "--coverage --coverage-tool gcovr --coverage-basedir app/modules/ring_buf`; "
                            "no coverage report was produced."):
        return
    files = module_files(load(os.path.join(twister_out, "coverage.json")))
    if not summary.get("files") and not files:
        report.fail_hard(f"The coverage report has no files under `{MODULE_DIR}`; check `--coverage-basedir`.")
        return

    for key, label, target in TARGETS:
        value = summary.get(key)
        value = float(value) if value is not None else 0.0
        ok = value >= target
        target_txt = f"{target:g}%" if target < 100 else "100%"
        check_label = f"{label} coverage {value:.1f}% (target {'≥ ' if target < 100 else ''}{target_txt})"
        fix, path, line = None, None, None
        if not ok:
            fix = f"{label} coverage of `{MODULE_DIR}` is {value:.1f}%; add tests to reach {'at least ' if target < 100 else ''}{target_txt}."
            if key == "function_percent":
                missing = uncovered_functions(files)
                if missing:
                    names = ", ".join(f"`{n}()`" for n, _, _ in missing[:MAX_LISTED])
                    fix = (f"Function coverage of `{MODULE_DIR}` is {value:.1f}%; add tests that call "
                           f"{names}, which no test calls yet.")
                    _, path, line = missing[0]
            elif key == "line_percent":
                missing = uncovered_lines(files)
                if missing:
                    fix += f" No test runs lines {lines_text(missing)} of `{missing[0][0]}`."
                    path, line = missing[0]
            elif key == "branch_percent":
                missing = partial_branch_lines(files)
                if missing:
                    fix += f" Cover both outcomes of the conditions on lines {lines_text(missing)} of `{missing[0][0]}`."
                    path, line = missing[0]
        report.check(ok, check_label, fix=fix, path=path, line=line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--twister-out", default="twister-out",
                    help="twister --outdir of the coverage run (default: twister-out)")
    ap.add_argument("--platform", default="native_sim", help="platform twister ran on (default: native_sim)")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()

    report = Report("l8-task2", "ring_buf coverage")
    if static_checks(report, os.path.abspath(args.root)):
        run_checks(report, os.path.join(args.twister_out, "twister.json"), args.platform)
        coverage_checks(report, args.twister_out)
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
