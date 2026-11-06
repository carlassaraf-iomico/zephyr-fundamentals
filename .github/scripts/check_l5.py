#!/usr/bin/env python3
"""Check l5-task1 / l5-task2: a custom board that Zephyr can find and build hello_world for.

Requirements (tasks.md, Lecture 5):
  task1  A custom board made by copy/rename, placed in <project_root>/boards/, and the
         hello_world sample builds for it.
  task2  A custom board made from scratch, hello_world builds for it, and it prints
         "Board Initialized" before main() runs.

Checks (both tasks):
  1. A board folder with board.yml, a .dts, Kconfig.<board> and <board>_defconfig;
     each missing file is one change.
  2. Zephyr can find it: boards/ at the repository root, <app>/boards/ (the app
     folder is a default BOARD_ROOT), or a folder added to BOARD_ROOT in an app's
     CMakeLists.txt or in zephyr/module.yml.
  3. (with --board-info/--build-dir) Zephyr's samples/hello_world builds for it,
     and its name doesn't clash with a Zephyr board.
task2 adds:
  4. A source file in the board folder prints "Board Initialized" (case and
     punctuation ignored) from SYS_INIT() or a board init hook, so it runs before main().
  5. The built image contains the message (the file is built and the hook enabled).
How a board was made can't be checked, so task1 and task2 boards are never compared.

Usage:
    python3 .github/scripts/check_l5.py --task l5-task1 [--root REPO] --print-board [--github-output F]
    python3 .github/scripts/check_l5.py --task l5-task2 [--root REPO]
        [--build-dir build --board-info board.json] [--json out.json]

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import os
import re
import sys

from homework_report import Report
import board as board_info  # imports Zephyr's scripts only when resolving

SKIP_DIRS = {".git", ".github", "deps", "twister-out", "build", "node_modules", "venv", "__pycache__"}
SRC_EXT = (".c", ".cpp", ".cc", ".h")
MSG = "Board Initialized"
MSG_RE = re.compile(r"board\W{0,3}initiali[sz]ed", re.I)
MSG_BYTES_RE = re.compile(rb"board\W{0,3}initiali[sz]ed", re.I)
HOOK_RE = re.compile(r"\bSYS_INIT(?:_NAMED)?\s*\(|\bvoid\s+(board_(?:early|late)_init_hook)\s*\(|"
                     r"\b(?:int|void)\s+(board_init)\s*\(")
CMAKE_ROOT_RE = re.compile(r"(?:list\s*\(\s*APPEND|set\s*\()\s*BOARD_ROOT\s+([^)]*)\)", re.I)
CMAKE_DIR_VARS = ("${CMAKE_CURRENT_SOURCE_DIR}", "${CMAKE_CURRENT_LIST_DIR}", "${CMAKE_SOURCE_DIR}",
                  "${APPLICATION_SOURCE_DIR}", "${PROJECT_SOURCE_DIR}")
HELLO = "samples/hello_world"


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def strip_comments_keep_strings(src):
    """Blank out C comments (keeping strings, which hold the message), offsets intact."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0)) if m.group(0).startswith("/") else m.group(0)
    return re.sub(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', blank, src, flags=re.S)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


# ---------------------------------------------------------------- finding boards
def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                             and not os.path.isfile(os.path.join(dirpath, d, "CMakeCache.txt")))
        yield os.path.relpath(dirpath, root), filenames


def board_name(path, files):
    if "board.yml" in files:
        text = read(os.path.join(path, "board.yml"))
        m = re.search(r"^\s*board:\s*\n(?:.*\n)*?\s*name:\s*['\"]?([\w-]+)", text, re.M)
        if m:
            return m.group(1)
    for f in files:
        if f.startswith("Kconfig.") and f[8:] not in ("defconfig", "board", "sysbuild", "soc"):
            return f[8:]
    for f in files:
        if f.endswith("_defconfig"):
            return f[:-len("_defconfig")]
    return os.path.basename(path)


