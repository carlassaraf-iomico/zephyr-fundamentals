# l6-task1: LED sensor driver

## Task
Write a sensor driver, following the lecture's structure, for an on-board LED.
`sensor_sample_fetch()` turns the LED on and `sensor_channel_get()` turns it off.

## Automatic checks
`.github/scripts/check_l6_l7.py --task l6-task1`. Names are the student's choice; the driver is
the source that sets `.sample_fetch` / `.channel_get`.
- The driver defines a sensor API struct (`DEVICE_API(sensor, ...)` or
  `static const struct sensor_driver_api`) whose `.sample_fetch` and `.channel_get` point at the
  driver's own functions. Nothing in the repository defines `sensor_sample_fetch` or
  `sensor_channel_get` itself; those are the API calls the app makes.
- The `.sample_fetch` function turns the LED on and the `.channel_get` function turns it off, not
  the other way round and not with a toggle. GPIO and LED API calls count, directly or through a
  helper in the repository, with the level as a literal, a `#define`, or a variable set earlier in
  the function.
- The LED's GPIO comes from devicetree (`GPIO_DT_SPEC_INST_GET`, `GPIO_DT_SPEC_GET` or similar),
  not a hard-coded port and pin.
- The device is instantiated with `DEVICE_DT_INST_DEFINE` (or `SENSOR_DEVICE_DT_INST_DEFINE`,
  `DEVICE_DT_DEFINE`), not `DEVICE_DEFINE`, and `DT_DRV_COMPAT` is defined.
- A devicetree binding (a `.yaml` in a `bindings` folder) has the `compatible` that
  `DT_DRV_COMPAT` names, and an overlay or board devicetree has a node with that `compatible`.
- The app gets the device from devicetree and calls `sensor_sample_fetch()` and
  `sensor_channel_get()`.
- The app builds for the board in `board.txt`, the driver's `.c` file is compiled into it, and the
  built devicetree has the driver's node.

## Decided by an instructor
When the script can't tell from the code, the review says an instructor will check it:
- An LED level the script can't follow (a value from another function, a level that depends on a
  condition, a write to a register).

## Not checked
- The LED on the student's hardware.
