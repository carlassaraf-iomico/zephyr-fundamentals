#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>

#include <custom_led/custom_led.h>

// Has to match custom_led.yaml compatible attribute replacing , and - for _
#define DT_DRV_COMPAT course_custom_led

// Custom LED driver configuration populated by GPIO_DT_SPEC_INST_GET at compile time
struct custom_led_config {
  struct gpio_dt_spec led_pin;
};

// Custom LED driver runtime data
struct custom_led_data {
    bool led_on;
};

/**
 * @brief Initialize the custom LED driver
 * @param dev Pointer to the device structure
 * @return 0 on success, negative error code on failure
 */
static int custom_led_init(const struct device *dev) {
  // Get the device configuration
  const struct custom_led_config *config = dev->config;
  // Configure the GPIO pin for the LED
  if (!gpio_is_ready_dt(&config->led_pin)) {
    return -ENODEV;
  }
  return gpio_pin_configure_dt(&config->led_pin, GPIO_OUTPUT_INACTIVE);
}

// API implementations

/**
 * @brief Turn the LED on
 * @param dev Pointer to the device structure
 * @param chan Sensor channel (not used in this driver)
 * @return 0 on success, negative error code on failure
 */
static int custom_led_sample_fetch(const struct device *dev, enum sensor_channel chan) {
  // Get runtime data for the device
  struct custom_led_data *data = dev->data;
  const struct custom_led_config *cfg = dev->config;
  data->led_on = true;
  return gpio_pin_set_dt(&cfg->led_pin, data->led_on);
}

/**
 * @brief Turn the LED off
 * @param dev Pointer to the device structure
 * @param chan Sensor channel (not used in this driver)
 * @param val Pointer to the sensor value structure
 * @return 0 on success, negative error code on failure
 */
static int custom_led_channel_get(const struct device *dev, enum sensor_channel chan, struct sensor_value *val) {
  // Get runtime data for the device
  struct custom_led_data *data = dev->data;
  const struct custom_led_config *cfg = dev->config;
  data->led_on = false;
  return gpio_pin_set_dt(&cfg->led_pin, data->led_on);
}

// Point sensor API to custom implementations
static const struct sensor_driver_api custom_led_api = {
  .sample_fetch = custom_led_sample_fetch,
  .channel_get = custom_led_channel_get,
};

// Create actual device
#define CUSTOM_LED_DEFINE(inst)                                       \
  static struct custom_led_data custom_led_data_##inst;               \
  static const struct custom_led_config custom_led_config_##inst = {  \
    .led_pin = GPIO_DT_SPEC_INST_GET(inst, gpios),                    \
  };                                                                  \
  SENSOR_DEVICE_DT_INST_DEFINE(inst,                                  \
                                custom_led_init, NULL,                \
                                &custom_led_data_##inst,              \
                                &custom_led_config_##inst,            \
                                POST_KERNEL,                          \
                                CONFIG_SENSOR_INIT_PRIORITY,          \
                                &custom_led_api);

// Create a device instance for every node in DTS
DT_INST_FOREACH_STATUS_OKAY(CUSTOM_LED_DEFINE)