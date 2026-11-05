# Submitting homework

Each task is a branch in your fork, and you submit it by opening a pull request to
`iomico-public/zephyr-course`. Automatic checks build your code, and a reviewer bot comments
on the pull request with what to change. When the task is approved, the bot closes the pull
request. Nothing is ever merged.

The task list is in the course materials. Branch names are the task names:
`l2-task1`, `l3-task1`, `l4-task1`, `l5-task1`, `l5-task2`, `l6-task1`, `l6-task2`, `l7-task1`,
`l7-task2`, `l8-task1`, `l8-task2`.

## Once: fork and name your board

1. Fork `iomico-public/zephyr-course` on GitHub and clone your fork into your west workspace,
   as shown in lecture 2.
2. Create `board.txt` at the root of the repository, next to `west.yml`, with your board's
   name on one line. Use the name you pass to `west build -b`:

   ```
   nucleo_f401re
   ```

   Boards with several CPUs need the full target, e.g. `esp32_devkitc/esp32/procpu`. Without
   hardware, use `native_sim`. The checks build every task for this board, so keep it up to date
   if you change boards.

   `board.txt` is part of `l2-task1`.

## Each task

1. Start the task's branch from your previous task's work, so each task builds on the last:

   ```sh
   git switch l3-task1          # your previous task
   git switch -c l4-task1       # the new task
   ```

2. Do the task, commit, and push the branch to your fork:

   ```sh
   git add -A
   git commit -m "l4-task1: heartbeat LED"
   git push -u origin l4-task1
   ```

3. On GitHub, open a pull request from `<you>/zephyr-course:l4-task1` to
   `iomico-public/zephyr-course:main`. GitHub offers a "Compare & pull request" button right
   after the push. Fill in the template.

4. Wait for the review. The checks usually take a few minutes; tasks that build Zephyr take
   longest. The bot then posts a review on the pull request:

   - ✅ **approved**: the task is done. The bot closes the pull request.
   - ❌ **changes needed**: the review lists what to change, most important first, with the file
     and line where it can. Some items also show as comments on the lines in "Files changed".
   - 👀 **a teacher will review this**: the bot couldn't decide. A teacher looks at it; you
     don't need to do anything.

5. To fix something, commit on the same branch and push again. Every push gets a new review
   on the same pull request. Don't open a new pull request.

Your first pull request may wait for a teacher to approve running the checks. That happens once
for new GitHub accounts.

### Good to know

- The pull request shows every change since you forked, so the `l7-task1` pull request also
  shows your L3 to L6 work. That's expected: the review looks at the task's files, not only the
  latest changes.
- Don't change files in `.github/`. A pull request that does gets no automatic review, only a
  teacher's.
- The checks build your code on GitHub's servers, so a task approved here builds without your
  local setup. Results show in the pull request's "Checks" tab as well, with the build log.
- The full review (automatic checks plus the rules a script can't judge) runs at most 5 times a
  day per pull request. After that, the automatic checks still run on each push, and the rest of
  the review waits.
- Pushing a tag, as in earlier courses (`git tag l4-task1 && git push origin l4-task1`), still
  runs the automatic checks in your fork's Actions tab. Only a pull request gets the full review
  and counts as a submission.

## For teachers

Setup on `iomico-public/zephyr-course` before the batch starts:

- **Workflows**: `.github/workflows/homework-check.yml` builds and checks the code on the pull
  request, with no secrets. `.github/workflows/homework-review.yml` runs after it from `main`,
  reads the result and the PR's files through the API, runs the AI review, and posts.
- **Settings → Actions → General**:
  - Fork pull request workflows: "Require approval for first-time contributors who are new to
    GitHub".
  - Workflow permissions: read repository contents.
  - Allowed actions: GitHub-owned, plus `zephyrproject-rtos/*`.
- **Environment `ai-review`**: deployment branches limited to `main`. Secret
  `ANTHROPIC_API_KEY`, from a dedicated Console workspace with a monthly spend limit.
- **Variables** (optional, Settings → Secrets and variables → Actions → Variables):

  | Variable | Default | Meaning |
  | --- | --- | --- |
  | `MANUAL_REVIEWER` | `carlassaraf` | Mentioned when the bot can't decide |
  | `REVIEW_MODEL` | `claude-opus-5-5` | Model for the AI review (`claude-sonnet-5-5` costs half) |
  | `REVIEW_EFFORT` | `medium` | `low`, `medium` or `high` |
  | `AI_DAILY_LIMIT` | `5` | AI reviews per pull request in 24 hours |
  | `CLOSE_APPROVED` | `true` | Close approved pull requests |

- **Labels**: the bot creates them when first needed: one per task, plus `approved`,
  `changes-needed` and `needs-teacher`.
- **Ruleset on `main`**: block merges and pushes for everyone except admins.

The rules each task is checked against are in `.github/rubric/`. To try the AI review on a local
checkout without posting anything:

```sh
pip install anthropic
python3 .github/scripts/ai_review.py --task l4-task1 --dir path/to/checkout --dry-run   # prompt only
python3 .github/scripts/ai_review.py --task l4-task1 --dir path/to/checkout --result result.json
```