class BoardDir:
    def __init__(self, root, rel, files):
        self.rel, self.files = rel, sorted(files)
        self.path = os.path.join(root, rel)
        self.name = board_name(self.path, files)
        parts = rel.split(os.sep)
        idx = max((i for i, p in enumerate(parts) if p == "boards"), default=None)
        self.root_rel = os.sep.join(parts[:idx]) if idx is not None else None  # its BOARD_ROOT
        self.findable = False

    def missing(self):
        n, d = self.name, f"`{self.rel}/`"
        out = []
        if "board.yml" not in self.files:
            out.append(("`board.yml`", f"Add `board.yml` to {d}: Zephyr needs it to find the board."))
        if not any(f.endswith(".dts") for f in self.files):
            out.append(("a `.dts` file", f"Add the board's devicetree `{n}.dts` to {d}."))
        if f"Kconfig.{n}" not in self.files:
            other = [f for f in self.files if f.startswith("Kconfig.") and f[8:] not in
                     ("defconfig", "sysbuild", "board", "soc")]
            fix = (f"Rename `{other[0]}` to `Kconfig.{n}`: Zephyr reads the file named after the board."
                   if other else f"Add `Kconfig.{n}` to {d}: it selects the board's SoC.")
            out.append((f"`Kconfig.{n}`", fix))
        if not any(f == f"{n}_defconfig" or (f.startswith(n + "_") and f.endswith("_defconfig"))
                   for f in self.files):
            other = [f for f in self.files if f.endswith("_defconfig")]
            fix = (f"Rename `{other[0]}` in {d} to `{n}_defconfig`: Zephyr only reads the defconfig named after "
                   "the board." if other else f"Add `{n}_defconfig` to {d}.")
            out.append((f"`{n}_defconfig`", fix))
        return out

    def sources(self):
        """(repo-relative path, code without comments) of the C sources in the board folder and below."""
        out = []
        for dp, _, fs in os.walk(self.path):
            for f in sorted(fs):
                if f.endswith(SRC_EXT):
                    p = os.path.join(dp, f)
                    rel = os.path.normpath(os.path.join(self.rel, os.path.relpath(p, self.path)))
                    out.append((rel, strip_comments_keep_strings(read(p))))
        return out


def is_board_dir(rel, files):
    if "board.yml" in files:
        return True
    if "boards" not in rel.split(os.sep)[:-1]:
        return False  # without board.yml, only folders below a boards/ folder count
    return any(f.endswith((".dts", "_defconfig")) or (f.startswith("Kconfig.") and f != "Kconfig.defconfig")
               for f in files)


def zephyr_apps(root):
    for rel, files in walk(root):
        if "CMakeLists.txt" in files and rel.split(os.sep)[0] not in ("tests", "samples"):
            text = read(os.path.join(root, rel, "CMakeLists.txt"))
            if "find_package(Zephyr" in text.replace(" ", ""):
                yield ("" if rel == "." else rel), text


def board_roots(root):
    """Folders whose boards/ Zephyr searches: the repo root (CI passes it, as tasks.md asks),
    every app folder, BOARD_ROOT additions in an app's CMakeLists.txt, and zephyr/module.yml."""
    roots = {""}
    for app, text in zephyr_apps(root):
        roots.add(app)
        for m in CMAKE_ROOT_RE.finditer(text):
            for tok in m.group(1).split():
                tok = tok.strip("\"'")
                if tok == "BOARD_ROOT" or "${ZEPHYR_BASE}" in tok or tok.startswith("$ENV"):
                    continue
                for var in CMAKE_DIR_VARS:
                    tok = tok.replace(var, os.path.join(root, app))
                if "${" in tok:
                    continue
                path = tok if os.path.isabs(tok) else os.path.join(root, app, tok)
                rel = os.path.relpath(os.path.normpath(path), root)
                roots.add("" if rel == "." else rel)
    module = os.path.join(root, "zephyr", "module.yml")
    if os.path.isfile(module):
        m = re.search(r"^\s*board_root:\s*['\"]?([^\s'\"]+)", read(module), re.M)
        if m:
            rel = os.path.normpath(m.group(1))
            roots.add("" if rel == "." else rel)
    return roots


