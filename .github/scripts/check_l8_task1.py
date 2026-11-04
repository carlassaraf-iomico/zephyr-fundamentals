#!/usr/bin/env python3
"""Check l8-task1: the 7 ring_buf unit tests.

Two layers:
  1. Static: each of the 7 stubs in tests/ring_buf/src/test_ring_buf.c no longer
     calls ztest_test_skip() and contains at least one zassert_*/zexpect_* check.
  2. Run (with --twister-json): twister ran all 8 tests on the platform and every
     one passed, none skipped.

In CI, run twister first and pass its JSON:

    west twister -T tests/ring_buf -p native_sim --outdir twister-out
    python3 .github/scripts/check_l8_task1.py --twister-json twister-out/twister.json

Without --twister-json only the static layer runs (useful locally on macOS,
where native_sim is not available).

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import json
import os
import re
import sys

from homework_report import Report

TEST_FILE = "tests/ring_buf/src/test_ring_buf.c"

PROVIDED = ("ring_buf_init", "test_fresh_state")
STUBS = [
    ("ring_buf_init", "test_reinit_clears_state"),
    ("ring_buf_push_pop", "test_single_push_pop"),
    ("ring_buf_push_pop", "test_fifo_order"),
    ("ring_buf_push_pop", "test_push_full_returns_enospc"),
    ("ring_buf_boundaries", "test_peek_does_not_consume"),
    ("ring_buf_boundaries", "test_pop_null_returns_einval"),
    ("ring_buf_boundaries", "test_is_full_after_fill"),
]

ZTEST_RE = re.compile(r"\bZTEST(?:_F|_USER|_USER_F)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\{")
ASSERT_RE = re.compile(r"\b(zassert|zexpect)_\w+\s*\(")
SKIP_RE = re.compile(r"\bztest_test_skip\s*\(")
ASSERT_FAIL_RE = re.compile(r"Assertion failed at \S*test_ring_buf\.c:(\d+): (\w+):")


def strip_comments(src):
    """Blank out comments and string contents, keeping offsets (and so line numbers) intact."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', blank, src, flags=re.S)


def find_tests(src):
    """Map (suite, name) -> (body, line) for every ZTEST in the file."""
    code = strip_comments(src)
    tests = {}
    for m in ZTEST_RE.finditer(code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        line = code.count("\n", 0, m.start()) + 1
        tests[(m.group(1), m.group(2))] = (code[m.end():i - 1], line)
    return tests


def static_checks(report, root):
    path = os.path.join(root, TEST_FILE)
    if not os.path.isfile(path):
        report.check(False, f"`{TEST_FILE}` exists at the repository root",
                     fix=f"Implement the 7 stub tests in `{TEST_FILE}` at the repository root, not in a copy of the project.")
        return False
    tests = find_tests(open(path, encoding="utf-8", errors="replace").read())

    for suite, name in STUBS:
        if (suite, name) not in tests:
            report.check(False, f"`{name}` exists",
                         fix=f"Keep the stub `ZTEST({suite}, {name})` and implement it as `TEST_SPEC.md` describes.",
                         path=TEST_FILE)
            continue
        body, line = tests[(suite, name)]
        if not report.check(not SKIP_RE.search(body), f"`{name}` is implemented (no `ztest_test_skip()`)",
                            fix=f"Replace `ztest_test_skip()` in `{name}` with the test body from `TEST_SPEC.md`.",
                            path=TEST_FILE, line=line):
            continue
        report.check(ASSERT_RE.search(body), f"`{name}` checks results with `zassert_*`",
                     fix=f"Add `zassert_*` checks to `{name}` for each expected value in `TEST_SPEC.md`.",
                     path=TEST_FILE, line=line)

    if PROVIDED not in tests:
        report.note(f"The provided example `{PROVIDED[1]}` was removed.")
    extra = sorted(n for s, n in tests if (s, n) not in STUBS and (s, n) != PROVIDED)
    if extra:
        report.note(f"{len(extra)} test(s) beyond the spec: {', '.join(f'`{n}`' for n in extra)}.")
    return True


def short(identifier):
    """'homework.unit.ring_buf.ring_buf_init.test_fresh_state' -> 'fresh_state'."""
    last = identifier.rsplit(".", 1)[-1]
    return last[5:] if last.startswith("test_") else last


def run_checks(report, twister_json, platform):
    if not os.path.isfile(twister_json):
        report.check(False, f"twister ran the tests on `{platform}`",
                     fix=f"Make the tests build and run: `west twister -T tests/ring_buf -p {platform}` produced no results.")
        return
    data = json.load(open(twister_json))
    suites = [s for s in data.get("testsuites", [])
              if s.get("platform", "").split("/")[0] == platform.split("/")[0]]
    if not report.check(suites, f"twister ran the tests on `{platform}`",
                        fix=f"Make `west twister -T tests/ring_buf -p {platform}` run the `ring_buf` tests; "
                            "twister selected no test suite for that platform."):
        return

    for suite in suites:
        status = suite.get("status")
        if status in ("error", "failed") and not suite.get("testcases"):
            reason = suite.get("reason") or status
            report.check(False, "the test binary builds and runs",
                         fix=f"Fix the build of `tests/ring_buf`: twister reports \"{reason}\". "
                             f"Run `west twister -T tests/ring_buf -p {platform} -v` to see the error.")
            return

    cases, failed_at = {}, {}
    for suite in suites:
        for case in suite.get("testcases", []):
            cases[short(case.get("identifier", ""))] = case
        # "Assertion failed at CMAKE_SOURCE_DIR/src/test_ring_buf.c:106: <suite>_test_<name>: ..."
        # Only the line number is kept; the assertion text may contain student strings.
        for m in ASSERT_FAIL_RE.finditer(suite.get("log") or ""):
            for _, name in STUBS + [PROVIDED]:
                if m.group(2).endswith(name):
                    failed_at.setdefault(short(name), int(m.group(1)))

    expected = [short(n) for _, n in STUBS] + [short(PROVIDED[1])]
    for name in expected:
        case = cases.get(name)
        if case is None:
            report.check(False, f"`test_{name}` ran",
                         fix=f"Make `test_{name}` run under twister; it is missing from the results.")
            continue
        status = case.get("status", "unknown")
        line = failed_at.get(name)
        if status == "skipped":
            fix = f"Implement `test_{name}`; twister reports it as skipped."
        elif line:
            fix = (f"Fix `test_{name}`: the assertion on line {line} fails. "
                   "Check the expected value against `TEST_SPEC.md`.")
        else:
            fix = f"Fix `test_{name}`: it {status} under twister. Check its assertions against `TEST_SPEC.md`."
        report.check(status == "passed", f"`test_{name}` passes", fix=fix,
                     path=TEST_FILE if line else None, line=line)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--twister-json", help="twister.json from `west twister -T tests/ring_buf ...`")
    ap.add_argument("--platform", default="native_sim", help="platform twister ran on (default: native_sim)")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()

    report = Report("l8-task1", "ring_buf unit tests")
    if static_checks(report, os.path.abspath(args.root)) and args.twister_json:
        run_checks(report, args.twister_json, args.platform)
    elif not args.twister_json:
        report.note("Tests were not run (no --twister-json); only the source was checked.")
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
