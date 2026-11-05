#!/usr/bin/env python3
"""Check l2-task1: the course repo forked, blinky built for the student's board.

Requirements (tasks.md, Lecture 2):
  1. Fork iomico-public/zephyr-course and set up the workspace: the pushed repo is
     the fork itself, with `app/` at its root (not a Zephyr tree, not the west
     workspace around it).
  2. Build the LED blink app for the student's board, declared in `board.txt`
     (one line, e.g. `nucleo_f401re`; `native_sim` without hardware).
  3-4. Flash it and see the LED toggle every second. CI can't flash; it notes
     when the code toggles no LED (fine for boards without one) or waits
     something other than 1000 ms. Neither fails the task.

Layers:
  - Layout (always, no Zephyr needed; --layout-only prints true/false so the
    workflow can skip the Zephyr setup for a wrong repo).
  - Sources: app/src toggles a GPIO/LED, and the delay works out to 1000 ms
    (literals, #defines, consts, K_MSEC/K_SECONDS, CONFIG_ values from the build).
  - Build (with --board-info and --build-dir): board.txt is valid and the app
    builds for that board (board-build action, board.py).

Usage:
    python3 .github/scripts/check_l2_task1.py [--root REPO] [--layout-only]
        [--build-dir build --board-info board.json] [--json out.json]

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import glob
import os
import re
import sys

from homework_report import Report
from check_l8_task1 import strip_comments
import board as board_info  # imports Zephyr's scripts only when resolving, so layout checks run without Zephyr

UPSTREAM = "iomico-public/zephyr-course"
PERIOD_MS = 1000
SRC_EXT = (".c", ".cpp", ".cc")
TOGGLE_CALLS = ("gpio_pin_toggle_dt", "gpio_pin_toggle", "gpio_pin_set_dt", "gpio_pin_set",
                "gpio_pin_set_raw", "gpio_port_toggle_bits", "gpio_port_set_bits", "gpio_port_clear_bits",
                "gpio_port_set_bits_raw", "gpio_port_clear_bits_raw", "led_on", "led_off", "led_on_dt",
                "led_off_dt", "led_set_brightness", "led_set_brightness_dt",
                "led_strip_update_rgb", "led_strip_update_channels")  # RGB LEDs on many ESP32 boards
# call -> (index of the argument with the delay, unit of a bare number in it)
DELAY_ARGS = {
    "k_msleep": (0, "ms"), "k_usleep": (0, "us"), "k_busy_wait": (0, "us"), "k_sleep": (0, "timeout"),
    "k_timer_start": (2, "timeout"),  # the period; the initial duration is arg 1
    "k_work_schedule": (1, "timeout"), "k_work_reschedule": (1, "timeout"),
    "k_work_schedule_for_queue": (2, "timeout"), "k_work_reschedule_for_queue": (2, "timeout"),
}
CONSTANTS = {"MSEC_PER_SEC": "1000", "USEC_PER_MSEC": "1000", "USEC_PER_SEC": "1000000", "K_NO_WAIT": "0"}
TIMEOUT_MACROS = (  # (macro, factor to ms)
    ("K_MSEC", "1"), ("K_SECONDS", "1000"), ("K_USEC", "0.001"), ("K_MINUTES", "60000"),
    ("K_TIMEOUT_ABS_MS", "1"),
)
NUM_SUFFIX_RE = re.compile(r"\b(\d+(?:\.\d+)?)[uUlLfF]+\b")
CAST_RE = re.compile(r"\(\s*(?:const\s+)?(?:unsigned\s+|signed\s+)?(?:u?int(?:8|16|32|64)?_t|int|long|unsigned|"
                     r"k_timeout_t|uint|size_t)\s*\)")
ARITH_RE = re.compile(r"^[\d\s.+\-*/()]+$")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def call_args(code, name):
    """(argument text, offset) for every call of `name(...)` in code."""
    for m in re.finditer(r"\b%s\s*\(" % re.escape(name), code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"(": 1, ")": -1}.get(code[i], 0)
            i += 1
        yield code[m.end():i - 1], m.start()


# ---------------------------------------------------------------- layout
def check_layout(report, root):
    """True when the repo is the zephyr-course fork with app/ at its root."""
    entries = set(os.listdir(root))
    if "Kconfig.zephyr" in entries or {"arch", "kernel"} <= entries:
        report.check(False, "the repository is your zephyr-course fork",
                     fix=f"Push `l2-task1` to your fork of `{UPSTREAM}` with `app/` at the repository root; "
                         "the tag currently points at a copy of the Zephyr source tree.")
        return False
    app_cmake = os.path.join(root, "app", "CMakeLists.txt")
    nested = [d for d in sorted(entries) if os.path.isdir(os.path.join(root, d))
              and os.path.isfile(os.path.join(root, d, "west.yml"))
              and os.path.isfile(os.path.join(root, d, "app", "CMakeLists.txt"))]
    workspace = ".west" in entries or os.path.isdir(os.path.join(root, "deps", "zephyr")) or nested
    if not os.path.isfile(app_cmake):
        moved = find_zephyr_app(root)
        if moved and not workspace:
            where = "the repository root" if moved == "." else f"`{moved}/`"
            fix = (f"Move the app from {where} to `app/`, as the fork ships it: CI and the later tasks build "
                   "`app/`.")
            report.check(False, "`app/CMakeLists.txt` is at the repository root",
                         fix=fix, path=os.path.join(moved, "CMakeLists.txt") if moved != "." else "CMakeLists.txt")
            return False
        if workspace:
            fix = ("Push `l2-task1` from your zephyr-course repository itself, not the west workspace around "
                   "it, so `app/` is at the repository root.")
        else:
            fix = (f"Keep the `app/` folder from `{UPSTREAM}` at the repository root; "
                   "`app/CMakeLists.txt` is missing.")
        report.check(False, "`app/CMakeLists.txt` is at the repository root", fix=fix)
        return False
    report.check(True, "`app/CMakeLists.txt` is at the repository root")
    if workspace:
        what = ", ".join(f"`{d}/`" for d in [".west", "deps"] + nested if d in entries)
        report.note(f"The repository also has {what}: those belong to the west workspace around the repo, "
                    "and west fetches them, so they don't need to be committed.")
    return report.check(os.path.isfile(os.path.join(root, "west.yml")), "`west.yml` is at the repository root",
                        fix=f"Restore `west.yml` at the repository root from `{UPSTREAM}`: west uses it to fetch "
                            "Zephyr for this repo.", path="west.yml")


def find_zephyr_app(root):
    """A Zephyr app (CMakeLists.txt with find_package(Zephyr)) at the root or one or two levels down."""
    for pattern in ("CMakeLists.txt", "*/CMakeLists.txt", "app/*/CMakeLists.txt"):
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            rel = os.path.relpath(os.path.dirname(path), root)
            if rel.split(os.sep)[0] in ("tests", "deps", "modules", "zephyr", "samples"):
                continue
            if "find_package(Zephyr" in read(path).replace(" ", ""):
                return rel
    return None


# ---------------------------------------------------------------- period
def definitions(code):
    """Object-like #defines and constants assigned once: name -> expression text."""
    defs = {}
    for m in re.finditer(r"^[ \t]*#[ \t]*define[ \t]+(\w+)[ \t]+([^\n]+)", code, re.M):
        defs[m.group(1)] = m.group(2).strip()
    assigned = {}
    for m in re.finditer(r"(?<![=!<>+\-*/%&|^])\b(\w+)\s*=\s*([^;=][^;]*);", code):
        assigned.setdefault(m.group(1), []).append(m.group(2).strip())
    for name, values in assigned.items():
        if len(values) == 1 and name not in defs:
            defs[name] = values[0]
    return defs


