#!/usr/bin/env python3
"""Check l3-task1: the LED Subsystem Kconfig menu.

Required menu (tasks.md, Lecture 3):

    [*] LED Subsystem  --->
         LED blink sleep time (1s (medium))  --->
         [ ] Advanced LED settings  --->
              (100) LED brightness (0-100)
              (500) LED fade duration (ms)
              Expert settings  --->
                   [ ] Enable LED debugging
                   [ ] Custom blink pattern

Symbols are found by structure and prompt words, not by name, so any naming
passes. The hidden int is checked by behaviour: the script selects each choice
option in turn and reads the value the int takes.

Usage:
    python3 .github/scripts/check_l3_task1.py [--root REPO] [--kconfig app/Kconfig] [--json result.json]

Needs kconfiglib: `pip install kconfiglib`, or $ZEPHYR_BASE/scripts/kconfig on the path.
Exit code 0 when approved, 1 otherwise.
"""
import argparse
import os
import sys
import tempfile

from homework_report import Report

try:
    import kconfiglib as kc
except ImportError:
    zb = os.environ.get("ZEPHYR_BASE")
    if zb:
        sys.path.insert(0, os.path.join(zb, "scripts", "kconfig"))
    try:
        import kconfiglib as kc
    except ImportError:
        sys.exit("kconfiglib not found: `pip install kconfiglib`, or set ZEPHYR_BASE to a Zephyr tree.")

EXPECTED_MS = [250, 500, 1000, 2000]


# ---------------------------------------------------------------- tree helpers
def walk(node):
    """Depth-first over node and its following siblings."""
    while node:
        yield node
        if node.list:
            yield from walk(node.list)
        node = node.next


def subtree(node):
    return [node] + (list(walk(node.list)) if node.list else [])


def children(node):
    out, n = [], node.list
    while n:
        out.append(n)
        n = n.next
    return out


def prompt(node):
    return node.prompt[0].lower() if node.prompt else ""


def mentions(node, *words):
    p = prompt(node)
    return bool(p) and all(w in p for w in words)


def is_sym(node, typ=None):
    return isinstance(node.item, kc.Symbol) and (typ is None or node.item.type == typ)


def is_menuconfig(node):
    return is_sym(node) and node.is_menuconfig


def first(nodes, pred):
    return next((n for n in nodes if pred(n)), None)


def describe(node):
    if node.item is kc.MENU:
        return f'plain `menu "{node.prompt[0]}"`'
    if node.item is kc.COMMENT:
        return "`comment`"
    if isinstance(node.item, kc.Choice):
        return "`choice`"
    kind = "menuconfig" if node.is_menuconfig else "config"
    return f"`{kind} {node.item.name}`"


class Kconf:
    """Wraps the parsed tree with paths relative to the repo root."""

    def __init__(self, kconf, root):
        self.k = kconf
        self.root = root

    def loc(self, node):
        if node is None:
            return {}
        path = os.path.relpath(node.filename, self.root) if os.path.isabs(node.filename) else node.filename
        return {"path": path, "line": node.linenr}


def parse(path, root):
    """Parse with a stub Zephyr tree, so `source "Kconfig.zephyr"` (or `"Kconfig"`, or
    `"$(ZEPHYR_BASE)/Kconfig"`) resolves to an empty file instead of all of Zephyr."""
    stub = tempfile.mkdtemp(prefix="kconfig-stub-")
    for name in ("Kconfig.zephyr", "Kconfig"):
        open(os.path.join(stub, name), "w").close()
    os.environ["srctree"] = stub
    os.environ["ZEPHYR_BASE"] = stub
    os.environ.setdefault("KCONFIG_WARN_UNDEF", "n")
    return Kconf(kc.Kconfig(os.path.abspath(path), warn=False), root)


