#!/usr/bin/env python3
"""Check l4-task1: heartbeat LED from devicetree and Kconfig.

Requirements (tasks.md, Lecture 4):
  1. `app.overlay` adds the alias `app-led` pointing at the board's LED.
  2. `Kconfig` has `int APP_HEARTBEAT_PERIOD_MS`, default 500, range 100-2000.
  3. The C/C++ code takes the GPIO from `DT_ALIAS(app_led)` and sleeps for
     `CONFIG_APP_HEARTBEAT_PERIOD_MS`.
  4. Changing the period in menuconfig changes the blink speed (needs a prompt).

The task builds on `app/`. A separate application folder (e.g. `l4-task1/`)
with the heartbeat work is accepted with a note, as the batch review does.

Layers:
  - Static (always): Kconfig parsed with kconfiglib; overlay and sources read
    with comments removed.
  - Build (with --build-dir): the generated devicetree has the alias and the
    generated .config has the symbol. CI builds for the board in board.txt
    (board-build action, --board-info board.json). Without board.txt it builds
    for native_sim and a failed build is only a note: the overlay may use
    labels that only the student's board has.

Usage:
    python3 .github/scripts/check_l4_task1.py [--root REPO] [--app DIR] \\
        [--build-dir build (--board-info board.json | --board B [--board-declared])] [--json out.json]
    python3 .github/scripts/check_l4_task1.py --print-app   # the app folder CI should build

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import difflib
import glob
import os
import re
import sys

from homework_report import Report
from check_l3_task1 import kc, parse
from check_l8_task1 import strip_comments
import board as board_info

SYMBOL = "APP_HEARTBEAT_PERIOD_MS"
CONFIG = f"CONFIG_{SYMBOL}"
DEFAULT, LOW, HIGH = 500, 100, 2000
SRC_EXT = (".c", ".cpp", ".h", ".hpp")
SKIP_DIRS = {".git", ".github", "deps", "tests", "twister-out", "modules"}

# Calls whose argument sets how long the LED waits.
DELAY_CALLS = ("k_msleep", "k_usleep", "k_sleep", "K_MSEC", "K_USEC", "K_SECONDS", "k_busy_wait",
               "k_timer_start", "k_work_schedule", "k_work_reschedule", "k_work_schedule_for_queue",
               "k_work_reschedule_for_queue", "K_TIMEOUT_ABS_MS")

ALIAS_RE = re.compile(r"\bapp([-_])led\s*=([^;]*);")
ALIAS_START_RE = re.compile(r"\bapp[-_]led\s*=")
# &label, &{/path} or "/path"
TARGET_RE = re.compile(r'^(&[A-Za-z_][\w-]*|&\{/[^{}]*\}|"/[^"]*")$')


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------- app folder
def repo_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                       and not os.path.isfile(os.path.join(dirpath, d, "CMakeCache.txt"))]
        for f in filenames:
            yield os.path.normpath(os.path.join(rel, f))


def find_app(root):
    """The folder holding the heartbeat work: `app` unless another Zephyr app has it and `app` doesn't."""
    def score(d):
        s = 0
        k = os.path.join(root, d, "Kconfig")
        if os.path.isfile(k) and SYMBOL in read(k):
            s += 2
        for p in glob.glob(os.path.join(root, d, "*.overlay")) + glob.glob(os.path.join(root, d, "boards", "*.overlay")):
            if ALIAS_START_RE.search(read(p)):
                s += 1
                break
        return s

    apps = sorted({os.path.dirname(f) for f in repo_files(root) if os.path.basename(f) == "CMakeLists.txt"
                   and "find_package(Zephyr" in read(os.path.join(root, f)).replace(" ", "")})
    best = max(apps, key=lambda d: (score(d), d == "app"), default="app")
    return "app" if score(best) == 0 or score("app") >= score(best) else best


# ---------------------------------------------------------------- Kconfig
def first_true(props):
    """First (value, cond) of a node's own properties whose `if` holds."""
    return next((p for p in props if kc.expr_value(p[-1])), None)


def int_of(sym):
    try:
        return int(sym.str_value, 0)
    except ValueError:
        return None


