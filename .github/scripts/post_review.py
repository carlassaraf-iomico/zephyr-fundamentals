#!/usr/bin/env python3
"""Post the homework review on a pull request.

Runs in the "Homework review" workflow (workflow_run, from the default branch,
with secrets). It never checks out or runs anything from the PR:

1. Finds the PR through the API from the check run's head repository, branch
   and SHA, and skips a SHA that was already reviewed.
2. Takes the task from the PR's branch name, and refuses to trust a PR that
   changes `.github/` (its check run used the PR's own workflow).
3. Reads result.json from the check run's artifact and checks it is for that task.
4. Runs the AI review (ai_review.py) when the scripts passed and the task has
   rules only the AI can judge. Files come from the PR head through the API.
5. Posts one review (event COMMENT) with the status, the changes and the
   checklist, inline comments on lines in the diff, and labels. Approved PRs
   are closed.

    python3 post_review.py --artifacts DIR            # in the workflow
    python3 post_review.py --artifacts DIR --pr 12 --dry-run   # print, post nothing
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_review  # noqa: E402
import github_api as gh  # noqa: E402
from homework_report import render_markdown  # noqa: E402

TASKS = ["l2-task1", "l3-task1", "l4-task1", "l5-task1", "l5-task2", "l6-task1", "l6-task2",
         "l7-task1", "l7-task2", "l8-task1", "l8-task2"]
TASK_RE = re.compile(r"^(l[2-8]-task[12])(?:$|[^0-9])")
MARKER = "<!-- homework-bot sha={sha} task={task} status={status} ai={ai} -->"
MARKER_RE = re.compile(r"<!-- homework-bot sha=(\w+) task=(\S*) status=(\w+) ai=(\d) -->")
RANK = {"approved": 0, "changes_needed": 1, "under_review": 2}
LABELS = {
    "approved": ("approved", "0e8a16", "Homework approved by the checks"),
    "changes_needed": ("changes-needed", "d93f0b", "Homework needs changes"),
    "under_review": ("needs-instructor", "fbca04", "An instructor reviews this by hand"),
}
TASK_LABEL_COLOR = "1d76db"
BOT_LOGINS = {"github-actions[bot]"}


def log(msg):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- inputs

def task_of(branch):
    m = TASK_RE.match(branch or "")
    return m.group(1) if m and m.group(1) in TASKS else None


def find_pr(repo, run, pr_number=None):
    """The open PR whose head is the check run's commit, or None."""
    if pr_number:
        return gh.get(f"repos/{repo}/pulls/{pr_number}")
    sha = run["head_sha"]
    candidates = [p["number"] for p in run.get("pull_requests") or []]
    if not candidates:  # always empty for PRs from forks
        owner = run["head_repository"]["owner"]["login"]
        candidates = [p["number"] for p in gh.get_all(
            f"repos/{repo}/pulls", state="open", head=f"{owner}:{run['head_branch']}")]
    for n in candidates:
        pr = gh.get(f"repos/{repo}/pulls/{n}")
        if pr["head"]["sha"] == sha and pr["base"]["repo"]["full_name"] == repo:
            return pr
    return None