# ---------------------------------------------------------------- checks
def find_toggle(nodes, words):
    """A requirement that must be a `menuconfig` with a bool prompt. Returns (node, problem_node)."""
    node = first(nodes, lambda n: is_menuconfig(n) and mentions(n, *words))
    if node:
        return node, None
    # Something with the right prompt but the wrong kind, for a precise message.
    wrong = first(nodes, lambda n: mentions(n, *words) and not isinstance(n.item, kc.Choice))
    return None, wrong


def check(report, kconf):
    top = list(walk(kconf.k.top_node))

    # 1. LED Subsystem: top-level menuconfig ---------------------------------
    led, wrong = find_toggle(top, ("led", "subsystem"))
    if not led:  # tolerate prompt typos ("LED Subsytem"): any LED menuconfig that isn't Advanced
        led = first(top, lambda n: is_menuconfig(n) and mentions(n, "led") and not mentions(n, "advanced"))
        wrong = wrong if not led else None
    if report.check(led, "`menuconfig` for LED Subsystem",
                    fix=(f"Declare LED Subsystem with `menuconfig <SYMBOL>` and a `bool` prompt instead of {describe(wrong)}."
                         if wrong else 'Add `menuconfig LED_SUBSYSTEM` with `bool "LED Subsystem"` as the top-level toggle.'),
                    **kconf.loc(wrong)):
        report.check(led.item.type == kc.BOOL, "LED Subsystem is a `bool`",
                     fix=f"Make `{led.item.name}` a `bool` so it shows as `[*]`.", **kconf.loc(led))
    led_scope = subtree(led) if led else top

    # 2. choice for blink sleep time -----------------------------------------
    choice = first(led_scope, lambda n: isinstance(n.item, kc.Choice) and (mentions(n, "sleep") or mentions(n, "blink")))
    if not choice and led:
        outside = first(top, lambda n: isinstance(n.item, kc.Choice))
        report.check(False, "`choice` for blink sleep time under LED Subsystem",
                     fix=("Move the blink time `choice` inside LED Subsystem (`if " + led.item.name + "` ... `endif`)."
                          if outside else 'Add a `choice` with prompt "LED blink sleep time" under LED Subsystem.'),
                     **kconf.loc(outside))
    else:
        report.check(choice, "`choice` for blink sleep time under LED Subsystem",
                     fix='Add a `choice` with prompt "LED blink sleep time" under LED Subsystem.')

    members = []
    if choice:
        members = [n.item for n in children(choice) if is_sym(n)]
        report.check(len(members) == 4, "choice has 4 options (250 ms, 500 ms, 1 s, 2 s)",
                     fix=f"Give the blink time `choice` exactly 4 options: 250 ms, 500 ms, 1 s and 2 s (found {len(members)}).",
                     **kconf.loc(choice))

    # 3. hidden int that follows the choice ----------------------------------
    # A hidden symbol never shows in menuconfig, so it may live anywhere in the file.
    member_set = set(members)
    hidden = [n for n in top if is_sym(n, kc.INT) and all(not m.prompt for m in n.item.nodes)]
    linked = first(hidden, lambda n: any(member_set & set(kc.expr_items(cond)) for _, cond in n.item.defaults))
    if report.check(linked, "hidden `int` with `default <ms> if <option>` per choice option",
                    fix=("Add a hidden `int` (no prompt) under LED Subsystem with one `default <ms> if <OPTION>` per choice option."
                         if not hidden else
                         f"Give `{hidden[0].item.name}` one `default <ms> if <OPTION>` per blink time option, so it follows the choice."),
                    **kconf.loc(hidden[0] if hidden else choice)):
        check_hidden_values(report, kconf, led, choice, members, linked)

    # 4. Advanced LED settings menuconfig ------------------------------------
    adv, wrong = find_toggle(led_scope, ("advanced",))
    if not adv and led:
        elsewhere, _ = find_toggle(top, ("advanced",))
        if elsewhere:
            wrong = elsewhere
    report.check(adv, "`menuconfig` for Advanced LED settings under LED Subsystem",
                 fix=(f"Declare Advanced LED settings with `menuconfig <SYMBOL>` under LED Subsystem instead of {describe(wrong)}."
                      if wrong and not is_menuconfig(wrong) else
                      "Move the Advanced LED settings `menuconfig` inside LED Subsystem." if wrong else
                      'Add `menuconfig` with `bool "Advanced LED settings"` under LED Subsystem.'),
                 **kconf.loc(wrong))
    adv_scope = subtree(adv) if adv else led_scope

    # 5. brightness and fade ranges ------------------------------------------
    check_int(report, kconf, adv_scope, top, "bright", "LED brightness", 0, 100, 100, adv)
    check_int(report, kconf, adv_scope, top, "fade", "LED fade duration", 0, 5000, 500, adv)

    # 6. Expert settings: plain menu, gated ---------------------------------
    # Grading rule (prompt.md): gated by `visible if` OR an enclosing `if`. A menu
    # placed next to Advanced is accepted when Advanced really hides it.
    expert = first(adv_scope, lambda n: n.item is kc.MENU and mentions(n, "expert"))
    nested = expert is not None and adv is not None
    if not expert:
        expert = first(led_scope, lambda n: n.item is kc.MENU and mentions(n, "expert"))
    wrong = None if expert else first(top, lambda n: mentions(n, "expert"))
    if report.check(expert, '`menu "Expert settings"` under Advanced LED settings',
                    fix=(f"Declare Expert settings as a plain `menu` under Advanced LED settings instead of {describe(wrong)}."
                         if wrong and wrong.item is not kc.MENU else
                         "Move the Expert settings `menu` inside Advanced LED settings." if wrong else
                         'Add `menu "Expert settings"` under Advanced LED settings.'),
                    **kconf.loc(wrong)):
        gated = expert_gated(kconf, led, adv, expert)
        report.check(gated, "Expert settings is hidden while Advanced LED settings is off",
                     fix=(f"Add `visible if {adv.item.name}` to the Expert settings menu, or move it inside "
                          f"`if {adv.item.name}`." if adv else
                          "Add a `visible if` condition to the Expert settings menu."),
                     **kconf.loc(expert))
        if gated and not nested and adv:
            report.note("Expert settings sits next to Advanced LED settings rather than inside it; "
                        "it is hidden by `visible if`, which the task accepts.")
    expert_scope = subtree(expert)[1:] if expert else []

    # 7. the two expert bools ------------------------------------------------
    bools = [n for n in expert_scope if is_sym(n, kc.BOOL)]
    report.check(len(bools) >= 2, 'two `bool` options in Expert settings ("Enable LED debugging", "Custom blink pattern")',
                 fix='Add `bool "Enable LED debugging"` and `bool "Custom blink pattern"` inside the Expert settings menu.',
                 **kconf.loc(expert))
    for word, label in (("debug", "Enable LED debugging"), ("pattern", "Custom blink pattern")):
        if len(bools) >= 2 and not first(bools, lambda n: mentions(n, word)):
            report.note(f'No Expert option mentions "{word}"; the task names it "{label}".')

    # Extras beyond the spec (grade 5 signal for the instructor; never fails).
    if led:
        expected = 1 + len(members) + 1 + 1 + 2 + 2  # led, options, hidden, adv, 2 ints, 2 bools
        syms = {n.item for n in led_scope if is_sym(n)}
        if len(syms) > expected:
            report.note(f"{len(syms) - expected} symbol(s) beyond the required menu.")