def check_kconfig(report, root, app):
    rel = f"{app}/Kconfig"
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        wrong_case = next((f for f in os.listdir(os.path.join(root, app)) if f.lower() == "kconfig"), None) \
            if os.path.isdir(os.path.join(root, app)) else None
        report.check(False, f"`{rel}` exists", path=f"{app}/{wrong_case}" if wrong_case else None,
                     fix=(f"Rename `{app}/{wrong_case}` to `{rel}`: names are case-sensitive on Linux, so the "
                          "build ignores it." if wrong_case else
                          f"Add `{rel}` with `config {SYMBOL}` (an `int`, `default {DEFAULT}`, `range {LOW} {HIGH}`)."))
        return
    try:
        kconf = parse(path, root)
    except kc.KconfigError as exc:
        msg = str(exc).strip().splitlines()[0].replace(root + os.sep, "")
        msg = msg.split(". Check that environment variables")[0]
        report.fail_hard(f"Fix this Kconfig error so the file parses: {msg}", path=rel)
        return

    sym = kconf.k.syms.get(SYMBOL)
    if not (sym and sym.nodes):
        defined = [s for s in kconf.k.unique_defined_syms if s.type == kc.INT]
        close = difflib.get_close_matches(SYMBOL, [s.name for s in defined], n=1, cutoff=0.85)
        if close:
            near = kconf.k.syms[close[0]]
            report.check(False, f"`config {SYMBOL}` is defined", **kconf.loc(near.nodes[0]),
                         fix=f"Rename `{close[0]}` to `{SYMBOL}`, and use `{CONFIG}` in the code.")
        else:
            report.check(False, f"`config {SYMBOL}` is defined", path=rel,
                         fix=f"Add `config {SYMBOL}` to `{rel}` as an `int` with `default {DEFAULT}` "
                             f"and `range {LOW} {HIGH}`.")
        return
    node = sym.nodes[0]
    loc = kconf.loc(node)
    if not report.check(sym.type == kc.INT, f"`{SYMBOL}` is an `int`",
                        fix=f"Declare `{SYMBOL}` as an `int`; it is a `{kc.TYPE_TO_STR[sym.type]}` now.", **loc):
        return
    report.check(node.prompt, f"`{SYMBOL}` has a prompt (editable in menuconfig)",
                 fix=f"Give `{SYMBOL}` a prompt, e.g. `int \"Heartbeat period (ms)\"`, so it can be changed in menuconfig.",
                 **loc)

    # Read the symbol's own `range`/`default` lines, ignoring the menu's `if`/`depends on`,
    # which may need Zephyr symbols (GPIO, ...) that are not loaded here.
    rng = first_true([r for n in sym.nodes for r in n.orig_ranges])
    rng = (int_of(rng[0]), int_of(rng[1])) if rng else None
    report.check(rng == (LOW, HIGH), f"`range {LOW} {HIGH}`",
                 fix=(f"Add `range {LOW} {HIGH}` to `{SYMBOL}`." if rng is None else
                      f"Change the range of `{SYMBOL}` to `range {LOW} {HIGH}`; it is {rng[0]}-{rng[1]} now."), **loc)
    dflt = first_true([d for n in sym.nodes for d in n.orig_defaults])
    value = int_of(dflt[0]) if dflt else None
    report.check(value == DEFAULT, f"`default {DEFAULT}`",
                 fix=(f"Add `default {DEFAULT}` to `{SYMBOL}`." if dflt is None else
                      f"Change the default of `{SYMBOL}` to `{DEFAULT}`; it is `{kc.expr_str(dflt[0])}` now."), **loc)


