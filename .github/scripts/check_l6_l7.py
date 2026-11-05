#!/usr/bin/env python3
"""Check l6-task1, l6-task2, l7-task1 and l7-task2: the LED sensor driver and its shell commands.

Requirements (tasks.md, Lectures 6 and 7; the rules are in .github/rubric/):
  l6-task1  A sensor driver for an LED: `.sample_fetch` turns it on, `.channel_get` turns it off;
            GPIO and instances from devicetree; the app calls the sensor API.
  l6-task2  An extension API function, declared in a header, that changes a field of the driver's
            data struct through the device; `main` calls it.
  l7-task1  A root shell command with `fetch`, `read` and `info` subcommands.
  l7-task2  A `set <value>` subcommand (`SHELL_CMD_ARG`) that rejects a missing or out-of-range
            value with `shell_error` and passes the value to the extension API.

Layers:
  - Static (always): C sources read with comments and strings blanked, plus the bindings and
    overlays. Names are whatever the student chose: the driver is found by its sensor API struct,
    the extension API by what `main` and the shell call.
  - Build (with --build-dir): the app builds for the board in board.txt, the driver and the shell
    code are compiled into it (compile_commands.json), and the devicetree has the driver's node.

Some rules can't be settled by reading the code (an LED level that comes from a variable, a
range the driver checks instead of the shell). Those are recorded as "for a teacher": they never
fail the task, and the result is `under_review` when nothing else failed.

Usage:
    python3 .github/scripts/check_l6_l7.py --task l6-task1 [--root REPO] [--app DIR] \\
        [--build-dir build (--board-info board.json | --board B [--board-declared])] [--json out.json]
    python3 .github/scripts/check_l6_l7.py --task l6-task1 --print-app   # the app folder CI should build

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import json
import os
import re
import sys

from homework_report import Report
from check_l8_task1 import strip_comments
import board as board_info

TASKS = {
    "l6-task1": "LED sensor driver",
    "l6-task2": "driver extension API",
    "l7-task1": "sensor shell commands",
    "l7-task2": "shell `set` command",
}
SRC_EXT = (".c", ".cpp", ".cc", ".h", ".hpp")
SKIP_DIRS = {".git", ".github", ".west", "deps", "tests", "twister-out", "build", "node_modules"}
COURSE_CODE = ("app/modules/calculator", "app/modules/ring_buf")  # given by the course, not the student's
KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "case", "catch",
            "defined", "__attribute__", "typeof", "alignof", "_Static_assert", "static_assert"}

PRINTS = ("shell_print", "shell_fprintf", "shell_info", "shell_warn", "shell_error", "shell_fprintf_normal",
          "shell_fprintf_info", "shell_fprintf_warn", "shell_fprintf_error", "printk", "printf",
          "LOG_INF", "LOG_DBG", "LOG_WRN", "LOG_ERR", "shell_hexdump", "puts", "cout")
DT_GPIO = re.compile(r"\b(GPIO_DT_SPEC_(?:INST_)?GET(?:_BY_IDX)?(?:_OR)?|DT_(?:INST_)?GPIO_(?:PIN|CTLR|FLAGS)"
                     r"(?:_BY_IDX)?|LED_DT_SPEC_(?:INST_)?GET|DT_(?:INST_)?PHANDLE(?:_BY_IDX)?|"
                     r"DEVICE_DT_GET\s*\(\s*DT_(?:INST_)?GPIO_CTLR)\b")
DT_INSTANCE = re.compile(r"\b(SENSOR_DEVICE_DT_INST_DEFINE|DEVICE_DT_INST_DEFINE|SENSOR_DEVICE_DT_DEFINE|"
                         r"DEVICE_DT_DEFINE)\s*\(")
DEVICE_FROM_DT = re.compile(r"\b(DEVICE_DT_GET(?:_ONE|_ANY|_OR_NULL)?|DEVICE_DT_INST_GET|device_get_binding|"
                            r"DEVICE_GET)\s*\(")

ON_WORDS = re.compile(r"^(1|1u|true|high|on|\w*_on|led_on|gpio_output_active|gpio_output_high|"
                      r"gpio_output_init_high|gpio_output_init_logical|!\s*0|!\s*false)$", re.I)
OFF_WORDS = re.compile(r"^(0|0u|false|low|off|\w*_off|led_off|gpio_output_inactive|gpio_output_low|"
                       r"gpio_output_init_low|!\s*1|!\s*true)$", re.I)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def block_end(code, start, open_="{", close="}"):
    """Offset just past the bracket that closes the one opened right before `start`."""
    depth, i = 1, start
    while i < len(code) and depth:
        c = code[i]
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
        i += 1
    return i


def split_args(text):
    """Split a macro or call's argument text at top-level commas."""
    out, depth, cur = [], 0, []
    for c in text:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if out or "".join(cur).strip():  # keep an empty last argument (a blanked string): positions matter
        out.append("".join(cur).strip())
    return out


def calls(code, name, start=0, end=None, member=False):
    """(args text, offset) for every call or macro use of `name(...)` in code[start:end].
    member: also calls through a struct (`api->name(...)`)."""
    end = len(code) if end is None else end
    for m in re.finditer(r"(?<![\w%s])%s\s*\(" % ("" if member else ".>", re.escape(name)), code[:end]):
        if m.start() < start:
            continue
        stop = block_end(code, m.end(), "(", ")")
        yield code[m.end():stop - 1], m.start()


# ---------------------------------------------------------------- sources
class Func:
    def __init__(self, src, name, params, body_start, body_end, static, pos):
        self.src, self.name, self.params = src, name, params
        self.start, self.end, self.static, self.pos = body_start, body_end, static, pos

    @property
    def body(self):
        return self.src.code[self.start:self.end]

    @property
    def path(self):
        return self.src.rel

    @property
    def line(self):
        return line_of(self.src.code, self.pos)

    def param_names(self):
        names = []
        for p in split_args(self.params):
            m = re.search(r"(\w+)\s*(?:\[[^\]]*\])*\s*$", p)
            names.append(m.group(1) if m and p.strip() != "void" else None)
        return names

    def takes_device(self):
        first = (split_args(self.params) or [""])[0]
        return bool(re.search(r"\bstruct\s+device\s*\*", first))


FUNC_RE = re.compile(r"\b(\w+)\s*\(((?:[^;{}()]|\([^;{}()]*\))*)\)\s*(?:const\s*)?\{")


class Src:
    def __init__(self, root, rel):
        self.rel = rel
        self.text = read(os.path.join(root, rel))
        self.code = strip_comments(self.text)
        self.funcs = {}
        # Function definitions, with preprocessor lines (and their `\` continuations) blanked.
        flat = re.sub(r"(?m)^[ \t]*#(?:[^\n]*\\\n)*[^\n]*", lambda m: re.sub(r"[^\n]", " ", m.group(0)), self.code)
        for m in FUNC_RE.finditer(flat):
            name = m.group(1)
            if name in KEYWORDS or name.isupper():
                continue
            # Only a definition: what comes before the name, back to the previous statement, is a type.
            # Macro uses without a `;` (`DT_INST_FOREACH_STATUS_OKAY(X)`) end a statement too.
            before = flat[:m.start()]
            prev = max(before.rfind(";"), before.rfind("}"), before.rfind("{"))
            decl = re.sub(r"\b[A-Z_][A-Z0-9_]*\s*\((?:[^()]|\([^()]*\))*\)", " ", before[prev + 1:])
            if "=" in decl or "(" in decl:
                continue
            end = block_end(self.code, m.end())
            self.funcs.setdefault(name, Func(self, name, m.group(2), m.end(), end - 1,
                                             bool(re.search(r"\bstatic\b", decl)), m.start(1)))

    def includes(self):
        return [os.path.basename(m.group(1)) for m in re.finditer(r'#\s*include\s*[<"]([^>"]+)[>"]', self.text)]


def repo_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith((".", "build"))
                       and not os.path.isfile(os.path.join(dirpath, d, "CMakeCache.txt"))
                       and os.path.normpath(os.path.join(rel, d)) not in COURSE_CODE]
        for f in filenames:
            yield os.path.normpath(os.path.join(rel, f))


