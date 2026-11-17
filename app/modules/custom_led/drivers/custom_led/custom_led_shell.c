#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/shell/shell.h>

// Same compatible as the driver, so the shell only works on custom LED devices
#define DT_DRV_COMPAT course_custom_led

// Every enabled custom LED in devicetree, in instance order
#define CUSTOM_LED_DEVICE(inst) DEVICE_DT_INST_GET(inst),
static const struct device *const custom_leds[] = {
  DT_INST_FOREACH_STATUS_OKAY(CUSTOM_LED_DEVICE)
};

/**
 * @brief Pick the device a command acts on
 * @param sh Shell instance, for error messages
 * @param argc Argument count; argv[1] is the optional device name
 * @param argv Arguments
 * @return The named custom LED, the first one when no name is given, or NULL if there is none
 */
static const struct device *custom_led_from_args(const struct shell *sh, size_t argc, char **argv) {
  if (ARRAY_SIZE(custom_leds) == 0) {
    shell_error(sh, "No custom LED devices in devicetree");
    return NULL;
  }
  if (argc < 2) {
    return custom_leds[0];
  }
  for (size_t i = 0; i < ARRAY_SIZE(custom_leds); i++) {
    if (strcmp(custom_leds[i]->name, argv[1]) == 0) {
      return custom_leds[i];
    }
  }
  shell_error(sh, "Unknown custom LED device: %s", argv[1]);
  return NULL;
}

/**
 * @brief Pick the device a command acts on and make sure it is ready
 * @return The device, or NULL after printing an error
 */
static const struct device *custom_led_ready_from_args(const struct shell *sh, size_t argc, char **argv) {
  const struct device *dev = custom_led_from_args(sh, argc, argv);
  if (dev != NULL && !device_is_ready(dev)) {
    shell_error(sh, "%s is not ready", dev->name);
    return NULL;
  }
  return dev;
}

// sensor fetch [device]: turn the LED on through sensor_sample_fetch()
static int cmd_fetch(const struct shell *sh, size_t argc, char **argv) {
  const struct device *dev = custom_led_ready_from_args(sh, argc, argv);
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
  const struct device *dev = custom_led_ready_from_args(sh, argc, argv);
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
  const struct device *dev = custom_led_from_args(sh, argc, argv);
  if (dev == NULL) {
    return -ENODEV;
  }
  shell_print(sh, "name: %s", dev->name);
  shell_print(sh, "ready: %s", device_is_ready(dev) ? "yes" : "no");
  return 0;
}

// Each subcommand takes an optional device name (1 mandatory = the command itself, 1 optional)
SHELL_STATIC_SUBCMD_SET_CREATE(sub_sensor,
  SHELL_CMD_ARG(fetch, NULL, "Turn the LED on (sensor_sample_fetch). Usage: fetch [device]", cmd_fetch, 1, 1),
  SHELL_CMD_ARG(read, NULL, "Read the LED and turn it off (sensor_channel_get). Usage: read [device]", cmd_read, 1, 1),
  SHELL_CMD_ARG(info, NULL, "Print the device name and ready state. Usage: info [device]", cmd_info, 1, 1),
  SHELL_SUBCMD_SET_END
);

SHELL_CMD_REGISTER(sensor, &sub_sensor, "Custom LED sensor commands", NULL);
