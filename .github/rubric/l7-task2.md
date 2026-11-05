# l7-task2: set command

## Task
Expose the l6-task2 extension API as a shell subcommand, e.g. `sensor set <value>`. The command
validates its argument and prints an error with `shell_error` when it is missing or out of range.
`SHELL_CMD_ARG` enforces the argument count.

## Automatic checks
None yet: the AI judges every rule below.

## AI checks
- `set` is registered with `SHELL_CMD_ARG`.
- A missing argument is rejected with an error: either the mandatory argument count includes the
  value (e.g. `2, 0`), so the shell rejects it, or the handler checks `argc` and calls
  `shell_error`.
- An out-of-range value is rejected with `shell_error`: there is both a minimum and a maximum
  check (the student picks the range), or a closed set of valid values (`0`/`1`, `on`/`off`)
  that rejects anything else.
- The parsed value is passed to the l6-task2 extension API function.