class Repo:
    def __init__(self, root):
        self.root = root
        self.files = sorted(repo_files(root))
        self.srcs = {f: Src(root, f) for f in self.files if f.endswith(SRC_EXT)}
        self.funcs = {}
        for s in self.srcs.values():
            for name, fn in s.funcs.items():
                self.funcs.setdefault(name, fn)

    def under(self, folder):
        prefix = "" if folder in ("", ".") else folder.rstrip("/") + "/"
        return [s for f, s in self.srcs.items() if f.startswith(prefix)]


# ---------------------------------------------------------------- the app
def is_app(root, rel_cmake):
    return "find_package(Zephyr" in read(os.path.join(root, rel_cmake)).replace(" ", "")


def find_app(repo, task):
    """The Zephyr app with the task's work: `app` unless another app has it and `app` doesn't."""
    apps = sorted({os.path.dirname(f) for f in repo.files if os.path.basename(f) == "CMakeLists.txt"
                   and is_app(repo.root, f)})
    want = ["sensor_sample_fetch", "sensor_channel_get"] if task.startswith("l6") else ["SHELL_CMD_REGISTER",
                                                                                         "SHELL_CMD_ARG_REGISTER"]

    def score(d):
        return sum(1 for s in repo.under(d) for w in want if w in s.code)
    best = max(apps, key=lambda d: (score(d), d == "app"), default="app")
    return "app" if score(best) == 0 or score("app") >= score(best) else best


# ---------------------------------------------------------------- the driver
class Driver:
    """The student's sensor driver: the source that sets `.sample_fetch` / `.channel_get`."""
    def __init__(self, repo, src):
        self.repo, self.src = repo, src
        self.members = {m.group(1): m.group(2) for m in
                        re.finditer(r"\.\s*(\w+)\s*=\s*\(?\s*&?\s*(\w+)", src.code)}
        self.folder = os.path.dirname(src.rel)
        m = re.search(r"#\s*define\s+DT_DRV_COMPAT\s+(\w+)", src.code)
        self.compat = m.group(1) if m else None
        self.files = repo.under(self.folder) if self.folder else [src]
        if any(os.path.basename(f.rel).startswith("main.") for f in self.files):  # the driver sits in app/src
            stem = os.path.splitext(os.path.basename(src.rel))[0]
            self.files = [f for f in self.files if os.path.splitext(os.path.basename(f.rel))[0] == stem]

    def func(self, name):
        for s in [self.src] + self.files:
            if name in s.funcs:
                return s.funcs[name]
        return self.repo.funcs.get(name)


def find_driver(repo, app, any_driver=False):
    """The sensor driver; with any_driver, a device driver of any kind when there is no sensor one."""
    best = None
    for s in repo.srcs.values():
        if s.rel.endswith((".h", ".hpp")):
            continue
        has = [bool(re.search(r"\.\s*%s\s*=" % k, s.code)) for k in ("sample_fetch", "channel_get")]
        device = bool(DT_INSTANCE.search(s.code) or re.search(r"\bDEVICE_DEFINE\s*\(", s.code))
        if not any(has) and not (any_driver and device):
            continue
        key = (sum(has), device, not s.rel.startswith(f"{app}/src/"))
        if best is None or key > best[0]:
            best = (key, s)
    return Driver(repo, best[1]) if best else None


def resolve_value(expr, func, defines, pos=None, depth=0):
    """'on', 'off', ('param', i) or None for the value passed to a GPIO set call.
    A variable or field (`data->led_on`) resolves to its last assignment before `pos` in the function."""
    e = re.sub(r"\(\s*(?:bool|int|uint\w*|u?int\d+_t)\s*\)", "", expr).strip()
    while e.startswith("(") and e.endswith(")"):
        e = e[1:-1].strip()
    e = defines.get(e, e)
    if func is not None and pos is not None and depth < 3 and re.fullmatch(r"[\w.>\s-]+", e) \
            and not ON_WORDS.match(e) and not OFF_WORDS.match(e):
        target = re.sub(r"\s*(->|\.)\s*", r"\1", e)
        last = None
        for m in re.finditer(r"([\w.>\s*-]+?)\s*=(?!=)\s*([^;]+);", func.src.code[func.start:pos]):
            lhs = re.sub(r"\s*(->|\.)\s*", r"\1", m.group(1)).split()
            if lhs and lhs[-1].lstrip("*") == target:
                last = (m.group(2), func.start + m.start(2))
        if last:
            return resolve_value(last[0], func, defines, last[1], depth + 1)
    if ON_WORDS.match(e):
        return "on"
    if OFF_WORDS.match(e):
        return "off"
    params = func.param_names() if func else []
    if e in params:
        return ("param", params.index(e))
    return None


SET_CALLS = {"gpio_pin_set_dt": 1, "gpio_pin_set": 2, "gpio_pin_set_raw": 2, "gpio_pin_configure_dt": 1,
             "gpio_pin_configure": 2, "led_set_brightness": 2, "led_set_brightness_dt": 1}
FIXED_CALLS = {"gpio_pin_toggle_dt": "toggle", "gpio_pin_toggle": "toggle", "gpio_port_toggle_bits": "toggle",
               "led_on": "on", "led_on_dt": "on", "led_off": "off", "led_off_dt": "off",
               "gpio_port_set_bits": "on", "gpio_port_set_bits_raw": "on",
               "gpio_port_clear_bits": "off", "gpio_port_clear_bits_raw": "off"}


def led_actions(repo, func, defines, depth=0):
    """LED effects of a function, in order: 'on', 'off', 'toggle', ('param', i) or None (unknown)."""
    if func is None or depth > 2:
        return []
    code, out = func.src.code, []
    events = []
    for name, idx in SET_CALLS.items():
        for args, pos in calls(code, name, func.start, func.end):
            a = split_args(args)
            if len(a) > idx:
                val = a[idx]
                if name.startswith("gpio_pin_configure"):
                    val = "on" if re.search(r"OUTPUT_(ACTIVE|HIGH|INIT_HIGH)", val) else \
                          "off" if re.search(r"OUTPUT_(INACTIVE|LOW|INIT_LOW)", val) else None
                    if val is None:
                        continue  # configuring as a plain output: no level
                    events.append((pos, val))
                elif name.startswith("led_set_brightness"):
                    v = resolve_value(val, func, defines, pos)
                    events.append((pos, "off" if v == "off" else v if isinstance(v, tuple) else
                                   ("on" if re.fullmatch(r"\d+", val.strip()) and int(val) > 0 else v)))
                else:
                    events.append((pos, resolve_value(val, func, defines, pos)))
    for name, effect in FIXED_CALLS.items():
        for _, pos in calls(code, name, func.start, func.end):
            events.append((pos, effect))
    # Helpers defined in the repo (`led_set(dev, true)`), with their parameters bound.
    for m in re.finditer(r"\b(\w+)\s*\(", code[func.start:func.end]):
        callee = repo.funcs.get(m.group(1))
        if not callee or callee is func or m.group(1) in SET_CALLS or m.group(1) in FIXED_CALLS:
            continue
        sub = led_actions(repo, callee, defines, depth + 1)
        if not sub:
            continue
        pos = func.start + m.start()
        args = split_args(code[pos + len(m.group(0)):block_end(code, pos + len(m.group(0)), "(", ")") - 1])
        for s in sub:
            if isinstance(s, tuple):
                s = resolve_value(args[s[1]], func, defines, pos) if s[1] < len(args) else None
            events.append((pos, s))
    return [e for _, e in sorted(events, key=lambda x: x[0])]


def led_state(actions):
    """'on', 'off', 'toggle', 'none' or 'unknown' from led_actions."""
    if not actions:
        return "none"
    if "toggle" in actions:
        return "toggle"
    definite = [a for a in actions if a in ("on", "off")]
    if len(definite) != len(actions):
        return "unknown"
    return definite[-1] if len(set(definite)) == 1 else "unknown"


