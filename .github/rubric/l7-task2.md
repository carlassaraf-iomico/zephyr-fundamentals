# l7-task2: set command

## Task
Expose the l6-task2 extension API as a shell subcommand, e.g. `sensor set <value>`. The command
validates its argument and prints an error with `shell_error` when it is missing or out of range.
`SHELL_CMD_ARG` enforces the argument count.

## Automatic checks
`.github/scripts/check_l6_l7.py --task l7-task2`.
- A subcommand named `set`, or one whose handler calls the extension API, registered with
  `SHELL_CMD_ARG`.
- A missing argument is rejected: the mandatory count includes the value (e.g. `2, 0`), or the
  handler checks `argc` and calls `shell_error`.
- An out-of-range value is rejected with `shell_error`: there is both a minimum and a maximum
  check (the student picks the range), or a closed set of valid values (`0`/`1`, `on`/`off`,
  string compares, `shell_strtobool`).
- The parsed value is passed to the extension API, directly or through a helper.
- The app builds for the board in `board.txt`, and the driver and the shell code are compiled
  into it.

## Decided by a teacher
- A handler with no range check of its own that relies on the driver returning an error.

## Not checked
- Running the command on the board.
