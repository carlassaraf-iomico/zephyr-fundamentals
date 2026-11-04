#!/usr/bin/env python3
"""Read the student's board from board.txt and work out how CI builds for it.

Students declare their board once, in L2, in a one-line `board.txt` at the
repository root:

    nucleo_f401re

Any Zephyr board target works (`esp32_devkitc/esp32/procpu`, `frdm_k64f@...`),
and `native_sim` is the choice for students without hardware. Every task with
app code (L2, L4, L6, L7) is then built for that board. Tests still run on
native_sim, since CI cannot run real hardware.

    board.py resolve --root zephyr-course --json board.json [--github-output FILE]
        Reads board.txt, checks the board exists in this Zephyr, and records what
        the build needs: the SDK toolchain and the west projects (HALs) to fetch.
    board.py mark board.json setup=failed
        Records that CI could not fetch modules or install the toolchain.

Checkers import check_build() to turn board.json and the build folder into
feedback. Needs ZEPHYR_BASE (and Zephyr's base Python requirements).
"""
import argparse
import difflib
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BOARD_FILE = "board.txt"
NATIVE = "native_sim"
EXAMPLE = "nucleo_f401re"
# <board>[@<revision>][/<soc>[/<cpucluster>][/<variant>]], as Zephyr's boards.cmake parses it.
# Restricting the characters also keeps the value safe to pass around in the workflow.
TARGET_RE = re.compile(r"^([A-Za-z0-9_-]+)(@[A-Za-z0-9_.-]+)?((?:/[A-Za-z0-9_-]*)+)?$")

ARCH_TOOLCHAIN = {
    "arm": "arm-zephyr-eabi",
    "arm64": "aarch64-zephyr-elf",
    "riscv": "riscv64-zephyr-elf",
    "x86": "x86_64-zephyr-elf",
    "arc": "arc-zephyr-elf",
    "posix": "host",  # native_sim and friends build with the runner's gcc
}
# Folder under zephyr/soc/ -> the west projects (HALs) its boards need. A vendor not
# listed here fetches every project in the student's west.yml.
SOC_VENDOR_PROJECTS = {
    "st": ["hal_stm32"],
    "nxp": ["hal_nxp"],
    "nordic": ["hal_nordic"],
    "espressif": ["hal_espressif"],
    "raspberrypi": ["hal_rpi_pico"],
    "infineon": ["hal_infineon"],
    "silabs": ["hal_silabs"],
    "atmel": ["hal_atmel"],
    "microchip": ["hal_microchip"],
    "ti": ["hal_ti"],
    "renesas": ["hal_renesas"],
    "gd": ["hal_gigadevice"],
    "ambiq": ["hal_ambiq"],
    "intel": [],
    "qemu": [],
    "cdns": [],
}
ARM_PROJECTS = ["cmsis_6"]
# Projects whose binary blobs a plain app build needs (`west blobs fetch`).
BLOB_PROJECTS = {"hal_espressif"}


# ---------------------------------------------------------------- board.txt

def problem(message, kind="fail", path=None):
    return {"message": message, "kind": kind, "path": path}


def find_board_file(root):
    """-> (relative path or None, problem or None). Accepts misplaced or miscased files, with a fix."""
    if BOARD_FILE in os.listdir(root):  # exact name, also on case-insensitive file systems
        return BOARD_FILE, None
    for name in sorted(os.listdir(root)):
        if name.lower() == BOARD_FILE and os.path.isfile(os.path.join(root, name)):
            return name, problem(f"Rename `{name}` to `{BOARD_FILE}`: file names are case-sensitive on Linux.",
                                 path=name)
    for path in sorted(glob.glob(os.path.join(root, "*", BOARD_FILE))):
        rel = os.path.relpath(path, root)
        if not rel.startswith((".", "deps")):
            return rel, problem(f"Move `{rel}` to the repository root: CI reads `{BOARD_FILE}` from there.",
                                path=rel)
    return None, None


def read_target(root, rel):
    """-> (target or None, problem or None)"""
    with open(os.path.join(root, rel), errors="replace") as f:
        lines = [l.split("#", 1)[0].strip() for l in f]
    words = [w for l in lines for w in l.split()]
    if not words:
        return None, problem(f"Write your board's name in `{rel}`, for example `{EXAMPLE}`, "
                             f"or `{NATIVE}` if you have no board.", path=rel)
    if len(words) > 1:
        shown = ", ".join(f"`{w[:40]}`" for w in words[:3])
        return None, problem(f"Keep only the board's name in `{rel}`; it has {shown}.", path=rel)
    if not TARGET_RE.match(words[0]):
        return None, problem(f"`{rel}` should hold only a board name such as `{EXAMPLE}`; "
                             f"`{words[0][:40]}` isn't one.", path=rel)
    return words[0], None