def file_defines(srcs):
    out = {}
    for s in srcs:
        for m in re.finditer(r"#\s*define\s+(\w+)\s+([^\n]+)", s.code):
            out[m.group(1)] = m.group(2).strip().strip("()").strip()
        for m in re.finditer(r"\benum\b[^{;]*\{([^}]*)\}", s.code):
            n = 0
            for item in split_args(m.group(1)):
                k = re.match(r"(\w+)\s*(?:=\s*(\d+))?", item)
                if k:
                    n = int(k.group(2)) if k.group(2) else n
                    out.setdefault(k.group(1), str(n))
                    n += 1
    return out


def check_driver(report, repo, app, task):
    """Driver checks shared by every task. Returns the Driver or None."""
    strict = task in ("l6-task1", "l7-task1")  # the tasks that use .sample_fetch and .channel_get
    drv = find_driver(repo, app, any_driver=not strict)
    own = [fn for fn in repo.funcs.values() if fn.name in ("sensor_sample_fetch", "sensor_channel_get",
                                                           "z_impl_sensor_sample_fetch", "z_impl_sensor_channel_get")]
    if own:
        fn = own[0]
        report.check(False, "the driver doesn't redefine Zephyr's sensor API", path=fn.path, line=fn.line,
                     fix=f"Rename `{fn.name}` in `{fn.path}`: `sensor_sample_fetch()` and `sensor_channel_get()` are "
                         "Zephyr's API calls. The driver's own functions go in its sensor API struct as "
                         "`.sample_fetch` and `.channel_get`.")
    if not drv:
        report.check(False, "a sensor driver with `.sample_fetch` and `.channel_get`",
                     fix="Add a sensor driver (e.g. `drivers/sensor/<name>/<name>.c`) that defines a sensor API "
                         "struct (`DEVICE_API(sensor, ...)`) with `.sample_fetch` and `.channel_get`.")
        return None
    fetch, get = drv.members.get("sample_fetch"), drv.members.get("channel_get")
    missing = [k for k, v in (("sample_fetch", fetch), ("channel_get", get)) if not v]
    if missing and not strict:  # this task is about the extension API or the shell; l6-task1 judged the rest
        report.note(f"The driver in `{drv.src.rel}` has no `.{missing[0]}` in a sensor API struct; "
                    "l6-task1 asks for both `.sample_fetch` and `.channel_get`.")
        return drv
    if not report.check(not missing, "the sensor API struct sets `.sample_fetch` and `.channel_get`",
                        path=drv.src.rel,
                        fix=f"Add `.{missing[0] if missing else ''}` to the sensor API struct in `{drv.src.rel}`, "
                            "pointing at the driver's own function."):
        return drv
    for member, name in (("sample_fetch", fetch), ("channel_get", get)):
        if not drv.func(name):
            report.check(False, f"`.{member}` points at a function of the driver", path=drv.src.rel,
                         fix=f"Define `{name}` (the `.{member}` function) in the driver.")
    if task != "l6-task1":
        return drv

    # l6-task1 only: what the functions do, and the devicetree side.
    defines = file_defines(drv.files + [drv.src])
    for member, name, want, verb in (("sample_fetch", fetch, "on", "on"), ("channel_get", get, "off", "off")):
        fn = drv.func(name)
        if not fn:
            continue
        state = led_state(led_actions(repo, fn, defines))
        label = f"`.{member}` turns the LED {verb}"
        if state == want:
            report.check(True, label)
        elif state == "toggle":
            report.check(False, label, path=fn.path, line=fn.line,
                         fix=f"Turn the LED {verb} in `{name}` (the `.{member}` function) instead of toggling it.")
        elif state in ("on", "off"):
            report.check(False, label, path=fn.path, line=fn.line,
                         fix=f"Turn the LED {verb} (not {state}) in `{name}` (the `.{member}` function).")
        elif state == "none" and not re.search(r"\w+\s*\(", fn.body):
            report.check(False, label, path=fn.path, line=fn.line,
                         fix=f"Turn the LED {verb} in `{name}` (the `.{member}` function), e.g. with "
                             f"`gpio_pin_set_dt(&config->led, {1 if want == 'on' else 0})`.")
        else:
            report.unsure(label, f"Couldn't tell from the code whether `{name}` turns the LED {verb}.",
                          path=fn.path, line=fn.line)

    code = "\n".join(s.code for s in drv.files + [drv.src])
    report.check(DT_GPIO.search(code), "the LED's GPIO comes from devicetree", path=drv.src.rel,
                        fix=f"Read the LED's GPIO from devicetree in `{drv.src.rel}`, e.g. "
                            "`GPIO_DT_SPEC_INST_GET(inst, led_gpios)`, instead of a fixed port and pin.")
    inst = DT_INSTANCE.search(drv.src.code)
    if re.search(r"\bDEVICE_DEFINE\s*\(", drv.src.code) and not inst:
        report.check(False, "the driver is instantiated from devicetree", path=drv.src.rel,
                     fix="Instantiate the driver from devicetree with `DT_INST_FOREACH_STATUS_OKAY` and "
                         "`DEVICE_DT_INST_DEFINE` instead of `DEVICE_DEFINE`.")
    else:
        report.check(inst, "the driver is instantiated from devicetree", path=drv.src.rel,
                     fix=f"Instantiate the driver in `{drv.src.rel}` with `DEVICE_DT_INST_DEFINE` for each enabled "
                         "instance (`DT_INST_FOREACH_STATUS_OKAY`).")
    if inst and inst.group(1).endswith("INST_DEFINE"):
        report.check(drv.compat, "`DT_DRV_COMPAT` names the binding", path=drv.src.rel,
                     fix=f"Add `#define DT_DRV_COMPAT <vendor>_<name>` to `{drv.src.rel}`, matching the binding's "
                         "`compatible`.")
    check_binding(report, repo, app, drv)
    return drv


def norm_compat(c):
    return re.sub(r"[^a-z0-9]", "_", c.lower())


def check_binding(report, repo, app, drv):
    bindings = {}
    for f in repo.files:
        if f.endswith((".yaml", ".yml")) and "bindings" in f.split(os.sep):
            m = re.search(r'^compatible\s*:\s*["\']?([^"\'\s#]+)', read(os.path.join(repo.root, f)), re.M)
            if m:
                bindings[norm_compat(m.group(1))] = (f, m.group(1))
    want = drv.compat
    if not want:
        return
    if not report.check(want in bindings, "a devicetree binding with the driver's `compatible`",
                        path=drv.src.rel,
                        fix=(f"Add a binding `dts/bindings/sensor/<vendor>,<name>.yaml` with `compatible: "
                             f"\"{want.replace('_', ',', 1)}\"` and the LED's `gpios` property: `DT_DRV_COMPAT "
                             f"{want}` matches none of your bindings." if bindings else
                             f"Add a devicetree binding (e.g. `dts/bindings/sensor/<vendor>,<name>.yaml`) with "
                             f"`compatible: \"{want.replace('_', ',', 1)}\"` and the LED's `gpios` property.")):
        return
    real = bindings[want][1]
    overlays = [f for f in repo.files if f.endswith((".overlay", ".dts", ".dtsi"))]  # app, board overlays, L5 boards
    node = None
    for f in overlays:
        raw = re.sub(r"//[^\n]*|/\*.*?\*/", "", read(os.path.join(repo.root, f)), flags=re.S)
        if re.search(r'compatible\s*=\s*[^;]*"%s"' % re.escape(real), raw):
            node = f
            break
    report.check(node, "an overlay adds a node with the driver's `compatible`", path=f"{app}/app.overlay",
                 fix=f"Add a node with `compatible = \"{real}\";` and the LED's GPIO to `{app}/app.overlay` "
                     "(or your board's overlay), so the driver gets an instance.")