def enable(node):
    """Set a bool to y. False when its dependencies (often Zephyr symbols we don't load) block it."""
    node.item.set_value(2)
    return node.item.tri_value == 2


def shown(node):
    return kc.expr_value(node.dep) and kc.expr_value(node.visibility)


def expert_gated(kconf, led, adv, expert):
    """Evaluate like menuconfig: Expert must be hidden while Advanced is off. (Extra conditions
    that also hide it with Advanced on are the student's choice.) Falls back to reading the
    expressions when the symbols can't be toggled here."""
    if led and adv and enable(led) and enable(adv):
        adv.item.set_value(0)
        hidden_when_off = not shown(expert)
        adv.item.set_value(2)
        return hidden_when_off
    if expert.visibility is not kconf.k.y:
        return True
    return adv is not None and adv.item in kc.expr_items(expert.dep)


def check_hidden_values(report, kconf, led, choice, members, hidden):
    """Select each option and read the hidden int. Needs LED Subsystem settable to y."""
    sym = hidden.item
    if led is not None and not enable(led):
        report.note(f"Could not enable `{led.item.name}` outside a Zephyr build (it depends on symbols "
                    "this checker doesn't load), so the hidden int's values were not evaluated.")
        return
    choice.item.set_value(2)  # an `optional` choice starts off; switch it on to select options
    default_sel = choice.item.selection
    values = []
    for m in members:
        m.set_value(2)
        try:
            values.append(int(sym.str_value, 0))
        except ValueError:
            values.append(None)
    report.check(len(set(values)) == len(members) and None not in values,
                 f"`{sym.name}` takes a different value for each option",
                 fix=f"Give `{sym.name}` a different `default` for each blink time option (values seen: {values}).",
                 **kconf.loc(hidden))
    if sorted(v for v in values if v is not None) != EXPECTED_MS:
        report.note(f"`{sym.name}` takes {values}; expected milliseconds {EXPECTED_MS}.")
    if default_sel is not None and len(members) == 4 and 1000 in values:
        if values[members.index(default_sel)] != 1000:
            report.note("The choice's default is not the 1 s option shown in the task's menu.")


