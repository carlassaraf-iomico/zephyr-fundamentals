#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/shell/shell.h>
#include <zephyr/shell/shell_string_conv.h>

#include <custom_led/custom_led.h>

// Same compatible as the driver, so the shell only works on custom LED devices
#define DT_DRV_COMPAT course_custom_led

// Blink periods `sensor set` accepts, in ms
#define CUSTOM_LED_SHELL_PERIOD_MIN_MS 100U
#define CUSTOM_LED_SHELL_PERIOD_MAX_MS 5000U

// Every enabled custom LED in devicetree, in instance order
#define CUSTOM_LED_DEVICE(inst) DEVICE_DT_INST_GET(inst),
static const struct device *const custom_leds[] = {
  DT_INST_FOREACH_STATUS_OKAY(CUSTOM_LED_DEVICE)
};

/**
 * @brief Pick the device a command acts on
 * @param sh Shell instance, for error messages
 * @param name Device name from the command line, or NULL to use the first custom LED
 * @return The named custom LED, the first one when no name is given, or NULL if there is none
 */
static const struct device *custom_led_from_name(const struct shell *sh, const char *name) {
  if (ARRAY_SIZE(custom_leds) == 0) {
    shell_error(sh, "No custom LED devices in devicetree");
    return NULL;
  }
  if (name == NULL) {
    return custom_leds[0];
  }
  for (size_t i = 0; i < ARRAY_SIZE(custom_leds); i++) {
    if (strcmp(custom_leds[i]->name, name) == 0) {
      return custom_leds[i];
    }
  }
  shell_error(sh, "Unknown custom LED device: %s", name);
  return NULL;
}

/**
 * @brief Pick the device a command acts on and make sure it is ready
 * @return The device, or NULL after printing an error
 */
static const struct device *custom_led_ready_from_name(const struct shell *sh, const char *name) {
  const struct device *dev = custom_led_from_name(sh, name);
  if (dev != NULL && !device_is_ready(dev)) {
    shell_error(sh, "%s is not ready", dev->name);
    return NULL;
  }
  return dev;
}

// sensor fetch [device]: turn the LED on through sensor_sample_fetch()
static int cmd_fetch(const struct shell *sh, size_t argc, char **argv) {
  const struct device *dev = custom_led_ready_from_name(sh, argc > 1 ? argv[1] : NULL);
  if (dev == NULL) {
    return -ENODEV;
  }
  int ret = sensor_sample_fetch(dev);
  if (ret < 0) {
    shell_error(sh, "%s: sensor_sample_fetch() failed (%d)", dev->name, ret);
    return ret;
  }
  shell_print(sh, "%s: fetched", dev->name);
  return 0;
}

// sensor read [device]: sensor_channel_get() and print what it returned
static int cmd_read(const struct shell *sh, size_t argc, char **argv) {
  const struct device *dev = custom_led_ready_from_name(sh, argc > 1 ? argv[1] : NULL);
  if (dev == NULL) {
    return -ENODEV;
  }
  struct sensor_value val = {0};
  int ret = sensor_channel_get(dev, SENSOR_CHAN_ALL, &val);
  if (ret < 0) {
    shell_error(sh, "%s: sensor_channel_get() failed (%d)", dev->name, ret);
    return ret;
  }
  shell_print(sh, "%s: val1=%d val2=%d", dev->name, val.val1, val.val2);
  return 0;
}

// sensor info [device]: print the device name and whether it is ready
static int cmd_info(const struct shell *sh, size_t argc, char **argv) {
  const struct device *dev = custom_led_from_name(sh, argc > 1 ? argv[1] : NULL);
  if (dev == NULL) {
    return -ENODEV;
  }
  shell_print(sh, "name: %s", dev->name);
  shell_print(sh, "ready: %s", device_is_ready(dev) ? "yes" : "no");
  return 0;
}

// sensor set <period_ms> [device]: set the blink period through custom_led_set_period()
static int cmd_set(const struct shell *sh, size_t argc, char **argv) {
  // SHELL_CMD_ARG already rejects a missing value; this keeps the handler safe on its own
  if (argc < 2) {
    shell_error(sh, "Missing period. Usage: set <period_ms> [device]");
    return -EINVAL;
  }
  int err = 0;
  unsigned long period_ms = shell_strtoul(argv[1], 10, &err);
  if (err != 0) {
    shell_error(sh, "Invalid period: %s (expected a number of ms)", argv[1]);
    return -EINVAL;
  }
  if (period_ms < CUSTOM_LED_SHELL_PERIOD_MIN_MS || period_ms > CUSTOM_LED_SHELL_PERIOD_MAX_MS) {
    shell_error(sh, "Period %lu ms out of range (%u-%u ms)", period_ms,
                CUSTOM_LED_SHELL_PERIOD_MIN_MS, CUSTOM_LED_SHELL_PERIOD_MAX_MS);
    return -EINVAL;
  }
  const struct device *dev = custom_led_ready_from_name(sh, argc > 2 ? argv[2] : NULL);
  if (dev == NULL) {
    return -ENODEV;
  }
  int ret = custom_led_set_period(dev, (uint32_t)period_ms);
  if (ret < 0) {
    shell_error(sh, "%s: custom_led_set_period() failed (%d)", dev->name, ret);
    return ret;
  }
  shell_print(sh, "%s: period set to %u ms", dev->name, custom_led_get_period(dev));
  return 0;
}

// Mandatory counts include the subcommand itself: fetch/read/info take an optional device name,
// set needs the period (2 mandatory) and takes an optional device name
SHELL_STATIC_SUBCMD_SET_CREATE(sub_sensor,
  SHELL_CMD_ARG(fetch, NULL, "Turn the LED on (sensor_sample_fetch). Usage: fetch [device]", cmd_fetch, 1, 1),
  SHELL_CMD_ARG(read, NULL, "Read the LED and turn it off (sensor_channel_get). Usage: read [device]", cmd_read, 1, 1),
  SHELL_CMD_ARG(info, NULL, "Print the device name and ready state. Usage: info [device]", cmd_info, 1, 1),
  SHELL_CMD_ARG(set, NULL, "Set the blink period (100-5000 ms). Usage: set <period_ms> [device]", cmd_set, 2, 1),
  SHELL_SUBCMD_SET_END
);

SHELL_CMD_REGISTER(sensor, &sub_sensor, "Custom LED sensor commands", NULL);