def check_app_uses_sensor(report, repo, app, drv):
    srcs = [s for s in repo.under(app) if drv is None or s.rel not in {f.rel for f in drv.files + [drv.src]}]
    main = next((s for s in srcs if re.match(r"main\.c(pp|c)?$", os.path.basename(s.rel))), srcs[0] if srcs else None)
    where = main.rel if main else f"{app}/src/main.c"
    code = "\n".join(s.code for s in srcs)
    report.check(DEVICE_FROM_DT.search(code), "the app gets the sensor device from devicetree", path=where,
                 fix=f"Get the sensor in `{where}` from devicetree, e.g. "
                     "`DEVICE_DT_GET_ONE(<vendor>_<name>)` or `DEVICE_DT_GET(DT_NODELABEL(<label>))`.")
    for api in ("sensor_sample_fetch", "sensor_channel_get"):
        report.check(re.search(r"\b%s(?:_chan)?\s*\(" % api, code), f"the app calls `{api}()`", path=where,
                     fix=f"Call `{api}()` on the sensor device in `{where}`.")


# ---------------------------------------------------------------- extension API (l6-task2, l7-task2)
SENSOR_MEMBERS = {"sample_fetch", "channel_get", "attr_set", "attr_get", "trigger_set", "get_decoder", "submit"}


def app_sources(repo, app, drv):
    """The app's own C/C++ sources: the app folder minus the driver's files and course modules."""
    skip = {f.rel for f in drv.files + [drv.src]} if drv else set()
    return [s for s in repo.under(app) if s.rel.endswith((".c", ".cpp", ".cc")) and s.rel not in skip
            and not s.rel.startswith(f"{app}/modules/") and "/drivers/" not in f"/{s.rel}"]


def all_members(repo, app_srcs):
    """{member: function} from every `.member = fn` initializer outside the app's own sources."""
    out = {}
    own = {s.rel for s in app_srcs}
    for s in repo.srcs.values():
        if s.rel in own:
            continue
        for m in re.finditer(r"\.\s*(\w+)\s*=\s*\(?\s*&?\s*(\w+)", s.code):
            if m.group(2) in repo.funcs:
                out.setdefault(m.group(1), m.group(2))
    return out


def extension_api(repo, drv, app_srcs):
    """{public name: implementing Func or None}: what the driver offers besides the sensor API.
    Plain functions, `__syscall`s (`z_impl_`), header wrappers that call `api->member(dev, ...)`,
    and members the app calls through the API pointer (`api->member(dev, ...)`)."""
    if not drv:
        return {}
    own = {s.rel for s in app_srcs}
    members = all_members(repo, app_srcs)
    sensor_impls = {members.get(m) for m in SENSOR_MEMBERS} | set(drv.members.values())
    inits = set()
    for s in repo.srcs.values():
        for macro in ("DEVICE_DT_INST_DEFINE", "SENSOR_DEVICE_DT_INST_DEFINE", "DEVICE_DT_DEFINE",
                      "SENSOR_DEVICE_DT_DEFINE", "DEVICE_DEFINE"):
            for args, _ in calls(s.code, macro):
                a = split_args(args)
                if len(a) > 2:
                    inits.add(a[1 if "INST" in macro or "DT_DEFINE" in macro else 2].lstrip("&"))
    out = {}
    for h in repo.srcs.values():
        if not h.rel.endswith((".h", ".hpp")):
            continue
        for m in re.finditer(r"\b__syscall\b[^;(]*?\b(\w+)\s*\(", h.code):
            impl = repo.funcs.get(f"z_impl_{m.group(1)}")
            d = re.search(r"->\s*(\w+)\s*\(", impl.body) if impl else None
            if d and d.group(1) in members and d.group(1) not in SENSOR_MEMBERS:  # z_impl_ calls api->member()
                impl = repo.funcs.get(members[d.group(1)])
            out[m.group(1)] = impl
        for fn in h.funcs.values():  # static inline wrappers
            if not fn.takes_device() or fn.name.startswith(("z_impl_", "z_vrfy_")) or fn.name in out:
                continue
            m = re.search(r"->\s*(\w+)\s*\(", fn.body)
            if m and m.group(1) not in SENSOR_MEMBERS:
                out[fn.name] = repo.funcs.get(members.get(m.group(1), ""))
            elif re.search(r"->\s*data\b", fn.body):
                out[fn.name] = fn
            elif re.search(r"\bsensor_attr_set\s*\(", fn.body):  # private attributes (SENSOR_ATTR_PRIV_START)
                out[fn.name] = repo.funcs.get(members.get("attr_set") or drv.members.get("attr_set", ""))
    for s in repo.srcs.values():
        if s.rel in own or s.rel.endswith((".h", ".hpp")):
            continue
        for fn in s.funcs.values():
            if fn.static or not fn.takes_device() or fn.name in sensor_impls | inits:
                continue
            if fn.name.startswith("z_vrfy_"):
                continue
            name = fn.name[len("z_impl_"):] if fn.name.startswith("z_impl_") else fn.name
            out.setdefault(name, fn)
    for s in app_srcs:  # the app calls the API struct directly: ext_api->set_period(dev, 500), api.set(dev, 1)
        for m in re.finditer(r"(?:->|\.)\s*(\w+)\s*\(", s.code):
            if m.group(1) in members and m.group(1) not in SENSOR_MEMBERS:
                out.setdefault(m.group(1), repo.funcs.get(members[m.group(1)]))
    return out


COPY_CALLS = r"\b(?:strn?cpy|strlcpy|memcpy|memmove|memset|snprintf|sprintf|strn?cat)\s*\(\s*&?\s*\(?\s*\w+\s*->"
LOG_CALLS = {"LOG_INF", "LOG_DBG", "LOG_WRN", "LOG_ERR", "printk", "printf", "ARG_UNUSED", "__ASSERT"}


def writes_data(fn, repo=None, members=None, depth=0):
    """What the function changes: 'data' (through the device), 'global:<name>', 'nothing', or None
    (can't tell). Follows repo helpers and `api->member(dev, ...)` calls two levels down."""
    if fn is None:
        return None
    body = fn.body
    params = fn.param_names()
    if re.search(r"->\s*data\s*\)*\s*(?:[-+*/%&|^]|<<|>>)?=(?!=)", body):  # *((uint32_t *)dev->data) = v
        return "data"
    member_write = re.search(r"\w\s*->\s*\w+(?:\s*(?:\.|->)\s*\w+|\s*\[[^\]]*\])*\s*(?:[-+*/%&|^]|<<|>>)?=(?!=)|"
                             r"(?:\+\+|--)\s*\w+\s*->|\w+\s*->\s*\w+\s*(?:\+\+|--)", body) or re.search(COPY_CALLS, body)
    if member_write and re.search(r"->\s*data\b|\bDEV_DATA\s*\(|\bdevice_get_data\s*\(|\bdev_data\b", body):
        return "data"
    # A file-scope variable, directly or through a field: `count = v`, `led_data.value.val1 = v`
    for m in re.finditer(r"(?<![\w.>])(\w+)(?:\s*(?:\.\s*\w+|\[[^\]]*\]))*\s*(?:[-+*/%&|^]|<<|>>)?=(?!=)", body):
        name = m.group(1)
        declared_here = re.search(r"\b[\w\s\*]+[\s*]%s\s*(?:=|;|\[)" % re.escape(name), body)
        if not declared_here and name not in params and name not in KEYWORDS and \
                re.search(r"^\s*(?:static\s+)?(?:volatile\s+)?[\w\s\*]+\b%s\s*(?:=|;|\[)" % re.escape(name),
                          fn.src.code, re.M):
            return f"global:{name}"
    if repo is not None and depth < 2:
        for m in re.finditer(r"(?:(->|\.)\s*)?\b(\w+)\s*\(", body):
            name = m.group(2)
            callee = repo.funcs.get((members or {}).get(name, "")) if m.group(1) else repo.funcs.get(name)
            if callee is None or callee is fn:
                continue
            got = writes_data(callee, repo, members, depth + 1)
            if got and got != "nothing":
                return got
    if member_write:
        return None  # writes something through a pointer the script can't trace
    calls_left = [n for n in re.findall(r"\b(\w+)\s*\(", body) if n not in KEYWORDS and n not in LOG_CALLS]
    if not re.search(r"(?<![=!<>])=(?!=)|\+\+|--", body) and not calls_left:
        return "nothing"
    if not re.search(r"(?<![=!<>])=(?!=)|\+\+|--", body.split("{", 1)[-1].replace("->data", "")) and \
            all(n in ("gpio_pin_set_dt", "gpio_pin_get_dt") for n in calls_left):
        return "nothing"
    # Only locals declared from the device and reads: `struct x *d = dev->data; return d->n;`
    assigns = re.findall(r"(?<![=!<>])=(?!=)", body)
    decls = re.findall(r"\b(?:const\s+)?(?:struct\s+)?\w+\s*\*?\s*\w+\s*=(?!=)", body)
    if len(assigns) == len(decls) and not re.search(r"\+\+|--", body) and not calls_left:
        return "nothing"
    return None