# ------------------------------------------------------------ Zephyr lookup

def zephyr_scripts():
    base = os.environ.get("ZEPHYR_BASE")
    if not base:
        sys.exit("ZEPHYR_BASE is not set")
    sys.path.insert(0, os.path.join(base, "scripts"))
    return Path(base)


def load_boards(zephyr_base, root):
    """All HWMv2 boards in Zephyr plus the repo's own boards/ (L5 custom boards)."""
    import list_boards  # from ZEPHYR_BASE/scripts
    roots = [zephyr_base, Path(root)]
    args = argparse.Namespace(board_roots=roots, soc_roots=roots, arch_roots=roots,
                              board=None, board_dir=[])
    try:
        return list_boards.find_v2_boards(args), list_boards
    except SystemExit as e:  # e.g. a student board that clashes with a Zephyr one
        raise RuntimeError(str(e))


def find_soc(zephyr_base, root, name):
    import list_hardware
    systems = list_hardware.find_v2_systems(argparse.Namespace(soc_roots=[zephyr_base, Path(root)]))
    return systems.get_soc(name)


def yaml_arch(board, identifier):
    """`arch:` from the board's twister YAML for this target (falls back to any of the board's YAMLs)."""
    import yaml
    dirs = board.directories if isinstance(board.directories, list) else [board.directories]
    found = []
    for d in dirs:
        for y in sorted(Path(d).glob("*.yaml")):
            try:
                data = yaml.safe_load(y.read_text()) or {}
            except Exception:
                continue
            if isinstance(data, dict) and data.get("arch"):
                found.append((data.get("identifier"), data["arch"]))
    for ident, arch in found:
        if ident == identifier:
            return arch
    archs = {arch for _, arch in found}
    return archs.pop() if len(archs) == 1 else None


def xtensa_toolchain(soc):
    """Xtensa toolchains are per SoC: CONFIG_SOC_TOOLCHAIN_NAME, e.g. espressif_esp32."""
    conds = {f"SOC_{soc.name.upper()}", f"SOC_SERIES_{(soc.series or '').upper()}"}
    for folder in soc.folder:
        for kconfig in sorted(Path(folder).rglob("Kconfig*")):
            text = kconfig.read_text(errors="replace")
            m = re.search(r"^config SOC_TOOLCHAIN_NAME\b(.*?)(?=^\S|\Z)", text, re.M | re.S)
            if not m:
                continue
            for name, cond in re.findall(r'default\s+"([^"]+)"(?:\s+if\s+(\w+))?', m.group(1)):
                if not cond or cond in conds:
                    return f"xtensa-{name}_zephyr-elf"
    return None


def manifest_projects(workspace):
    try:
        out = subprocess.run(["west", "list", "-f", "{name}"], cwd=workspace, capture_output=True,
                             text=True, check=True).stdout
        return set(out.split())
    except (OSError, subprocess.CalledProcessError):
        return None