# ---------------------------------------------------------------- overlay
def alias_blocks(code):
    """(start, end) offsets of every `aliases { ... }` body."""
    for m in re.finditer(r"\baliases\s*\{", code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        yield m.end(), i - 1


def find_alias(path):
    """(kind, sep, line): kind is 'ok', 'target' (not a node reference) or 'syntax'; None if absent."""
    text = read(path)
    code = strip_comments(text)  # same offsets as text, comments and strings blanked
    for start, end in alias_blocks(code):
        m = ALIAS_RE.search(code, start, end)
        if m:
            line = line_of(code, m.start())
            target = text[m.start(2):m.end(2)].strip()  # raw text: a path is a string
            if TARGET_RE.match(target):
                return "ok", m.group(1), line
            if "}" in target or "\n" in target:  # ran past the line: a `;` is missing
                return "syntax", None, line
            return "target", m.group(1), line
        m = ALIAS_START_RE.search(code, start, end)
        if m:
            return "syntax", None, line_of(code, m.start())
    return None


def check_overlay(report, root, app):
    main_overlay = f"{app}/app.overlay"
    inside = [main_overlay] + sorted(os.path.relpath(p, root) for p in
                                     glob.glob(os.path.join(root, app, "boards", "*.overlay")) +
                                     glob.glob(os.path.join(root, app, "*.overlay"))
                                     if os.path.relpath(p, root) != main_overlay)
    inside = [p for p in inside if os.path.isfile(os.path.join(root, p))]
    label = "overlay defines the `app-led` alias"
    found = {rel: f for rel in inside if (f := find_alias(os.path.join(root, rel)))}

    def applied(rel):
        # `app.overlay` belongs in the app folder; `boards/` is only for `<board>.overlay` files.
        # app/boards/app.overlay is not accepted, even when CMakeLists.txt adds it.
        return os.path.basename(rel) != "app.overlay" or rel == main_overlay

    usable = [rel for rel in found if applied(rel)]
    if usable:
        rel = next((r for r in usable if found[r][0] == "ok"), usable[0])
        kind, sep, line = found[rel]
        if kind == "syntax":
            report.check(False, label, path=rel, line=line,
                         fix="Fix the `app-led` alias syntax: end the property with `;`, e.g. `app-led = &led0;`, "
                             "and close the `aliases` node with `};`.")
            return
        if rel != main_overlay:
            report.note(f"The `app-led` alias is in `{rel}`, not `{main_overlay}`.")
        report.check(True, label)
        report.check(kind == "ok", "`app-led` points at a node", path=rel, line=line,
                     fix="Point `app-led` at your LED node, e.g. `app-led = &led0;` or `app-led = &{/leds/led_0};`.")
        if sep == "_":
            report.note("The alias is spelled `app_led`; the task asks for `app-led` (both work with `DT_ALIAS(app_led)`).")
        return
    if found:
        rel = next(iter(found))
        report.check(False, label, path=rel, line=found[rel][2],
                     fix=f"Move `{rel}` to `{main_overlay}`: `app.overlay` belongs in the app folder, and "
                         f"`{app}/boards/` is only for `<board>.overlay` files.")
        return

    # Not in the app: maybe in an overlay the build never applies.
    elsewhere = next((f for f in repo_files(root) if f.endswith(".overlay") and not f.startswith(app + os.sep)
                      and find_alias(os.path.join(root, f))), None)
    if elsewhere:
        report.check(False, label, path=elsewhere,
                     fix=f"Move the `app-led` alias from `{elsewhere}` to `{main_overlay}`; the build of `{app}` "
                         "does not apply overlays outside the app folder.")
    elif inside:
        report.check(False, label, path=inside[0],
                     fix=f"Add `app-led = &<your LED node>;` inside an `aliases {{ }}` node in `{inside[0]}`.")
    else:
        report.check(False, label,
                     fix=f"Add `{main_overlay}` with an `aliases` node containing `app-led = &<your LED node>;`.")


# ---------------------------------------------------------------- sources
def call_args(code, name):
    """(argument text, offset) for every call of `name(...)` in code."""
    for m in re.finditer(r"\b%s\s*\(" % re.escape(name), code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"(": 1, ")": -1}.get(code[i], 0)
            i += 1
        yield code[m.end():i - 1], m.start()


FUNC_RE = re.compile(r"\b(\w+)\s*\([^;{}()]*\)\s*(?:const\s*)?\{")


def derived_names(code, seed):
    """Names whose value comes from the seed: `#define X ...seed...`, `X = ...seed...;`,
    and functions that `return ...seed...;`. Repeated until nothing new is found."""
    names = {seed}
    funcs = [(m.group(1), m.end()) for m in FUNC_RE.finditer(code)
             if m.group(1) not in ("if", "for", "while", "switch")]
    while True:
        alt = r"\b(?:%s)\b" % "|".join(re.escape(n) for n in names)
        new = set()
        for m in re.finditer(r"#\s*define\s+(\w+)[^\n]*" + alt, code):
            new.add(m.group(1))
        for m in re.finditer(r"\b(\w+)\s*(?:\[[^\]]*\])?\s*=\s*[^;=]*" + alt, code):
            new.add(m.group(1))
        for m in re.finditer(r"\breturn\b[^;]*" + alt, code):
            owner = [name for name, body in funcs if body < m.start()]
            if owner:
                new.add(owner[-1])
        if new <= names:
            return names
        names |= new


def check_sources(report, root, app):
    files = sorted(f for f in repo_files(os.path.join(root, app)) if f.endswith(SRC_EXT))
    files = [os.path.join(app, f) for f in files]
    if not report.check(files, f"`{app}/src` has the application code",
                        fix=f"Add the heartbeat code to `{app}/src/main.c` (or `main.cpp`)."):
        return
    texts = {f: strip_comments(read(os.path.join(root, f))) for f in files}
    main = next((f for f in files if os.path.basename(f).startswith("main.")), files[0])

    uses_alias = any(re.search(r"\bDT_ALIAS\s*\(\s*app_led\s*\)", t) for t in texts.values())
    other = None
    for f, t in texts.items():
        m = re.search(r"\bDT_ALIAS\s*\(\s*(\w+)\s*\)", t)
        if m and m.group(1) != "app_led":
            other = (f, line_of(t, m.start()), m.group(1))
            break
    if other and not uses_alias:
        report.check(False, "the GPIO comes from `DT_ALIAS(app_led)`", path=other[0], line=other[1],
                     fix=f"Use `DT_ALIAS(app_led)` instead of `DT_ALIAS({other[2]})` for the LED GPIO.")
    else:
        report.check(uses_alias, "the GPIO comes from `DT_ALIAS(app_led)`", path=main,
                     fix="Get the LED with `GPIO_DT_SPEC_GET(DT_ALIAS(app_led), gpios)`.")

    if not report.check(any(re.search(r"\b%s\b" % CONFIG, t) for t in texts.values()),
                        f"the code uses `{CONFIG}`", path=main,
                        fix=f"Use `{CONFIG}` as the blink period in `{main}` instead of a fixed value."):
        return
    sets_delay, fixed = False, None
    for f, t in texts.items():
        alt = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(n) for n in derived_names(t, CONFIG)))
        for call in DELAY_CALLS:
            for args, pos in call_args(t, call):
                if alt.search(args):
                    sets_delay = True
                elif fixed is None and call in ("k_msleep", "k_sleep", "k_usleep"):
                    fixed = (f, line_of(t, pos), call)
    if fixed and not sets_delay:
        report.check(False, f"`{CONFIG}` sets the blink delay", path=fixed[0], line=fixed[1],
                     fix=f"Pass `{CONFIG}` to `{fixed[2]}()` instead of a fixed delay.")
    else:
        report.check(sets_delay, f"`{CONFIG}` sets the blink delay", path=main,
                     fix=f"Sleep for `{CONFIG}` milliseconds between LED toggles, e.g. `k_msleep({CONFIG})`.")