def declared_in_header(repo, name, member=False):
    """The header declaring `name(...)`; for a struct member, any header that names it."""
    rx = r"\b%s\b" % re.escape(name) if member else r"\b%s\s*\(" % re.escape(name)
    for s in repo.srcs.values():
        if s.rel.endswith((".h", ".hpp")) and re.search(rx, s.code):
            return s
    return None


def check_extension(report, repo, app, drv):
    srcs = app_sources(repo, app, drv)
    ext = extension_api(repo, drv, srcs)
    mains = [s for s in srcs if re.match(r"main\.c(pp|c)?$", os.path.basename(s.rel))] or srcs
    main = mains[0].rel if mains else f"{app}/src/main.c"
    called = [(name, s) for s in srcs for name in ext
              if re.search(r"(?<![\w.])(?:->\s*)?%s\s*\(" % re.escape(name), s.code) and name not in s.funcs]
    called_driver = [(m.group(1), s) for s in srcs for m in re.finditer(r"(?<![\w.>])(\w+)\s*\(", s.code)
                     if m.group(1) in repo.funcs and repo.funcs[m.group(1)].src.rel not in {x.rel for x in srcs}
                     and m.group(1) not in s.funcs and m.group(1) not in ext]
    if drv and not any(n for n, _ in called_driver if n in ext) and called_driver and not [
            1 for name in ext for x in srcs if re.search(r"(?<![\w.])(?:->\s*)?%s\s*\(" % re.escape(name), x.code)]:
        name, caller = called_driver[0]
        fn = repo.funcs[name]
        report.check(False, "the extension API takes the device and changes its data", path=fn.path, line=fn.line,
                     fix=f"Make `{name}` take the device (`const struct device *dev`) and change a field of the "
                         f"driver's data struct through it (`dev->data`); `{caller.rel}` calls it without the device.")
        return None
    if not ext:
        report.check(False, "the driver has an extension API function", path=drv.src.rel if drv else None,
                     fix="Add an extension API function to your driver that takes the device "
                         "(`const struct device *dev`) and changes a field of its data struct, declare it in a "
                         f"header, and call it from `{main}`.")
        return None
    if not report.check(called, "the app calls the extension API", path=main,
                        fix=f"Call your driver's custom extension API function "
                            f"(`{next(iter(ext))}`) from `{main}`."):
        return None
    impls = {n: ext[n] for n, _ in called}
    members = all_members(repo, srcs)
    name, caller = next(((n, c) for n, c in called if impls[n] and writes_data(impls[n], repo, members) == "data"),
                        called[0])
    member_call = re.search(r"->\s*%s\s*\(" % re.escape(name), caller.code)
    proto = re.search(r"^[ \t]*(?:extern\s+)?(?:static\s+)?[\w\s\*]*\b(?:void|int|bool|char|\w+_t|struct\s+\w+)"
                      r"[\s\*]+%s\s*\([^;{}]*\)\s*;" % re.escape(name), caller.code, re.M)
    header = declared_in_header(repo, name, member=bool(member_call))
    if member_call and not header:
        report.check(False, "the extension API is declared in a header", path=caller.rel,
                     line=line_of(caller.code, member_call.start()),
                     fix=f"Declare the API struct with `{name}` in a header next to your driver and include it from "
                         f"`{caller.rel}` instead of declaring it there.")
    elif proto:
        report.check(False, "the extension API is declared in a header", path=caller.rel,
                     line=line_of(caller.code, proto.start()),
                     fix=f"Declare `{name}` in a header next to your driver and include that header from "
                         f"`{caller.rel}` instead of declaring it locally.")
    else:
        report.check(header, "the extension API is declared in a header", path=drv.src.rel,
                     fix=f"Declare `{name}` in a header (e.g. `include/drivers/sensor/<name>.h`) and include it from "
                         f"`{caller.rel}`.")
    impl = ext[name]
    if impl is None:
        report.unsure("the extension API changes the driver's data", f"Couldn't find the code behind `{name}`.")
        return caller.rel
    what = writes_data(impl, repo, members)
    if what == "data":
        report.check(True, "the extension API changes a field of the driver's data (`dev->data`)")
    elif what and what.startswith("global:"):
        report.check(False, "the extension API changes a field of the driver's data (`dev->data`)",
                     path=impl.path, line=impl.line,
                     fix=f"Store the value in the driver's data struct (`dev->data`) in `{impl.name}` instead of "
                         f"the variable `{what[7:]}`, so each device instance has its own.")
    elif what == "nothing":
        report.check(False, "the extension API changes a field of the driver's data (`dev->data`)",
                     path=impl.path, line=impl.line,
                     fix=f"Make `{impl.name}` change a field of the driver's data struct (`dev->data`); it doesn't "
                         "change anything now.")
    else:
        report.unsure("the extension API changes a field of the driver's data (`dev->data`)",
                      f"Couldn't tell what `{impl.name}` changes.", path=impl.path, line=impl.line)
    return caller.rel


# ---------------------------------------------------------------- shell (l7)
class Cmd:
    def __init__(self, name, macro, subset, handler, mand, src, pos):
        self.name, self.macro, self.subset, self.handler = name, macro, subset, handler
        self.mand, self.src, self.pos = mand, src, pos

    @property
    def line(self):
        return line_of(self.src.code, self.pos)


def shell_tree(repo):
    """-> (roots: [Cmd], sets: {set name: [Cmd]})"""
    roots, sets = [], {}

    def entry(macro, a, src, pos):
        # SHELL_CMD(name, subcmd, help, handler) / SHELL_CMD_ARG(name, subcmd, help, handler, mand, opt)
        if len(a) < 4:
            return None
        mand = a[4] if macro.endswith("ARG") and len(a) > 4 else None
        sub = a[1].lstrip("&").strip()
        return Cmd(a[0].strip(), macro, None if sub in ("NULL", "") else sub, a[3].lstrip("&").strip(), mand, src, pos)

    for s in repo.srcs.values():
        for macro in ("SHELL_STATIC_SUBCMD_SET_CREATE", "SHELL_SUBCMD_SET_CREATE"):
            for args, pos in calls(s.code, macro):
                a = split_args(args)
                if not a:
                    continue
                items = sets.setdefault(a[0], [])
                for item in a[1:]:
                    # `[0] = SHELL_CMD_ARG(...)` (a designated initializer) counts too
                    m = re.match(r"(?:\[\s*\w+\s*\]\s*=\s*)?(SHELL_CMD_ARG|SHELL_CMD|SHELL_COND_CMD_ARG|SHELL_COND_CMD|"
                                 r"SHELL_EXPR_CMD_ARG|SHELL_EXPR_CMD)\s*\((.*)\)\s*$", item, re.S)
                    if m:
                        b = split_args(m.group(2))
                        if "COND" in m.group(1) or "EXPR" in m.group(1):
                            b = b[1:]
                        c = entry("SHELL_CMD_ARG" if m.group(1).endswith("ARG") else "SHELL_CMD", b, s,
                                  pos + s.code[pos:].find(item[:20]))
                        if c:
                            items.append(c)
        for args, pos in calls(s.code, "SHELL_SUBCMD_ADD"):
            a = split_args(args)  # ((parent), syntax, subcmd, help, handler, mand, opt)
            if len(a) >= 7:
                parent = a[0].strip("() ").split(",")[-1].strip()
                sets.setdefault(parent, []).append(Cmd(a[1], "SHELL_CMD_ARG", a[2] if a[2] != "NULL" else None,
                                                       a[4].lstrip("&"), a[5], s, pos))
        for macro in ("SHELL_CMD_REGISTER", "SHELL_CMD_ARG_REGISTER", "SHELL_COND_CMD_REGISTER",
                      "SHELL_COND_CMD_ARG_REGISTER"):
            for args, pos in calls(s.code, macro):
                a = split_args(args)
                if "COND" in macro:
                    a = a[1:]
                c = entry("SHELL_CMD_ARG" if "ARG" in macro else "SHELL_CMD", a, s, pos)
                if c:
                    roots.append(c)
    return roots, sets


