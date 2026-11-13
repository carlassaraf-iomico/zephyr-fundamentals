# Submitting homework

Each task is a branch in your fork, named after the task (`lX-taskY`, e.g. `l4-task1`). You
submit a task by opening a pull request from its branch to `iomico-public/zephyr-course`.
Automatic checks build your code, and a reviewer bot comments on the pull request with what to
change. When the task is approved, the bot closes the pull request. Nothing is ever merged.

Every task's branch starts from `main`, and your fork's `main` stays exactly as you forked it:
never commit to it. All your work for a task goes on that task's branch.

## Once: fork and clone

Fork `iomico-public/zephyr-course` on GitHub and clone your fork into your west workspace, as
shown in the course.

## Start a task

Create the task's branch from `main` before you change anything:

```sh
git switch main
git switch -c l4-task1
```

The branch must hold everything the task needs to build and run. If a task builds on work from
an earlier task, bring that work into the new branch in whatever way suits you, for example by
copying files from the earlier branch with `git checkout <earlier-branch> -- <path>`.

## Submit a task

1. Do the task on its branch, commit, and push the branch to your fork:

   ```sh
   git add -A
   git commit -m "l4-task1: heartbeat LED"
   git push -u origin l4-task1
   ```

2. On GitHub, open a pull request from `<you>/zephyr-course:l4-task1` to
   `iomico-public/zephyr-course:main`. GitHub offers a "Compare & pull request" button right
   after the push. Fill in the template.

3. Wait for the review. The checks usually take a few minutes; tasks that build Zephyr take
   longest. The bot then posts a review on the pull request:

   - ✅ **approved**: the task is done. The bot closes the pull request.
   - ❌ **changes needed**: the review lists what to change, most important first, with the file
     and line where it can. Some items also show as comments on the lines in "Files changed".
     Fix them as shown below.
   - 👀 **an instructor will review this**: the checks passed but couldn't decide everything. An
     instructor looks at it; you don't need to do anything.

Your first pull request may wait for an instructor to approve running the checks. That happens
once for new GitHub accounts.

## Fix a task

Commit the fix on the task's own branch and push it again:

```sh
git switch l4-task1          # if you're not on it already
git add -A
git commit -m "l4-task1: use the app-led alias"
git push
```

The same pull request gets a new review. Don't open a new pull request.

## Your board

The checks build your code for the board named in `board.txt`, a file at the root of the
repository, next to `west.yml`, holding your board's name on one line. Use the name you pass to
`west build -b`:

```
nucleo_f401re
```

Boards with several CPUs need the full target, e.g. `esp32_devkitc/esp32/procpu`. Without
hardware, use `native_sim`. Every task branch with app code needs this file; without it, the
checks build for `native_sim` and ask you to add it.

## Good to know

- Don't change files in `.github/`. A pull request that does gets no automatic review, only an
  instructor's.
- The checks build your code on GitHub's servers, so a task approved here builds without your
  local setup. Results show in the pull request's "Checks" tab as well, with the build log.
- Some tasks also run the course's tests from `tests/` with your code. They rely on the names
  the task asks for, so keep those names exactly as written.
