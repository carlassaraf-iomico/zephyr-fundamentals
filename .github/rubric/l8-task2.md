# l8-task2: coverage

## Task
Run the ring_buf tests with coverage (`--coverage --coverage-tool gcovr --coverage-basedir
app/modules/ring_buf`) and reach lines ≥ 81%, functions 100% and branches ≥ 64%.

## Automatic checks
- All tests pass, and CI's own coverage run meets each target. Each metric below its target is
  one change, naming what no test reaches.
- The student commits `twister-out/coverage/` (gcovr's `index.html`), as tasks.md asks. Another
  folder is accepted with a note. Its numbers must match CI's run on the same commit, within 1
  point for lines, 0.5 for functions and 5 for branches (branch counts vary between gcc versions).
  A report that doesn't match is stale or not from these tests: regenerate and commit it.