def find_boards(root, task):
    roots = board_roots(root)
    dirs = [BoardDir(root, rel, files) for rel, files in walk(root) if rel != "." and is_board_dir(rel, files)]
    for b in dirs:
        b.findable = b.root_rel is not None and b.root_rel in roots

    def score(b):
        # task2: the board that prints the message first (a repo often keeps the task1 board too).
        srcs = b.sources() if task == "l5-task2" else []
        has_msg = any(MSG_RE.search(code) for _, code in srcs)
        has_hook = any(HOOK_RE.search(code) for _, code in srcs)
        return (has_msg, has_hook, b.findable, -len(b.missing()), b.root_rel == "", b.rel)
    return sorted(dirs, key=score, reverse=True)


# ---------------------------------------------------------------- checks
def check_board(report, root, b):
    report.check(True, f"custom board `{b.name}` in `{b.rel}/`")
    if not b.missing():
        report.check(True, f"the board has `board.yml`, a `.dts`, `Kconfig.{b.name}` and `{b.name}_defconfig`")
    for what, fix in b.missing():
        report.check(False, f"the board has {what}", fix=fix, path=b.rel)
    report.check(b.findable, "Zephyr can find the board", path=b.rel,
                 fix=f"Move the board directory `{b.rel}/` to `boards/` at the repository root or to "
                     "`app/boards/`, or add its parent folder to `BOARD_ROOT`.")


# Zephyr 4.1+ board hooks run before main() too; last batch, ~30 approved boards used them.
ACCEPT_BOARD_HOOKS = True
SYS_INIT_RE = re.compile(r"\bSYS_INIT\s*\(\s*(\w+)|\bSYS_INIT_NAMED\s*\(\s*\w+\s*,\s*(\w+)")
BOARD_HOOK_RE = re.compile(r"\b(board_(?:early|late)_init_hook)\s*\(")


def hook_enabled(b, hook):
    """The board turns the hook on: `select BOARD_LATE_INIT_HOOK` in a Kconfig file, or `=y` in its defconfig."""
    opt = hook.upper()
    for dp, _, fs in os.walk(b.path):
        for f in fs:
            if f.startswith("Kconfig") or f.endswith("_defconfig"):
                text = read(os.path.join(dp, f))
                if re.search(r"^\s*(select\s+%s\b|CONFIG_%s\s*=\s*y)" % (opt, opt), text, re.M):
                    return True
    return False


def body_of(code, name):
    """(start, end) of the body of function `name` defined in code, or None."""
    m = re.search(r"\b%s\s*\([^;{}()]*\)\s*\{" % re.escape(name), code)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(code) and depth:
        depth += {"{": 1, "}": -1}.get(code[i], 0)
        i += 1
    return m.end(), i - 1


def prints_message(srcs, name, depth=0):
    """(path, line) where function `name` (or a board helper it calls) prints the message, or None."""
    for p, c in srcs:
        span = body_of(c, name)
        if not span:
            continue
        m = MSG_RE.search(c, *span)
        if m:
            return p, line_of(c, m.start())
        if depth < 2:
            for call in re.finditer(r"\b(\w+)\s*\(", c[span[0]:span[1]]):
                if call.group(1) != name:
                    got = prints_message(srcs, call.group(1), depth + 1)
                    if got:
                        return got
    return None


