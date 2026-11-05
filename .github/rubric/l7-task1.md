# l7-task1: shell commands

## Task
Using the l6-task1 sensor driver, add a `sensor` root shell command with the subcommands:
`fetch` calls `sensor_sample_fetch()`, `read` calls `sensor_channel_get()` and prints the result,
`info` prints the device name and ready state.

## Automatic checks
`.github/scripts/check_l6_l7.py --task l7-task1`.
- One root command registered with `SHELL_CMD_REGISTER` (in any file), with subcommands
  `fetch`, `read` and `info` (`SHELL_STATIC_SUBCMD_SET_CREATE` or similar). The root may be named
  `sensor` or something else; separate root commands don't count.
- `fetch` calls `sensor_sample_fetch()`, directly or through a helper.
- `read` calls `sensor_channel_get()` and prints something that comes from it: the
  `sensor_value`, the return code, or a message chosen by the return code. A fixed text doesn't
  count.
- `info` prints the device's real name (`dev->name`, `DEVICE_DT_NAME(...)`, ...), not a
  hard-coded string, and the ready state from `device_is_ready()`. Reading
  `dev->state->initialized` passes with a note pointing to `device_is_ready()`.
- The shell is enabled (`CONFIG_SHELL=y` in the build).
- The driver still has `.sample_fetch` and `.channel_get`.
- The app builds for the board in `board.txt`, and the driver and the shell code are compiled
  into it.

## Decided by an instructor
- A handler the script can't find (registered through a macro of the student's own).

## Not checked
- Running the commands on the board.
