# l6-task1: LED sensor driver

## Task
Write a sensor driver, following the lecture's structure, for an on-board LED.
`sensor_sample_fetch()` turns the LED on and `sensor_channel_get()` turns it off.

## Automatic checks
None yet: the AI judges every rule below.

## AI checks
- The driver is in its own folder: `drivers/sensor/<name>/` or `app/drivers/[sensor/]<name>/`,
  with a `.c` file, a devicetree binding (`dts/bindings/...yaml`) with a `compatible`, and the
  `CMakeLists.txt` / `Kconfig` wiring that adds it to the build (directly from the app, or as a
  module through `zephyr/module.yml`).
- The driver defines a sensor API struct (`DEVICE_API(sensor, ...)` or
  `static const struct sensor_driver_api`) whose `.sample_fetch` and `.channel_get` point at the
  driver's own functions. A driver doesn't define `sensor_sample_fetch` or `sensor_channel_get`
  itself; those are the API calls the app makes.
- The `.sample_fetch` function turns the LED on, and the `.channel_get` function turns it off.
- The LED's GPIO comes from devicetree (a `gpios` property read with `GPIO_DT_SPEC_INST_GET` or
  similar), not a hard-coded port and pin.
- The device is instantiated with `DEVICE_DT_INST_DEFINE` (or `SENSOR_DEVICE_DT_INST_DEFINE`)
  for each enabled instance, and the app's overlay adds a node with the driver's `compatible`.
- The app gets the device from devicetree and calls `sensor_sample_fetch()` and
  `sensor_channel_get()`.

## Not checked
- The LED on the student's hardware.