# ---------------------------------------------------------------- build
def check_build(report, app, build_dir, info):
    """Build checks for the board in board.json (see board.py); the board itself is checked there."""
    if not board_info.check_build(report, info, build_dir, app):
        return
    board = info["board"]
    zdir = os.path.join(build_dir, "zephyr")
    dts = os.path.join(zdir, "zephyr.dts")
    if os.path.isfile(dts):
        code = strip_comments(read(dts))
        has = any(ALIAS_START_RE.search(code, s, e) for s, e in alias_blocks(code))
        report.check(has, "the built devicetree has the `app-led` alias", path=f"{app}/app.overlay",
                     fix=f"Make sure the overlay is applied: the `app-led` alias is missing from the "
                         f"`{board}` build's devicetree.")
    cfg = os.path.join(zdir, ".config")
    if os.path.isfile(cfg):
        m = re.search(r"^%s=(\d+)" % CONFIG, read(cfg), re.M)
        if report.check(m, f"`{CONFIG}` is in the build's `.config`", path=f"{app}/Kconfig",
                        fix=f"Make `{SYMBOL}` part of the build: its `if`/`depends on` is off in the "
                            f"`{board}` build, so the code can't use it."):
            if int(m.group(1)) != DEFAULT:
                report.note(f"The build uses {m.group(1)} ms, not the default {DEFAULT}: `prj.conf` or a board "
                            "file sets it.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--app", help="application folder (default: found automatically, normally `app`)")
    ap.add_argument("--print-app", action="store_true", help="print the application folder and exit")
    ap.add_argument("--build-dir", help="`west build` directory of the app, to check the build output")
    ap.add_argument("--board-info", help="board.json from `board.py resolve` (CI); overrides --board")
    ap.add_argument("--board", default="native_sim", help="board the app was built for (local runs)")
    ap.add_argument("--board-declared", action="store_true",
                    help="the student declared this board; a failed build is then a failure, not a note")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    app = args.app or find_app(root)
    if args.print_app:
        print(app)
        return 0

    report = Report("l4-task1", "heartbeat LED from devicetree and Kconfig")
    if app != "app":
        report.note(f"The heartbeat app is in `{app}/`; the task builds on `app/`.")
    check_overlay(report, root, app)
    check_kconfig(report, root, app)
    check_sources(report, root, app)
    if args.build_dir:
        info = (board_info.load_info(args.board_info) if args.board_info
                else board_info.info_for(args.board, args.board_declared))
        check_build(report, app, args.build_dir, info)
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