def resolve(root, workspace=None):
    """-> info dict for board.json."""
    info = {"board": NATIVE, "declared": False, "file": None, "problems": [], "buildable": True,
            "arch": "posix", "toolchain": "host", "projects": [], "board_root": None, "setup": "ok"}
    rel, p = find_board_file(root)
    if p:
        info["problems"].append(p)
    if rel is None:
        info["missing"] = True
        info["problems"].append(problem(
            f"No `{BOARD_FILE}` at the repository root, so CI built for `{NATIVE}`. Add one with your "
            f"board's name (for example `{EXAMPLE}`) so CI builds for the board you use.", kind="note"))
        return info
    info["file"] = rel
    target, p = read_target(root, rel)
    if p:
        info["problems"].append(p)
        info["buildable"] = False
        return info
    info["board"], info["declared"] = target, True

    zephyr_base = zephyr_scripts()
    try:
        boards, list_boards = load_boards(zephyr_base, root)
    except RuntimeError as e:
        info["problems"].append(problem(f"Zephyr could not list the boards: {e}", path=rel))
        info["buildable"] = False
        return info
    name, revision, quals = TARGET_RE.match(target).groups()
    board = boards.get(name)
    if board is None:
        close = difflib.get_close_matches(name, boards, n=1, cutoff=0.8)
        hint = (f" Did you mean `{close[0]}`?" if close else "") + " `west boards` lists the board names."
        info["problems"].append(problem(f"`{rel}` names `{name}`, which this Zephyr version doesn't have.{hint}",
                                        path=rel))
        info["buildable"] = False
        return info

    # Same rules as zephyr/cmake/modules/boards.cmake: the SoC may be left out only on single-SoC boards.
    targets = list_boards.board_v2_qualifiers(board)
    q = (quals or "").lstrip("/")
    if len(board.socs) == 1:
        if not quals:
            q = board.socs[0].name
        elif quals.startswith("//"):
            q = board.socs[0].name + "/" + quals[2:]
    if targets and q not in targets:
        options = ", ".join(f"`{name}/{t}`" for t in targets[:4])
        what = f"`{target}` is not a target of `{name}`" if quals else f"`{name}` needs its CPU in the name"
        info["problems"].append(problem(f"{what}: write one of {options} in `{rel}`.", path=rel))
        info["buildable"] = False
        return info

    in_repo = Path(board.dir).resolve().is_relative_to(Path(root).resolve())
    if in_repo:
        info["board_root"] = "."
    identifier = f"{name}/{q}" if q else name
    arch = yaml_arch(board, identifier)
    soc = find_soc(zephyr_base, root, q.split("/")[0]) if q else None
    if arch == "xtensa" and soc:
        toolchain = xtensa_toolchain(soc)
    else:
        toolchain = ARCH_TOOLCHAIN.get(arch)
    info["arch"], info["toolchain"] = arch, toolchain
    if not toolchain:
        info["problems"].append(problem(
            f"CI can't tell which toolchain `{target}` needs, so it didn't build the app. "
            "A teacher will build it by hand.", kind="note"))
        info["buildable"] = False
        return info
    if toolchain == "host":
        return info

    # West projects to fetch, filtered by what the student's west.yml has.
    vendor = None
    if soc and soc.folder:
        parts = Path(soc.folder[0]).resolve().parts
        if "soc" in parts:
            vendor = parts[len(parts) - 1 - parts[::-1].index("soc") + 1]
    needed = SOC_VENDOR_PROJECTS.get(vendor)
    if needed is None:
        info["projects"] = ["all"]
        return info
    needed = needed + (ARM_PROJECTS if arch == "arm" else [])
    have = manifest_projects(workspace or os.path.dirname(os.path.abspath(root)))
    if have is not None:
        missing = [n for n in needed if n not in have]
        if missing:
            names = ", ".join(f"`{n}`" for n in missing)
            info["problems"].append(problem(
                f"Add {names} to the `name-allowlist` in `west.yml`: `{target}` needs "
                f"{'it' if len(missing) == 1 else 'them'} to build.", path="west.yml"))
            info["buildable"] = False
        needed = [n for n in needed if n in have]
    info["projects"] = needed
    return info


def sdk_version():
    try:
        return Path(os.environ["ZEPHYR_BASE"], "SDK_VERSION").read_text().strip()
    except (KeyError, OSError):
        return ""


# ------------------------------------------------------------- for checkers

def load_info(path):
    with open(path) as f:
        return json.load(f)


def info_for(board, declared):
    """board.json equivalent for a local run with --board/--board-declared."""
    return {"board": board, "declared": declared, "problems": [], "buildable": True, "setup": "ok"}


ERROR_RES = (  # most specific first
    re.compile(r"devicetree error: .*"),
    re.compile(r"(?P<path>[^\s:]+\.(?:c|h|cpp|dts|dtsi|overlay|conf)):(?P<line>\d+):(?:\d+:)? (?:fatal )?error: .*"),
    re.compile(r"CMake Error.*"),
    re.compile(r"(?:error|ERROR): (?!command exited with status).*"),  # not west's "cmake failed" summary
)


def first_error(log_path, root):
    """-> (message, path, line) from the first error in a build log, paths made relative to root."""
    prefix = re.compile(re.escape(os.path.realpath(root).rstrip("/") + "/") + "|" +
                        re.escape(root.rstrip("/") + "/"))
    try:
        with open(log_path, errors="replace") as f:
            lines = [re.sub(r"\x1b\[[0-9;]*m", "", l).strip() for l in f]
    except OSError:
        return None, None, None
    for rx in ERROR_RES:
        for i, l in enumerate(lines):
            m = rx.search(l)
            if not m:
                continue
            msg = prefix.sub("", m.group(0))
            if msg.startswith("CMake Error"):
                # CMake puts the reason on the following lines, up to the first blank line.
                more = []
                for nxt in lines[i + 1:]:
                    if not nxt:
                        break
                    more.append(nxt)
                msg = (msg + " " + " ".join(more)).strip()
                msg = prefix.sub("", msg)
            path = line = None
            if "path" in rx.groupindex:
                path = prefix.sub("", m.group("path"))
                line = int(m.group("line"))
            return msg[:300], path, line
    return None, None, None