def load_result(artifacts, task):
    """result.json from the check run, or (None, why)."""
    path = Path(artifacts) / "homework-result" / "result.json"
    if not path.is_file():
        matches = list(Path(artifacts).rglob("result.json"))
        path = matches[0] if len(matches) == 1 else path
    if not path.is_file():
        return None, "The checks didn't produce a result for this commit."
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError("too large")
        result = json.loads(path.read_text())
        if not isinstance(result, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as e:
        return None, f"The checks' result can't be read ({e})."
    if result.get("task") != task:
        return None, f"The checks ran for `{result.get('task')}`, not `{task}`."
    if result.get("status") not in ("approved", "changes_needed", "under_review", "error", "not_checked"):
        return None, "The checks' result has an unknown status."
    return result, None


def bot_reviews(repo, number):
    out = []
    for r in gh.get_all(f"repos/{repo}/pulls/{number}/reviews"):
        m = MARKER_RE.search(r.get("body") or "")
        if m and (r.get("user") or {}).get("login") in BOT_LOGINS:
            out.append({"sha": m.group(1), "task": m.group(2), "status": m.group(3),
                        "ai": m.group(4) == "1", "at": r.get("submitted_at")})
    return out


def ai_reviews_today(reviews):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    n = 0
    for r in reviews:
        if r["ai"] and r["at"]:
            at = dt.datetime.fromisoformat(r["at"].replace("Z", "+00:00"))
            n += at >= since
    return n


# ---------------------------------------------------------------- PR head files

def head_files(repo, sha, task, changed):
    tree = gh.get(f"repos/{repo}/git/trees/{sha}", recursive=1)
    blobs = {e["path"]: e for e in tree.get("tree", []) if e.get("type") == "blob"}

    def read(path):
        e = blobs.get(path)
        if not e or e.get("size", 0) > ai_review.MAX_FILE_CHARS:
            return None
        data = gh.get(f"repos/{repo}/git/blobs/{e['sha']}")
        try:
            return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        except ValueError:
            return None

    return ai_review.build_files(task, read, set(blobs), changed)


def diff_lines(pr_files):
    """{path: set of new-side line numbers GitHub accepts inline comments on}."""
    out = {}
    for f in pr_files:
        lines, new = set(), 0
        for row in (f.get("patch") or "").splitlines():
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", row)
            if m:
                new = int(m.group(1))
                continue
            if row.startswith("-"):
                continue
            if row.startswith(("+", " ")):
                lines.add(new)
                new += 1
        out[f["filename"]] = lines
    return out


# ---------------------------------------------------------------- decision

def decide(task, result, result_problem, touches_github, ai_call):
    """Returns (status, summary, changes, reason, ai_ran). `ai_call()` runs the AI review."""
    if touches_github:
        return ("under_review", "This pull request changes files in `.github/`, so its checks "
                "can't be trusted. An instructor will review it.", [],
                "The PR changes `.github/`.", False)
    if result is None:
        return ("under_review", f"{result_problem} An instructor will look at it.", [],
                result_problem, False)
    status = result["status"]
    if status == "error":
        msg = (result.get("error") or {}).get("message", "The checks could not evaluate this commit.")
        return ("under_review", "The checks could not evaluate this commit. An instructor will look at it.",
                [], msg, False)
    if status == "changes_needed":
        return ("changes_needed", "The automatic checks found something to change.",
                result.get("changes") or [], "", False)
    if status == "under_review":  # the scripts passed what they could decide; the rest is the instructor's
        unsure = [c.get("label", "") for c in result.get("checks") or [] if c.get("ok") is None]
        return ("under_review", "The automatic checks passed everything they can decide. An instructor will check "
                "the rest; you don't need to do anything.", [],
                "Not decided by the checks: " + "; ".join(unsure) + ".", False)
    if task not in ai_review.AI_TASKS:
        if status == "approved":
            return ("approved", "All automatic checks passed.", [], "", False)
        return ("under_review", "This task has no automatic checks yet. An instructor will review it.",
                [], "No checks and no AI rules for this task.", False)

    ai = ai_call()
    if ai is None:
        return None  # daily limit: the caller explains
    if ai["status"] == "off":  # AI review switched off: the instructor's batch review covers these rules
        if status == "approved":
            return ("under_review", "All automatic checks passed. An instructor will check the rest of "
                    "this task; you don't need to do anything.", [], "", False)
        return ("under_review", "This task has no automatic checks yet. An instructor will review it; "
                "you don't need to do anything.", [], "", False)
    if ai["status"] == "approved":
        return ("approved", "All automatic checks passed, and the code meets the task's other rules.",
                [], ai.get("reason", ""), True)
    if ai["status"] == "changes_needed":
        lead = ("The automatic checks passed, but the code" if status == "approved"
                else "The code")
        return ("changes_needed", f"{lead} doesn't meet all of the task's rules yet.",
                ai["changes"], ai.get("reason", ""), True)
    return ("under_review", "An instructor will review this task.", [], ai.get("reason", ""), True)


# ---------------------------------------------------------------- output

HEADINGS = {
    "approved": "✅ {task} approved",
    "changes_needed": "❌ {task}: changes needed",
    "under_review": "👀 {task}: an instructor will review this",
    "limited": "⏸️ {task}: review paused",
}


def where(c):
    if not c.get("path"):
        return ""
    return f" (`{c['path']}" + (f":{c['line']}" if c.get("line") else "") + "`)"


def compose(task, sha, status, summary, changes, reason, ai_ran, result, reviewer, extra=""):
    # A paused review doesn't count as reviewing the commit, so a rerun can still review it.
    marker_sha = "limited" if status == "limited" else sha
    lines = [MARKER.format(sha=marker_sha, task=task or "-", status=status, ai=int(ai_ran)),
             f"## {HEADINGS[status].format(task=task or 'Submission')}", "", summary, ""]
    if changes:
        lines += ["### What to change", ""]
        lines += [f"{i}. {c['message']}{where(c)}" for i, c in enumerate(changes, 1)]
        lines.append("")
    if status == "under_review" and reviewer:
        lines += [f"@{reviewer}, please review this by hand: {reason or 'see above.'}", ""]
    if extra:
        lines += [extra, ""]
    if result:
        checks = result.get("checks") or []
        passed = sum(1 for c in checks if c.get("ok") is True)
        unsure = sum(1 for c in checks if c.get("ok") is None)
        label = (f"Automatic checks ({passed}/{len(checks)} passed" + (f", {unsure} for an instructor)" if unsure else ")")
                 if checks else "Automatic checks")
        lines += [f"<details><summary>{label}</summary>", "",
                  render_markdown(result, heading=4), "</details>", ""]
    if status == "approved":
        lines.append(f"Reviewed commit {sha[:7]}. Nothing else to do for this task; "
                     "this pull request will be closed.")
    elif status == "limited":
        lines.append(f"Checked commit {sha[:7]}.")
    else:
        lines.append(f"Reviewed commit {sha[:7]}. Push a new commit to this branch "
                     "to get a new review.")
    return "\n".join(lines)


def post(repo, pr, sha, body, changes, pr_files, dry_run):
    commentable = diff_lines(pr_files)
    comments = [{"path": c["path"], "line": c["line"], "side": "RIGHT", "body": c["message"]}
                for c in changes
                if c.get("path") and c.get("line") in commentable.get(c["path"], ())]
    payload = {"commit_id": sha, "event": "COMMENT", "body": body, "comments": comments}
    if dry_run:
        log(f"[dry-run] review on #{pr['number']} with {len(comments)} inline comments:\n{body}")
        return
    try:
        gh.post(f"repos/{repo}/pulls/{pr['number']}/reviews", payload)
    except gh.GitHubError as e:
        if e.status != 422 or not comments:
            raise
        log(f"Inline comments rejected ({e}); posting the review without them.")
        payload["comments"] = []
        gh.post(f"repos/{repo}/pulls/{pr['number']}/reviews", payload)


def set_labels(repo, pr, task, status, dry_run):
    wanted = {LABELS[status][0]} | ({task} if task else set())
    managed = {v[0] for v in LABELS.values()}
    current = {lab["name"] for lab in pr.get("labels") or []}
    remove = (current & managed) - wanted
    add = wanted - current
    if dry_run:
        log(f"[dry-run] labels: add {sorted(add)}, remove {sorted(remove)}")
        return
    for name in add:
        try:
            gh.get(f"repos/{repo}/labels/{name}")
        except gh.GitHubError as e:
            if e.status != 404:
                raise
            spec = next((v for v in LABELS.values() if v[0] == name), (name, TASK_LABEL_COLOR, f"Homework {name}"))
            try:
                gh.post(f"repos/{repo}/labels", {"name": spec[0], "color": spec[1], "description": spec[2]})
            except gh.GitHubError as e2:
                if e2.status != 422:  # created meanwhile
                    raise
    for name in remove:
        try:
            gh.delete(f"repos/{repo}/issues/{pr['number']}/labels/{name}")
        except gh.GitHubError as e:
            if e.status != 404:
                raise
    if add:
        gh.post(f"repos/{repo}/issues/{pr['number']}/labels", {"labels": sorted(add)})


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifacts", required=True, help="folder with the check run's artifacts")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"),
                    help="workflow_run event JSON (default: the current event)")
    ap.add_argument("--pr", type=int, help="review this PR instead of finding it from the event")
    ap.add_argument("--ai-json", type=Path, help="use this AI review instead of calling the API (testing)")
    ap.add_argument("--dry-run", action="store_true", help="print the review; post nothing")
    args = ap.parse_args()

    reviewer = (os.environ.get("MANUAL_REVIEWER") or "carlassaraf").lstrip("@")
    daily_cap = int(os.environ.get("AI_DAILY_LIMIT") or 5)
    close_approved = os.environ.get("CLOSE_APPROVED", "true") != "false"
    # Off unless AI_REVIEW=on and the API key is set.
    ai_enabled = os.environ.get("AI_REVIEW") == "on" and bool(os.environ.get("ANTHROPIC_API_KEY"))

    run = {}
    if args.event and Path(args.event).is_file():
        run = json.loads(Path(args.event).read_text()).get("workflow_run") or {}
    if not run and not args.pr:
        log("No workflow_run event and no --pr; nothing to review.")
        return 1

    pr = find_pr(args.repo, run, args.pr)
    if pr is None:
        log("No open PR has this commit as its head (closed, or a newer push); nothing to post.")
        return 0
    if pr["state"] != "open":
        log(f"PR #{pr['number']} is {pr['state']}; nothing to post.")
        return 0
    sha = pr["head"]["sha"]
    if run and run.get("head_sha") != sha:
        log("The PR head moved since this check run; the newer run will review it.")
        return 0

    reviews = bot_reviews(args.repo, pr["number"])
    if any(r["sha"] == sha for r in reviews):
        log(f"Commit {sha[:7]} was already reviewed on PR #{pr['number']}.")
        return 0

    task = task_of(pr["head"]["ref"])
    pr_files = gh.get_all(f"repos/{args.repo}/pulls/{pr['number']}/files")
    if task is None:
        body = compose(None, sha, "changes_needed",
                       f"`{pr['head']['ref']}` is not a task name, so no checks ran.",
                       [{"message": "Push your work to a branch named after the task, e.g. `l4-task1`, "
                                    "and open a pull request from that branch."}],
                       "", False, None, reviewer)
        post(args.repo, pr, sha, body, [], pr_files, args.dry_run)
        set_labels(args.repo, pr, None, "changes_needed", args.dry_run)
        return 0

    touches_github = any(f["filename"].startswith(".github/") or
                         (f.get("previous_filename") or "").startswith(".github/") for f in pr_files)
    result, problem = load_result(args.artifacts, task)
    if result is None and run.get("conclusion") == "cancelled":
        log("The check run was cancelled; nothing to post.")
        return 0

    ai_out = {}

    def ai_call():
        if args.ai_json:
            ai_out.update(json.loads(args.ai_json.read_text()))
            return ai_out
        if ai_reviews_today(reviews) >= daily_cap:
            return None
        if not ai_enabled:
            ai_out.update(status="off")
            return ai_out
        changed = {f["filename"] for f in pr_files}
        files, skipped = head_files(args.repo, sha, task, changed)
        try:
            ai_out.update(ai_review.review(task, result, files, skipped,
                                           os.environ.get("REVIEW_MODEL") or None,
                                           os.environ.get("REVIEW_EFFORT") or None))
        except Exception as e:  # API down, rate limit, ...: an instructor looks instead
            log(f"AI review failed: {e!r}")
            ai_out.update(status="under_review", reason=f"The AI review failed ({type(e).__name__}).")
        return ai_out

    decision = decide(task, result, problem, touches_github, ai_call)
    if decision is None:
        body = compose(task, sha, "limited", "The automatic checks passed.", [], "", False, result, None,
                       extra=(f"This task already had {daily_cap} full reviews in the last 24 hours, "
                              "so the rest of the review is paused. Push again later to get it."))
        post(args.repo, pr, sha, body, [], pr_files, args.dry_run)
        return 0
    status, summary, changes, reason, ai_ran = decision

    if ai_out.get("usage"):
        log(f"AI review: {ai_out.get('model')} {ai_out['usage']} status={ai_out.get('status')} "
            f"reason={ai_out.get('reason')!r}")
    # Routine instructor reviews (the AI is off, or a rule the scripts can't decide) only get the
    # `needs-instructor` label; a mention is for real problems (.github changes, broken checks).
    routine = not touches_github and result is not None and (
        ai_out.get("status") == "off" or result.get("status") == "under_review")
    mention = None if routine else reviewer
    body = compose(task, sha, status, summary, changes, reason, ai_ran, result, mention)
    post(args.repo, pr, sha, body, changes, pr_files, args.dry_run)
    set_labels(args.repo, pr, task, status, args.dry_run)
    if status == "approved" and close_approved:
        if args.dry_run:
            log(f"[dry-run] close PR #{pr['number']}")
        else:
            gh.patch(f"repos/{args.repo}/pulls/{pr['number']}", {"state": "closed"})

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"PR #{pr['number']} ({task}, {sha[:7]}): **{status}**"
                    + (f" (AI: {ai_out.get('model')}, {ai_out.get('usage')})" if ai_ran else "") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