def check_message(report, root, b):
    """task2: a function the board registers with SYS_INIT() prints the message (before main()).
    Returns (ok, file with the message, init function)."""
    label = f'the board prints "{MSG}" before `main()` (`SYS_INIT()`' + (" or a board hook)" if ACCEPT_BOARD_HOOKS else ")")
    srcs = b.sources()
    inits = [(p, m.group(1) or m.group(2), line_of(c, m.start())) for p, c in srcs for m in SYS_INIT_RE.finditer(c)]
    for p, fn, _ in inits:
        got = prints_message(srcs, fn)
        if got:
            report.check(True, label)
            return True, got[0], fn
    with_msg = [(p, c) for p, c in srcs if MSG_RE.search(c)]
    for p, c in with_msg:  # printed from a board hook (a file may define both hooks)
        m = next((h for h in BOARD_HOOK_RE.finditer(c) if prints_message(srcs, h.group(1))), None)
        if not m:
            continue
        hook = m.group(1)
        if not ACCEPT_BOARD_HOOKS:
            report.check(False, label, path=p, line=line_of(c, m.start()),
                         fix=f'Print "{MSG}" from a function registered with `SYS_INIT()` in `{p}` instead of '
                             f"`{hook}()`.")
            return False, p, None
        if report.check(hook_enabled(b, hook), label, path=p, line=line_of(c, m.start()),
                        fix=f"Enable `CONFIG_{hook.upper()}` so `{hook}()` runs: add `select {hook.upper()}` to "
                            f"`Kconfig.{b.name}`, or `CONFIG_{hook.upper()}=y` to `{b.name}_defconfig`."):
            return True, p, f"hook:{hook}"
        return False, p, None
    if with_msg and inits:  # the message is there, but not in the registered function
        p, fn, line = inits[0]
        mp, mc = with_msg[0]
        report.check(False, label, path=mp, line=line_of(mc, MSG_RE.search(mc).start()),
                     fix=f'Print "{MSG}" from `{fn}()`, the function `{p}` registers with `SYS_INIT()`, so it '
                         "runs before `main()`.")
        return False, mp, None
    with_hook = [(p, c) for p, c in srcs if HOOK_RE.search(c)]
    if with_msg:
        p, c = with_msg[0]
        report.check(False, label, path=p, line=line_of(c, MSG_RE.search(c).start()),
                     fix=f'Print "{MSG}" from a `SYS_INIT()` function (or `board_late_init_hook()`) in `{p}`, '
                         "so it runs before `main()`.")
        return False, p, None
    if with_hook:
        p, c = with_hook[0]
        report.check(False, label, path=p, line=line_of(c, HOOK_RE.search(c).start()),
                     fix=f'Make the `SYS_INIT` hook in `{p}` print exactly "{MSG}".')
        return False, p, None
    elsewhere = None
    for rel, files in walk(root):
        for f in files:
            if f.endswith(SRC_EXT):
                p = os.path.normpath(os.path.join(rel, f))
                if not p.startswith(b.rel + os.sep):
                    c = strip_comments_keep_strings(read(os.path.join(root, p)))
                    m = MSG_RE.search(c)
                    if m:
                        elsewhere = (p, line_of(c, m.start()))
                        break
        if elsewhere:
            break
    if elsewhere:
        report.check(False, label, path=elsewhere[0], line=elsewhere[1],
                     fix=f'Move the code that prints "{MSG}" from `{elsewhere[0]}` into a source file in the '
                         f"board directory `{b.rel}/`, run from a `SYS_INIT()` hook, so it prints before `main()`.")
    else:
        report.check(False, label, path=b.rel,
                     fix=f"Add a source file in the board directory `{b.rel}/` that prints \"{MSG}\" from a "
                         "`SYS_INIT()` hook, and add it to the board's `CMakeLists.txt`.")
    return False, None, None