def subcommands(cmd, sets, seen=None):
    """All commands under cmd (depth first)."""
    seen = seen or set()
    if not cmd.subset or cmd.subset in seen:
        return []
    seen.add(cmd.subset)
    out = []
    for c in sets.get(cmd.subset, []):
        out.append(c)
        out += subcommands(c, sets, seen)
    return out


def find_command_group(roots, sets, names=("fetch", "read", "info")):
    """(root, {name: Cmd}) for the command whose direct subcommands include most of `names`."""
    best = (0, None, {})
    for r in roots:
        for parent in [r] + subcommands(r, sets):
            kids = {c.name.lower(): c for c in sets.get(parent.subset, [])} if parent.subset else {}
            n = sum(1 for k in names if k in kids)
            if n > best[0]:
                best = (n, r, kids)
    return best[1], best[2]


def reach(repo, fn, depth=0, seen=None):
    """fn plus the repo functions it calls, up to two levels down."""
    seen = seen if seen is not None else set()
    if fn is None or fn.name in seen or depth > 2:
        return []
    seen.add(fn.name)
    out = [fn]
    for m in re.finditer(r"\b(\w+)\s*\(", fn.body):
        callee = repo.funcs.get(m.group(1))
        if callee:
            out += reach(repo, callee, depth + 1, seen)
    return out


def calls_any(fns, names):
    return any(re.search(r"(?<![\w.>])(?:%s)\s*\(" % "|".join(map(re.escape, names)), f.body) for f in fns)


def print_args(fn):
    """Argument texts of every print call in fn."""
    out = []
    for p in PRINTS:
        for args, pos in calls(fn.src.code, p, fn.start, fn.end):
            out.append((args, pos))
    out += [(m.group(0), fn.start + m.start()) for m in re.finditer(r"<<[^;]*", fn.body)]  # C++ streams
    return out


def derived(body, seeds):
    names = {n for n in seeds if n}
    if not names:
        return set()  # an empty alternation would match everywhere
    while True:
        alt = r"\b(?:%s)\b" % "|".join(re.escape(n) for n in names)
        new = {m.group(1) for m in re.finditer(r"\b(\w+)\s*(?:\[[^\]]*\])?\s*=(?!=)[^;]*" + alt, body)}
        new |= {m.group(1) for m in re.finditer(alt + r"[^;]*?&\s*(\w+)", body)}  # sscanf(argv[1], "%d", &v)
        # Set in a branch chosen by the value: `if (strcmp(argv[1], "1") == 0) { on = true; }`
        for m in re.finditer(r"\bif\s*\(", body):
            cond_end = block_end(body, m.end(), "(", ")")
            if not re.search(alt, body[m.end():cond_end]):
                continue
            rest = body[cond_end:].lstrip()
            stmt = rest[1:block_end(rest, 1) - 1] if rest.startswith("{") else rest.split(";", 1)[0]
            new |= {a.group(1) for a in re.finditer(r"(?<![\w.>])(\w+)\s*=(?!=)", stmt)}
        new -= KEYWORDS
        if new <= names:
            return names
        names |= new


def check_read(report, repo, cmd):
    label = "`read` prints what `sensor_channel_get()` returns"
    fns = reach(repo, repo.funcs.get(cmd.handler))
    if not fns:
        report.unsure(label, f"Couldn't find the `read` handler `{cmd.handler}`.", path=cmd.src.rel, line=cmd.line)
        return
    owner = next((f for f in fns if re.search(r"\bsensor_channel_get\s*\(", f.body)), None)
    if not owner:
        report.check(False, "`read` calls `sensor_channel_get()`", path=fns[0].path, line=fns[0].line,
                     fix=f"Call `sensor_channel_get()` in the `read` handler (`{cmd.handler}`).")
        return
    report.check(True, "`read` calls `sensor_channel_get()`")
    body = owner.body
    seeds = set()
    for args, pos in calls(owner.src.code, "sensor_channel_get", owner.start, owner.end):
        a = split_args(args)
        if len(a) >= 3:
            seeds |= set(re.findall(r"\w+", a[2])) - {"struct", "sensor_value"}
        before = owner.src.code[owner.start:pos]
        m = re.search(r"(\w+)\s*=\s*$", before)
        if m:
            seeds.add(m.group(1))
        # The call is the condition: `if (sensor_channel_get(...))`. (`return sensor_channel_get(...)`
        # doesn't count: the shell doesn't print a handler's return code.)
        if re.search(r"\b(if|while)\s*\(?[^;{}]*$", before[-80:]) or re.search(r"[!?]\s*$", before):
            seeds.add("__direct__")
    names = derived(body, seeds - {"__direct__"}) if seeds - {"__direct__"} else set()
    prints = [p for f in fns for p in print_args(f)]
    if not prints:
        report.check(False, label, path=owner.path, line=owner.line,
                     fix=f"Print the result of `sensor_channel_get()` in `{owner.name}` (the `sensor_value` fields "
                         "or the return code).")
        return
    alt = re.compile(r"\b(?:%s)\b|\bval[12]\b|sensor_value_to_\w+" % "|".join(map(re.escape, names))) if names \
        else re.compile(r"\bval[12]\b|sensor_value_to_\w+")
    uses = any(alt.search(a) for a, _ in prints)
    # A message chosen by the return code: `if (ret < 0) shell_error(...)` or `if (sensor_channel_get(...))`.
    cond = "__direct__" in seeds or (names and re.search(
        r"\b(?:if|switch)\s*\([^{;]*\b(?:%s)\b|\?\s*" % "|".join(map(re.escape, names)), body))
    report.check(uses or cond, label, path=owner.path, line=owner.line,
                 fix=f"Print the result of `sensor_channel_get()` in `{owner.name}` (the `sensor_value` fields or "
                     "the return code) instead of a fixed message.")


def check_info(report, repo, cmd):
    fns = reach(repo, repo.funcs.get(cmd.handler))
    if not fns:
        report.unsure("`info` prints the device name and ready state",
                      f"Couldn't find the `info` handler `{cmd.handler}`.", path=cmd.src.rel, line=cmd.line)
        return
    h = fns[0]
    body = "\n".join(f.body for f in fns)
    name_src = re.compile(r"->\s*name\b|\bDEVICE_DT_NAME\b|\bDT_NODE_FULL_NAME\b|\bDT_PROP\s*\([^)]*label|"
                          r"\bdevice_get_name\b|\bdev_name\b")
    names = derived(body, set(re.findall(r"\b(\w+)\s*=\s*[^;]*->\s*name\b", body))) | {"__never__"}
    prints = [a for f in fns for a, _ in print_args(f)]
    alt = re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, names)))
    report.check(any(name_src.search(a) or alt.search(a) for a in prints), "`info` prints the device's real name",
                 path=h.path, line=h.line,
                 fix=f"Print the device's real name (`dev->name`) in the `info` handler (`{cmd.handler}`).")
    ready = re.search(r"\bdevice_is_ready\s*\(", body)
    state = re.search(r"->\s*state\s*->\s*(?:initialized|init_res)\b", body)
    report.check(ready or state, "`info` prints the ready state from `device_is_ready()`", path=h.path, line=h.line,
                 fix=f"Print whether the device is ready, from `device_is_ready(dev)`, in the `info` handler "
                     f"(`{cmd.handler}`).")
    if state and not ready:
        report.note(f"`{cmd.handler}` reads `dev->state` directly; `device_is_ready(dev)` is the API for the ready "
                    "state.")


