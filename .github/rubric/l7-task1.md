# l7-task1: shell commands

## Task
Using the l6-task1 sensor driver, add a `sensor` root shell command with the subcommands:
`fetch` calls `sensor_sample_fetch()`, `read` calls `sensor_channel_get()` and prints the result,
`info` prints the device name and ready state.

## Automatic checks
None yet: the AI judges every rule below.

## AI checks
- A root command registered with `SHELL_CMD_REGISTER` (any file), with subcommands `fetch`,
  `read` and `info` from `SHELL_STATIC_SUBCMD_SET_CREATE` or similar. The root may be named
  `sensor` or something close; the subcommands must exist.
- `fetch` calls `sensor_sample_fetch()` on the LED sensor device.
- `read` calls `sensor_channel_get()` and prints something that comes from that call: the
  `sensor_value` (`val1`/`val2`), the return code, or a success or error message based on the
  return code. A fixed text that doesn't depend on the call doesn't count.
- `info` prints the device's real name and its ready state. Any source of the real name counts
  (`dev->name`, `DEVICE_DT_NAME(...)`, ...); a hard-coded string doesn't. The ready state comes
  from `device_is_ready()`.
- The shell is enabled (`CONFIG_SHELL=y` in `prj.conf` or an overlay config).