def check_image(report, root, b, build_dir, msg_file, init_fn=None):
    """task2: the message, and the SYS_INIT() entry that prints it, made it into the hello_world image."""
    elf = os.path.join(build_dir, "zephyr", "zephyr.elf")
    try:
        with open(elf, "rb") as f:
            data = f.read()
    except OSError:
        return
    label = f'the `hello_world` image contains "{MSG}"'
    if MSG_BYTES_RE.search(data):
        report.check(True, label)
        if init_fn and init_fn.startswith("hook:"):  # the hook only runs when its option is on
            opt = init_fn[5:].upper()
            cfg = os.path.join(build_dir, "zephyr", ".config")
            if os.path.isfile(cfg):
                report.check(re.search(r"^CONFIG_%s=y" % opt, read(cfg), re.M),
                             f"`CONFIG_{opt}` is on in the build", path=msg_file,
                             fix=f"Enable `CONFIG_{opt}` for `{b.name}` (`select {opt}` in `Kconfig.{b.name}`): "
                                 f"without it, Zephyr never calls `{init_fn[5:]}()`.")
        elif init_fn:  # SYS_INIT(fn, ...) links an init entry named __init_<fn>
            report.check(b"__init_" + init_fn.encode() + b"\0" in data,
                         f"`{init_fn}()` is registered as an init function in the image", path=msg_file,
                         fix=f"Make sure `SYS_INIT({init_fn}, ...)` is compiled: the `hello_world` build for "
                             f"`{b.name}` has no init entry for `{init_fn}()`, so it never runs.")
        return
    fix = (f'The `hello_world` build for `{b.name}` doesn\'t contain "{MSG}": make sure the board\'s source '
           "file is built and its `SYS_INIT` runs.")
    path = msg_file
    if msg_file:
        cmake = os.path.join(b.path, "CMakeLists.txt")
        fname = os.path.basename(msg_file)
        code = strip_comments_keep_strings(read(os.path.join(root, msg_file)))
        hook = HOOK_RE.search(code)
        hook_fn = hook and (hook.group(1) or None)
        cfg = os.path.join(build_dir, "zephyr", ".config")
        config = read(cfg) if os.path.isfile(cfg) else ""
        if not os.path.isfile(cmake):
            fix = (f"Add `CMakeLists.txt` to `{b.rel}/` with `zephyr_library()` and "
                   f"`zephyr_library_sources({fname})`, so the board's code is built.")
            path = b.rel
        elif fname not in read(cmake):
            fix = f"Add `{fname}` to `{b.rel}/CMakeLists.txt` with `zephyr_library_sources({fname})`."
            path = os.path.join(b.rel, "CMakeLists.txt")
        elif hook_fn:
            opt = hook_fn.upper()
            if f"CONFIG_{opt}=y" not in config:
                fix = (f"Enable `CONFIG_{opt}` so `{hook_fn}()` runs: add `select {opt}` to `Kconfig.{b.name}`, "
                       f"or `CONFIG_{opt}=y` to `{b.name}_defconfig`.")
    report.check(False, label, fix=fix, path=path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", required=True, choices=("l5-task1", "l5-task2"))
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--print-board", action="store_true",
                    help="print the custom board CI should build and its BOARD_ROOT, then exit")
    ap.add_argument("--github-output", help="with --print-board: append board= and board-root= to this file")
    ap.add_argument("--build-dir", help="`west build` directory of hello_world")
    ap.add_argument("--board-info", help="board.json from the board-build action")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    boards = find_boards(root, args.task)

    if args.print_board:
        b = boards[0] if boards else None
        name, broot = (b.name, b.root_rel or ".") if b and b.root_rel is not None else ("", "")
        print(f"board={name}\nboard-root={broot}")
        if args.github_output:
            with open(args.github_output, "a") as f:
                f.write(f"board={name}\nboard-root={broot}\n")
        return 0

    title = "custom board, copy/rename" if args.task == "l5-task1" else "custom board, from scratch"
    report = Report(args.task, title)
    if not report.check(boards, "a custom board folder exists",
                        fix="Add your custom board under `boards/<vendor>/<board>/` at the repository root, with "
                            "`board.yml`, `<board>.dts`, `Kconfig.<board>` and `<board>_defconfig`."):
        return report.finish(args.json)
    b = boards[0]
    if len(boards) > 1:
        others = ", ".join(f"`{o.rel}/`" for o in boards[1:4])
        report.note(f"Checked the board in `{b.rel}/`; the repository also has {others}.")
    check_board(report, root, b)
    msg_ok, msg_file, init_fn = check_message(report, root, b) if args.task == "l5-task2" else (False, None, None)
    if args.board_info and os.path.isfile(args.board_info):
        info = board_info.load_info(args.board_info)
        built = board_info.check_build(report, info, args.build_dir or "build", HELLO,
                                       what="`hello_world`")
        if built and msg_ok:  # task2; when the source is wrong, that change already says what to fix
            check_image(report, root, b, args.build_dir or "build", msg_file, init_fn)
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