def check_shell_enabled(report, repo, app, build_dir):
    cfg = os.path.join(build_dir, "zephyr", ".config") if build_dir else None
    if cfg and os.path.isfile(cfg):
        on = re.search(r"^CONFIG_SHELL=y", read(cfg), re.M)
    else:
        on = any(re.search(r"^\s*CONFIG_SHELL\s*=\s*y", read(os.path.join(repo.root, f)), re.M)
                 for f in repo.files if f.endswith(".conf") or f.endswith("_defconfig")) or \
            any(re.search(r"^\s*select\s+SHELL\s*$", read(os.path.join(repo.root, f)), re.M)
                for f in repo.files if os.path.basename(f).startswith("Kconfig"))  # the build's .config decides in CI
    report.check(on, "the shell is enabled (`CONFIG_SHELL=y`)", path=f"{app}/prj.conf",
                 fix=f"Enable the shell: add `CONFIG_SHELL=y` to `{app}/prj.conf`.")


def check_shell(report, repo, app, task, drv, build_dir):
    roots, sets = shell_tree(repo)
    check_shell_enabled(report, repo, app, build_dir)
    root, kids = find_command_group(roots, sets)
    if task == "l7-task1":
        flat = [r for r in roots if r.name.lower() in ("fetch", "read", "info")]
        if not root and flat:
            report.check(False, "one root command with `fetch`, `read` and `info` subcommands",
                         path=flat[0].src.rel, line=flat[0].line,
                         fix="Register a single root `sensor` command with `SHELL_CMD_REGISTER` and make `fetch`, "
                             "`read`, `info` its subcommands (`SHELL_STATIC_SUBCMD_SET_CREATE`) instead of separate "
                             "root commands.")
            return None
        if not report.check(root, "a root shell command with subcommands",
                            fix="Register a root `sensor` shell command with `SHELL_CMD_REGISTER` and `fetch`, "
                                "`read` and `info` subcommands (`SHELL_STATIC_SUBCMD_SET_CREATE`)."):
            return None
        if root.name == "sensor":
            report.note("The root command is `sensor`, the same name as Zephyr's own sensor shell; that one is "
                        "only built with `CONFIG_SENSOR_SHELL=y`.")
        for name in ("fetch", "read", "info"):
            report.check(name in kids, f"a `{name}` subcommand", path=root.src.rel, line=root.line,
                         fix=f"Add a `{name}` subcommand to the `{root.name}` shell command.")
        if "fetch" in kids:
            c = kids["fetch"]
            fns = reach(repo, repo.funcs.get(c.handler))
            if fns:
                report.check(calls_any(fns, ["sensor_sample_fetch", "sensor_sample_fetch_chan"]),
                             "`fetch` calls `sensor_sample_fetch()`", path=fns[0].path, line=fns[0].line,
                             fix=f"Call `sensor_sample_fetch()` in the `fetch` handler (`{c.handler}`).")
            else:
                report.unsure("`fetch` calls `sensor_sample_fetch()`",
                              f"Couldn't find the `fetch` handler `{c.handler}`.", path=c.src.rel, line=c.line)
        if "read" in kids:
            check_read(report, repo, kids["read"])
        if "info" in kids:
            check_info(report, repo, kids["info"])
        return root
    check_set(report, repo, app, drv, roots, sets, root)
    return root


def check_set(report, repo, app, drv, roots, sets, root):
    ext = extension_api(repo, drv, app_sources(repo, app, drv))
    every = [c for r in roots for c in [r] + subcommands(r, sets)]
    cmd = next((c for c in every if c.name.lower() == "set"), None)
    if cmd is None and ext:
        cmd = next((c for c in every if calls_any(reach(repo, repo.funcs.get(c.handler)), list(ext))), None)
    if not report.check(cmd, "a `set` subcommand",
                        path=root.src.rel if root else None, line=root.line if root else None,
                        fix="Add a `set <value>` subcommand with `SHELL_CMD_ARG` that passes the value to your "
                            "driver's extension API."):
        return
    report.check(cmd.macro == "SHELL_CMD_ARG", "`set` is registered with `SHELL_CMD_ARG`",
                 path=cmd.src.rel, line=cmd.line,
                 fix="Register the `set` subcommand with `SHELL_CMD_ARG` (e.g. mandatory count 2) instead of "
                     "`SHELL_CMD`.")
    fns = reach(repo, repo.funcs.get(cmd.handler))
    if not fns:
        report.unsure("`set` validates its argument", f"Couldn't find the `set` handler `{cmd.handler}`.",
                      path=cmd.src.rel, line=cmd.line)
        return
    h = fns[0]
    body = "\n".join(f.body for f in fns)
    has_error = re.search(r"\bshell_error\s*\(", body)

    # A missing value: the shell rejects it (mandatory count includes it) or the handler checks argc.
    mand = int(cmd.mand) if cmd.mand and cmd.mand.strip().isdigit() else None
    argc_check = re.search(r"\bargc\s*(?:<|<=|!=|==)\s*\d|\d\s*(?:>|>=|!=|==)\s*argc\b", body)
    if mand is not None and mand >= 2:
        report.check(True, "a missing value is rejected")
    else:
        report.check(argc_check and has_error, "a missing value is rejected", path=cmd.src.rel, line=cmd.line,
                     fix=f"Reject a missing argument: set the `SHELL_CMD_ARG` mandatory count to 2, or check `argc` in "
                         f"`{cmd.handler}` and call `shell_error`.")

    # The value: whatever comes from argv.
    names = derived(body, {"argv"}) - {"argv", "argc", "sh", "shell", "dev", "ret", "err", "rc"}
    ext_calls = [(n, a, f, pos) for f in fns for n in ext
                 for a, pos in calls(f.src.code, n, f.start, f.end, member=True)]
    if not ext_calls:
        other = re.search(r"\bsensor_attr_set\s*\(", body)
        direct = re.search(r"->\s*data\b", body)
        report.check(False, "the value goes to the extension API", path=h.path, line=h.line,
                     fix=(f"Pass the value to your driver's custom extension API function in `{h.name}` instead of "
                          "calling `sensor_attr_set()`." if other else
                          f"Pass the value to your driver's extension API in `{h.name}` instead of writing the "
                          "driver's data directly from the shell handler." if direct else
                          f"Pass the parsed value to your driver's extension API function in `{h.name}`."))
    else:
        alt = re.compile(r"\b(?:%s)\b|\bargv\b" % "|".join(map(re.escape, names or {"argv"})))

        def in_value_branch(pos):
            """The call sits in an `if` branch whose condition reads the value (`if (!strcmp(argv[1], "on"))`)."""
            code = h.src.code
            for m in re.finditer(r"\bif\s*\(", code[h.start:pos]):
                start = h.start + m.end()
                cond_end = block_end(code, start, "(", ")")
                if not alt.search(code[start:cond_end - 1]):
                    continue
                rest = code[cond_end:]
                skip = len(rest) - len(rest.lstrip())
                if rest.lstrip().startswith("{"):
                    end = block_end(code, cond_end + skip + 1)
                else:
                    end = code.find(";", cond_end) + 1
                if cond_end <= pos < end:
                    return True
            return False

        def passes(n, a, f, pos):
            if f is h:
                return alt.search(a) or in_value_branch(pos)
            # In a helper: the helper passes on one of its parameters, and the handler gives it the value.
            params = [p for p in f.param_names() if p]
            return any(re.search(r"\b%s\b" % re.escape(p), a) for p in params) and any(
                alt.search(x) for x, _ in calls(h.src.code, f.name, h.start, h.end))
        ok = any(passes(*c) for c in ext_calls)
        report.check(ok, "the value goes to the extension API", path=h.path, line=h.line,
                     fix=f"Pass the parsed value to your extension API in `{h.name}`; `{ext_calls[0][0]}()` is "
                         "called without it.")

    # Out of range: both a minimum and a maximum, or a closed set of values.
    # The value may also be checked as `atoi(argv[1])` or `strlen(argv[1])` inline, or by a helper
    # (`in_range(argv[1])`): those count as the value too.
    body = "\n".join(f.body for f in fns if f.src is h.src)
    body = re.sub(r"\b(?:atoi|atol|strto\w+|shell_strto\w+|strlen)\s*\((?:[^()]|\([^()]*\))*\bargv\b(?:[^()]|\([^()]*\))*\)",
                  "__value__", body)
    # Out-parameters of the parse (`strtol(argv[1], &endptr, 10)`, `&err`) are not the value.
    names = {n for n in names if not re.search(r"end|err|ptr|^rc$|^ret$|^res$", n, re.I)} | {"__value__"}
    for f in fns[1:]:
        if f.src is not h.src:  # the shell validates: only its own helpers count, not the driver's code
            continue
        params = f.param_names()
        for args, _ in calls(h.src.code, f.name, h.start, h.end):
            for i, a in enumerate(split_args(args)):
                if i < len(params) and params[i] and re.search(r"\bargv\b|\b(?:%s)\b" % "|".join(map(re.escape, names)), a):
                    names |= derived(f.body, {params[i]})
    body = re.sub(r"\b__value__\s*==\s*0\b", "__value__ < 1", body)  # strlen(...) == 0: an empty value
    lower = upper = False
    if names:
        alt = r"(?:%s)" % "|".join(map(re.escape, names))
        for m in re.finditer(r"\b%s\b\s*(<=?|>=?)(?![<>=])" % alt, body):
            lower |= m.group(1).startswith("<")
            upper |= m.group(1).startswith(">")
        for m in re.finditer(r"(?<![<>=-])(<=?|>=?)\s*\b%s\b(?!\s*(?:\(|\[|->|\.))" % alt, body):
            upper |= m.group(1).startswith("<")
            lower |= m.group(1).startswith(">")
    # A sign check before an unsigned parse is a minimum: `if (argv[1][0] == '-')`
    signs = r"\bargv\s*\[\s*\d+\s*\]" + (r"|\b(?:%s)\b" % "|".join(map(re.escape, names)) if names else "")
    if re.search(r"(?:%s)\s*\[\s*0\s*\]\s*==\s*'-'" % signs, h.src.text[h.start:h.end]):
        lower = True
    # A closed set: string compares, shell_strtobool, `v != 0 && v != 1`, or a switch with a default.
    eq = len(re.findall(r"\b(?:%s)\s*(?:!=|==)\s*[\w'\"]+" % "|".join(map(re.escape, names)), body)) if names else 0
    # One strcmp (`invert = strcmp(argv[1], "1") == 0`) maps everything else to false: not a closed set.
    closed = eq >= 2 or len(re.findall(r"\b(?:strn?cmp|strn?casecmp)\s*\(", body)) >= 2 or \
        re.search(r"\bshell_strtobool\s*\(", body) or \
        (names and re.search(r"\bswitch\s*\(\s*(?:%s)\s*\)[^}]*\bdefault\s*:" % "|".join(map(re.escape, names)),
                             body, re.S))
    label = "an out-of-range value is rejected with `shell_error`"
    if (lower and upper) or closed:
        report.check(has_error, label, path=h.path, line=h.line,
                     fix=f"Call `shell_error` in `{h.name}` when the value is out of range.")
    elif lower or upper:
        side, other = ("minimum", "maximum") if upper else ("maximum", "minimum")
        report.check(False, label, path=h.path, line=h.line,
                     fix=f"Add a {side} check in `{h.name}` and call `shell_error` when the value is "
                         f"{'below' if side == 'minimum' else 'above'} it; only the {other} is checked now.")
    elif has_error and re.search(r"\b(?:ret|rc|err|res|result)\s*(?:<|!=)\s*0|\bif\s*\(\s*(?:ret|rc|err)\s*\)",
                                 body):
        report.unsure(label, f"`{h.name}` has no range check of its own; the driver may reject the value.",
                      path=h.path, line=h.line)
    else:
        report.check(False, label, path=h.path, line=h.line,
                     fix=f"Check the value against a minimum and a maximum in `{h.name}` and call `shell_error` "
                         "when it is out of range.")