def check_int(report, kconf, scope, top, word, label, lo, hi, default, adv):
    node = first(scope, lambda n: is_sym(n, kc.INT) and mentions(n, word))
    if not node:
        elsewhere = first(top, lambda n: is_sym(n, kc.INT) and mentions(n, word))
        report.check(False, f'`int` "{label}" under Advanced LED settings',
                     fix=(f"Move `{elsewhere.item.name}` inside Advanced LED settings." if elsewhere else
                          f'Add an `int "{label}"` symbol inside Advanced LED settings.'),
                     **kconf.loc(elsewhere))
        return
    sym = node.item
    ranges = [(r[0].str_value, r[1].str_value) for r in sym.ranges]
    report.check((str(lo), str(hi)) in ranges, f"`{sym.name}` has `range {lo} {hi}`",
                 fix=(f"Change the range of `{sym.name}` to `range {lo} {hi}` (found `range {ranges[0][0]} {ranges[0][1]}`)."
                      if ranges else f"Add `range {lo} {hi}` to `{sym.name}`."),
                 **kconf.loc(node))
    if sym.defaults and sym.defaults[0][0].str_value != str(default):
        report.note(f"`{sym.name}` defaults to {sym.defaults[0][0].str_value}; the task's menu shows ({default}).")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--kconfig", default="app/Kconfig", help="Kconfig path relative to --root")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()

    report = Report("l3-task1", "LED Subsystem Kconfig menu")
    root = os.path.abspath(args.root)
    path = os.path.join(root, args.kconfig)

    if not os.path.isfile(path):
        report.check(False, f"`{args.kconfig}` exists",
                     fix=f"Add the LED Subsystem menu to `{args.kconfig}` at the repository root.")
        return report.finish(args.json)

    try:
        kconf = parse(path, root)
    except kc.KconfigError as exc:
        # Keep the first sentence, with paths relative to the repo instead of the runner.
        msg = str(exc).strip().splitlines()[0].replace(root + os.sep, "")
        msg = msg.split(". Check that environment variables")[0]
        report.fail_hard(f"Fix this Kconfig error so the file parses: {msg}", path=args.kconfig)
        return report.finish(args.json)

    check(report, kconf)
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
