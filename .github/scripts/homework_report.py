"""Shared reporting for the homework checkers.

Every checker builds a Report, records one check per requirement, and calls
finish(). finish() prints a PASS/FAIL checklist, adds GitHub annotations and a
job summary when running in Actions, and writes a result JSON that matches one
entry of the course feedback file (feedback/students/<nickname>.json):

    {"task": "l3-task1", "status": "approved" | "changes_needed" | "error",
     "ref": "<tag or branch>", "changes": [{"message", "path", "line"}],
     "checks": [...], "notes": [...]}

"error" means the checker could not evaluate the submission (for example the
Kconfig does not parse); a teacher should look at it.
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
        return "approved" if all(c["ok"] for c in self.checks) else "changes_needed"

    def changes(self):
        if self.error:
            items = [self.error]
        else:
            items = [c for c in self.checks if not c["ok"]]
        out = []
        for c in items[:MAX_CHANGES]:
            item = {"message": c["message"]}
            if c.get("path"):
                item["path"] = c["path"]
            if c.get("line"):
                item["line"] = c["line"]
            out.append(item)
        return out

    def finish(self, json_path=None):
        status = self.status
        passed = sum(c["ok"] for c in self.checks)

        print(f"{self.task}: {self.title}")
        print("=" * 64)
        if self.error:
            print(f"[ERROR] {self.error['message']}")
        for c in self.checks:
            print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['label']}")
            if not c["ok"] and c["message"] != c["label"]:
                print(f"       -> {c['message']}")
        for n in self.notes:
            print(f"[NOTE] {n}")
        print("=" * 64)
        print(f"{passed}/{len(self.checks)} checks passed; status: {status}")

        if os.environ.get("GITHUB_ACTIONS") == "true":
            self._annotate()
            self._summary(status, passed)

        if json_path:
            result = {
                "task": self.task,
                "status": status,
                "ref": os.environ.get("GITHUB_REF_NAME"),
                "changes": self.changes(),
                "checks": [{"ok": c["ok"], "label": c["label"]} for c in self.checks],
                "notes": self.notes,
            }
            with open(json_path, "w") as f:
                json.dump(result, f, indent=2)
                f.write("\n")

        return 0 if status == "approved" else 1

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
        icon = {"approved": "✅", "changes_needed": "❌", "error": "⚠️"}[status]
        lines = [f"## {icon} {self.task}: {self.title}", "",
                 f"**{status.replace('_', ' ')}** ({passed}/{len(self.checks)} checks passed)", ""]
        if self.error:
            lines += [f"> {self.error['message']}", ""]
        failed = [c for c in self.checks if not c["ok"]]
        if failed:
            lines += ["| What to change | Where |", "| --- | --- |"]
            for c in failed:
                where = ""
                if c.get("path"):
                    where = f"`{c['path']}" + (f":{c['line']}" if c.get("line") else "") + "`"
                lines.append(f"| {_cell(c['message'])} | {where} |")
            lines.append("")
        if self.notes:
            lines += ["**Notes**", ""] + [f"- {n}" for n in self.notes] + [""]
        if self.checks:
            lines += [f"<details><summary>All {len(self.checks)} checks</summary>", ""]
            lines += [f"- {'✅' if c['ok'] else '❌'} {c['label']}" for c in self.checks]
            lines += ["", "</details>", ""]
        with open(path, "a") as f:
            f.write("\n".join(lines) + "\n")


def _cell(text):
    return text.replace("|", "\\|").replace("\n", " ")