# ---------------------------------------------------------------- build
def compiled(build_dir):
    path = os.path.join(build_dir, "compile_commands.json")
    if not os.path.isfile(path):
        return None
    try:
        return [e.get("file", "") for e in json.load(open(path))]
    except (OSError, ValueError):
        return None


def check_build(report, repo, app, build_dir, info, drv, shell_root, caller=None):
    if not board_info.check_build(report, info, build_dir, app):
        return
    board = info["board"]
    files = compiled(build_dir)
    if files is not None and drv:
        rel = drv.src.rel
        cmake = next((f for f in (os.path.join(drv.folder, "CMakeLists.txt"),) if f in repo.files), None)
        gate = None
        if cmake:
            m = re.search(r"(?:_ifdef\s*\(|if\s*\(\s*)(CONFIG_\w+)", read(os.path.join(repo.root, cmake)))
            gate = m.group(1) if m else None
        report.check(any(f.endswith("/" + rel) for f in files), "the driver is compiled into the app",
                     path=rel, fix=(f"Enable the driver: `{gate}` is off in the `{board}` build, so `{rel}` isn't "
                                    f"compiled. Set it in `{app}/prj.conf`, or make its Kconfig default to the "
                                    "devicetree node (`default y` + `depends on DT_HAS_..._ENABLED`)."
                                    if gate else
                                    f"Add `{rel}` to the build of `{app}`: from `{app}/CMakeLists.txt` "
                                    "(`target_sources` / `add_subdirectory`), or as a module through "
                                    "`zephyr/module.yml`."))
    if files is not None and shell_root:
        rel = shell_root.src.rel
        report.check(any(f.endswith("/" + rel) for f in files), "the shell commands are compiled into the app",
                     path=rel, fix=f"Add `{rel}` to the build of `{app}` (e.g. `target_sources(app PRIVATE ...)`).")
    if files is not None and caller:  # l6-task2: the file that calls the extension API is the app's
        report.check(any(f.endswith("/" + caller) for f in files), "the code calling the extension API is built",
                     path=caller, fix=f"Add `{caller}` to the build of `{app}`: it calls the extension API, but the "
                                      f"`{board}` build doesn't compile it.")
    dts = os.path.join(build_dir, "zephyr", "zephyr.dts")
    if drv and drv.compat and os.path.isfile(dts) and report.task == "l6-task1":
        code = read(dts)
        compat = re.compile(r'compatible\s*=\s*[^;]*"([^"]+)"')
        nodes = [m for m in compat.finditer(code) if norm_compat(m.group(1)) == drv.compat]
        report.check(nodes, "the built devicetree has the driver's node", path=f"{app}/app.overlay",
                     fix=f"Make sure the overlay is applied: no node in the `{board}` build's devicetree has the "
                         f"driver's `compatible` ({drv.compat}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
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
    repo = Repo(root)
    app = args.app or find_app(repo, args.task)
    if args.print_app:
        print(app)
        return 0

    report = Report(args.task, TASKS[args.task])
    if app != "app":
        report.note(f"The app is in `{app}/`; the course builds on `app/`.")
    drv = check_driver(report, repo, app, args.task)
    shell_root = caller = None
    if args.task == "l6-task1":
        check_app_uses_sensor(report, repo, app, drv)
    elif args.task == "l6-task2":
        caller = check_extension(report, repo, app, drv)
    else:
        shell_root = check_shell(report, repo, app, args.task, drv, args.build_dir)
    if args.build_dir:
        info = (board_info.load_info(args.board_info) if args.board_info
                else board_info.info_for(args.board, args.board_declared))
        check_build(report, repo, app, args.build_dir, info, drv, shell_root, caller)
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