DT_MISSING_RE = re.compile(r"DT_N_(ALIAS|NODELABEL)_(\w+?)_(?:P_|EXISTS|ORD|FULL_NAME)")


def devicetree_hint(log_path, board):
    """A plain-words reason for the cryptic `__device_dts_ord_DT_N_ALIAS_led0_...` build errors."""
    try:
        text = open(log_path, errors="replace").read()
    except OSError:
        return None
    m = DT_MISSING_RE.search(text) if "error" in text else None
    if not m:
        return None
    kind, name = m.groups()
    if kind == "ALIAS":
        return (f"`{board}`'s devicetree has no `{name}` alias, which `DT_ALIAS({name})` needs: add it in an "
                f"overlay, or declare a board that has it.")
    return f"`{board}`'s devicetree has no node labelled `{name}`, which `DT_NODELABEL({name})` needs."


def check_build(report, info, build_dir, app, require_file=False):
    """Record the board and build checks. True when the build output exists and can be checked.
    require_file: board.txt is a deliverable of this task (L2), so a missing one fails."""
    board = info["board"]
    if require_file and info.get("missing"):
        report.check(False, f"`{BOARD_FILE}` declares your board",
                     fix=f"Add `{BOARD_FILE}` at the repository root with your board's name, for example "
                         f"`{EXAMPLE}`, or `{NATIVE}` if you have no board. CI builds every task for it.")
    for p in info.get("problems", []):
        if require_file and info.get("missing"):
            continue
        if p["kind"] == "note":
            report.note(p["message"])
        else:
            report.check(False, f"`{BOARD_FILE}` names a board CI can build", fix=p["message"], path=p.get("path"))
    if not info.get("buildable", True):
        return False
    if info.get("setup") != "ok":
        report.note(f"CI could not install the toolchain or modules for `{board}`, so the build was not "
                    "checked. This is a CI problem, not yours; a teacher will rerun it.")
        return False
    zdir = os.path.join(build_dir, "zephyr")
    built = any(os.path.isfile(os.path.join(zdir, n)) for n in ("zephyr.elf", "zephyr.exe"))
    if not built:
        if info.get("declared"):
            log = info.get("build_log")
            err, path, line = first_error(log, info.get("root") or "zephyr-course") if log else (None, None, None)
            hint = devicetree_hint(log, board) if log else None
            detail = (f" {hint}" if hint else f" The first error is `{err}`." if err
                      else " The build step of this run shows the error.")
            report.check(False, f"the app builds for `{board}`",
                         fix=f"Make the app build for `{board}`: `west build -b {board} {app}` fails.{detail}",
                         path=path, line=line)
        else:
            report.note(f"The `{board}` build failed. This is expected when the overlay uses labels that "
                        f"only your board has; declare the board in `{BOARD_FILE}`.")
        return False
    report.check(True, f"the app builds for `{board}`")
    return True


# ---------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="read board.txt and write board.json")
    r.add_argument("--root", default=".", help="repository root (default: current directory)")
    r.add_argument("--json", required=True, help="write board.json here")
    r.add_argument("--workspace", help="west workspace, to list the projects in west.yml (default: the root's parent)")
    r.add_argument("--github-output", help="also append step outputs to this file ($GITHUB_OUTPUT)")
    m = sub.add_parser("mark", help="set fields in board.json, e.g. setup=failed")
    m.add_argument("json")
    m.add_argument("fields", nargs="+")
    args = ap.parse_args()

    if args.cmd == "mark":
        info = load_info(args.json)
        for f in args.fields:
            k, _, v = f.partition("=")
            info[k] = v
        with open(args.json, "w") as f:
            json.dump(info, f, indent=2)
        return 0

    root = os.path.abspath(args.root)
    info = resolve(root, args.workspace)
    info["root"] = root
    info["sdk_version"] = sdk_version()
    with open(args.json, "w") as f:
        json.dump(info, f, indent=2)
    print(json.dumps(info, indent=2))
    if args.github_output:
        build = info["buildable"]
        with open(args.github_output, "a") as f:
            f.write(f"board={info['board']}\n")
            f.write(f"build={'true' if build else 'false'}\n")
            f.write(f"toolchain={(info['toolchain'] or '') if build else ''}\n")
            f.write(f"projects={' '.join(info['projects']) if build else ''}\n")
            f.write(f"projects-key={'-'.join(info['projects']) if build else ''}\n")
            blobs = [p for p in info["projects"] if p in BLOB_PROJECTS] if build else []
            f.write(f"blobs={' '.join(blobs)}\n")
            f.write(f"board-root={info['board_root'] or ''}\n")
            f.write(f"sdk-version={info['sdk_version']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