def config_values(root, build_dir):
    """CONFIG_ values: the build's .config first, then app/prj.conf."""
    vals = {}
    for path in (os.path.join(root, "app", "prj.conf"),
                 os.path.join(build_dir, "zephyr", ".config") if build_dir else None):
        if path and os.path.isfile(path):
            for m in re.finditer(r"^(CONFIG_\w+)=(\d+)\s*$", read(path), re.M):
                vals[m.group(1)] = m.group(2)
    return vals


def to_ms(expr, unit, defs):
    """Milliseconds an argument stands for, or None when it can't be worked out."""
    text = expr
    for _ in range(20):  # expand names, at most 20 rounds
        new = re.sub(r"\b[A-Za-z_]\w*\b",
                     lambda m: f"({defs[m.group(0)]})" if m.group(0) in defs and m.group(0) not in
                     dict(TIMEOUT_MACROS) else m.group(0), text)
        if new == text:
            break
        text = new
    is_timeout = False
    for _ in range(20):  # innermost K_MSEC(...) etc. first
        new = text
        for macro, factor in TIMEOUT_MACROS:
            new = re.sub(r"\b%s\s*\(([^()]*)\)" % macro, r"((\1)*%s)" % factor, new)
        if new == text:
            break
        is_timeout, text = True, new
    text = CAST_RE.sub("", NUM_SUFFIX_RE.sub(r"\1", text))
    if not ARITH_RE.match(text):
        return None
    try:
        value = float(eval(text, {"__builtins__": {}}, {}))  # digits and + - * / ( ) only, checked above
    except Exception:
        return None
    if unit == "us" and not is_timeout:
        value /= 1000
    return value


