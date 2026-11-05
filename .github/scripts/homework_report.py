"""Shared reporting for the homework checkers.

Every checker builds a Report, records one check per requirement, and calls
finish(). finish() prints a PASS/FAIL checklist, adds GitHub annotations and a
job summary when running in Actions, and writes a result JSON that matches one
entry of the course feedback file (feedback/students/<nickname>.json):

    {"task": "l3-task1", "status": "approved" | "changes_needed" | "under_review" | "error",
     "ref": "<tag or branch>", "changes": [{"message", "path", "line"}],
     "title": "...", "checks": [{"ok", "label", "message", "path", "line"}],
     "notes": [...], "error": null | {"message", "path", "line"}}

"error" means the checker could not evaluate the submission (for example the
Kconfig does not parse); an instructor should look at it. "under_review" means every
check that could be decided passed, but some can't be decided from the code
(check `ok` is null); an instructor decides those.
"""
import json
import os

MAX_CHANGES = 5  # same cap as the feedback emails


class Report:
    def __init__(self, task, title):
        self.task = task
        self.title = title
        self.checks = []  # dicts: ok, label, message, path, line
        self.notes = []
        self.error = None

    def check(self, ok, label, fix=None, path=None, line=None):
        """Record one requirement. `fix` is the imperative message shown when it fails."""
        ok = bool(ok)
        self.checks.append({"ok": ok, "label": label, "message": fix or label,
                            "path": path, "line": line})
        return ok

    def unsure(self, label, why, path=None, line=None):
        """A requirement the checker can't decide from the code: an instructor looks. Never fails the task."""
        self.checks.append({"ok": None, "label": label, "message": why, "path": path, "line": line})

    def note(self, message):
        """Informational remark; never fails the task."""
        self.notes.append(message)

    def fail_hard(self, message, path=None, line=None):
        """The checker could not evaluate the submission at all."""
        self.error = {"message": message, "path": path, "line": line}

    @property
    def status(self):
        if self.error:
            return "error"
        if any(c["ok"] is False for c in self.checks):
            return "changes_needed"
        return "under_review" if any(c["ok"] is None for c in self.checks) else "approved"

    def changes(self):
        if self.error:
            items = [self.error]
        else:
            items = [c for c in self.checks if c["ok"] is False]
        out = []
        for c in items[:MAX_CHANGES]:
            item = {"message": c["message"]}
            if c.get("path"):
                item["path"] = c["path"]
            if c.get("line"):
                item["line"] = c["line"]
            out.append(item)
        return out

    def result(self):
        """The result JSON (one task entry of the feedback file, plus the check list)."""
        return {
            "task": self.task,
            "title": self.title,
            "status": self.status,
            # PR runs set HOMEWORK_REF to the PR's branch; GITHUB_REF_NAME would be "12/merge".
            "ref": os.environ.get("HOMEWORK_REF") or os.environ.get("GITHUB_REF_NAME"),
            "changes": self.changes(),
            "checks": [{"ok": c["ok"], "label": c["label"], "message": c["message"],
                        "path": c["path"], "line": c["line"]} for c in self.checks],
            "notes": self.notes,
            "error": self.error,
        }

    def finish(self, json_path=None):
        status = self.status
        passed = sum(c["ok"] is True for c in self.checks)

        print(f"{self.task}: {self.title}")
        print("=" * 64)
        if self.error:
            print(f"[ERROR] {self.error['message']}")
        for c in self.checks:
            print(f"[{ {True: 'PASS', False: 'FAIL', None: 'INSTRUCTOR'}[c['ok']] }] {c['label']}")
            if c["ok"] is not True and c["message"] != c["label"]:
                print(f"       -> {c['message']}")
        for n in self.notes:
            print(f"[NOTE] {n}")
        print("=" * 64)
        print(f"{passed}/{len(self.checks)} checks passed; status: {status}")

        if os.environ.get("GITHUB_ACTIONS") == "true":
            self._annotate()
            self._summary(status, passed)

        if json_path:
            with open(json_path, "w") as f:
                json.dump(self.result(), f, indent=2)
                f.write("\n")

        # A rule left for an instructor isn't the student's failure: don't show a red check for it.
        return 0 if status in ("approved", "under_review") else 1

    def _annotate(self):
        for c in self.changes():
            loc = ""
            if c.get("path"):
                loc = f" file={c['path']}"
                if c.get("line"):
                    loc += f",line={c['line']}"
            msg = c["message"].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error{loc}::{msg}")

    def _summary(self, status, passed):
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not path:
            return
        with open(path, "a") as f:
            f.write(render_markdown(self.result(), heading=2) + "\n")


STATUS_ICON = {"approved": "✅", "changes_needed": "❌", "under_review": "👀", "error": "⚠️", "not_checked": "➖"}
CHECK_ICON = {True: "✅", False: "❌", None: "👀"}


def render_markdown(result, heading=3):
    """The checklist as Markdown, from a result dict. Used by the run summary and the PR review."""
    status = result.get("status", "error")
    checks = result.get("checks") or []
    passed = sum(1 for c in checks if c.get("ok") is True)
    title = result.get("title") or result.get("task", "")
    lines = [f"{'#' * heading} {STATUS_ICON.get(status, '⚠️')} {result.get('task', '')}: {title}", ""]
    if status == "not_checked":
        lines += ["No automatic checks for this task yet.", ""]
    else:
        unsure = sum(1 for c in checks if c.get("ok") is None)
        extra = f", {unsure} for an instructor" if unsure else ""
        lines += [f"**{status.replace('_', ' ')}** ({passed}/{len(checks)} checks passed{extra})", ""]
    if result.get("error"):
        lines += [f"> {_cell(result['error']['message'])}", ""]
    failed = [c for c in checks if c.get("ok") is False]
    if failed:
        lines += ["| What to change | Where |", "| --- | --- |"]
        for c in failed:
            lines.append(f"| {_cell(c.get('message') or c.get('label', ''))} | {_where(c)} |")
        lines.append("")
    instructor = [c for c in checks if c.get("ok") is None]
    if instructor:
        lines += ["**For an instructor** (can't be decided from the code)", ""]
        lines += [f"- {_cell(c.get('label', ''))}: {_cell(c.get('message', ''))}" for c in instructor] + [""]
    notes = result.get("notes") or []
    if notes:
        lines += ["**Notes**", ""] + [f"- {n}" for n in notes] + [""]
    if checks:
        lines += [f"<details><summary>All {len(checks)} checks</summary>", ""]
        lines += [f"- {CHECK_ICON.get(c.get('ok'), '❌')} {c.get('label', '')}" for c in checks]
        lines += ["", "</details>", ""]
    return "\n".join(lines)


def _where(c):
    if not c.get("path"):
        return ""
    return f"`{c['path']}" + (f":{c['line']}" if c.get("line") else "") + "`"


def _cell(text):
    return text.replace("|", "\\|").replace("\n", " ")
