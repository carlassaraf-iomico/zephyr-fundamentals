# l8-task2: coverage

## Task
Run the ring_buf tests with coverage (`--coverage --coverage-tool gcovr --coverage-basedir
app/modules/ring_buf`) and reach lines ≥ 81%, functions 100% and branches ≥ 64%.

## Automatic checks
- All tests pass, and CI's own coverage run meets each target. Each metric below its target is
  one change, naming what no test reaches. A committed `twister-out/coverage/` is ignored.