def check_sources(report, root, build_dir):
    src_dir = os.path.join(root, "app", "src")
    files = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(src_dir) for f in fs if f.endswith(SRC_EXT))
    if not report.check(files, "`app/src` has the blinky code",
                        fix="Keep the blinky code in `app/src/` (`main.c` or `main.cpp`) as the fork ships it."):
        return
    codes = {f: strip_comments(read(f)) for f in files}
    rel = {f: os.path.relpath(f, root) for f in files}
    main = next((f for f in files if os.path.basename(f).startswith("main.")), files[0])

    toggles = [(f, name) for f, code in codes.items() for name in TOGGLE_CALLS
               if re.search(r"\b%s\s*\(" % name, code)]
    if not toggles:
        # The task asks for a blinking LED only "if there's an LED on your board".
        report.note("The code doesn't toggle an LED (`gpio_pin_toggle_dt()` or similar). That's fine if your "
                    "board has no LED; otherwise toggle it in the main loop.")
        return
    report.check(True, "the code toggles an LED")

    defs = dict(CONSTANTS)
    for code in codes.values():
        defs.update(definitions(code))
    defs.update(config_values(root, build_dir))
    delays = []  # (file, line, call text, ms or None)
    for f, code in codes.items():
        for name, (idx, unit) in DELAY_ARGS.items():
            for args, pos in call_args(code, name):
                parts = split_args(args)
                arg = parts[idx] if idx < len(parts) else ""
                ms = to_ms(arg, unit, defs)
                if name == "k_timer_start" and ms == 0 and len(parts) > 1:
                    ms = to_ms(parts[1], unit, defs)  # one-shot timer: the duration
                delays.append((f, line_of(code, pos), f"{name}({' '.join(args.split())})", ms))
    # The period is a note, not a failure (decided Nov 4): L2 is about the fork, the board and the build.
    if not delays:
        report.note(f"The code doesn't wait between LED toggles; the task asks for one toggle per second, "
                    f"for example with `k_msleep({PERIOD_MS})` in `{rel[main]}`.")
        return
    known = [d for d in delays if d[3] is not None]
    if any(abs(d[3] - PERIOD_MS) < 0.5 for d in known) or (
            len(known) > 1 and len(known) == len(delays) and abs(sum(d[3] for d in known) - PERIOD_MS) < 0.5):
        report.check(True, f"the LED waits {PERIOD_MS} ms between toggles")
    elif known and len(known) == len(delays):
        f, line, call, ms = known[0]
        report.note(f"The task asks for one toggle per second: `{call}` in `{rel[f]}` line {line} waits "
                    f"{ms:g} ms.")
    else:
        report.note("CI couldn't work out how long the LED waits between toggles; an instructor will check that "
                    "it's one second.")


def split_args(args):
    """Split a call's argument text on top-level commas."""
    out, depth, cur = [], 0, ""
    for ch in args:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += {"(": 1, ")": -1}.get(ch, 0)
        cur += ch
    out.append(cur)
    return [a.strip() for a in out]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--layout-only", action="store_true",
                    help="print `true` when the layout is right (Zephyr setup can run), `false` otherwise")
    ap.add_argument("--build-dir", help="`west build` directory of app/")
    ap.add_argument("--board-info", help="board.json from the board-build action")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    report = Report("l2-task1", "blinky on your board")
    if args.layout_only:
        print("true" if check_layout(report, root) else "false")
        return 0
    if check_layout(report, root):
        check_sources(report, root, args.build_dir)
        if args.board_info and os.path.isfile(args.board_info):
            board_info.check_build(report, board_info.load_info(args.board_info), args.build_dir or "build",
                                   "app", require_file=True)
        elif args.board_info:
            report.note("CI did not get to build the app; an instructor will check the build.")
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
