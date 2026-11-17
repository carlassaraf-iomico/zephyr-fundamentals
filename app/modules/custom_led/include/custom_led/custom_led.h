#ifndef DRIVER_CUSTOM_LED_H
#define DRIVER_CUSTOM_LED_H

#include <stdint.h>
#include <zephyr/drivers/sensor.h>

// Blink period a device starts with, before custom_led_set_period() is called
#define CUSTOM_LED_DEFAULT_PERIOD_MS 1000U

// Extended API types
typedef int (*custom_led_set_name_t)(const struct device *dev, const char *name);
typedef int (*custom_led_get_name_t)(const struct device *dev, char *name);
typedef int (*custom_led_set_period_t)(const struct device *dev, uint32_t period_ms);
typedef uint32_t (*custom_led_get_period_t)(const struct device *dev);

// Sensor API implementation + extended API
struct custom_led_driver_api {
  struct sensor_driver_api sensor;
  custom_led_set_name_t set_name;
  custom_led_get_name_t get_name;
  custom_led_set_period_t set_period;
  custom_led_get_period_t get_period;
};

// Expose custom implementations

static inline int custom_led_set_name(const struct device *dev, const char *name) {
  const struct custom_led_driver_api *api = (const struct custom_led_driver_api *)dev->api;
  return api->set_name(dev, name);
}

static inline int custom_led_get_name(const struct device *dev, char *name) {
  const struct custom_led_driver_api *api = (const struct custom_led_driver_api *)dev->api;
  return api->get_name(dev, name);
}

/**
 * @brief Set the LED's blink period (one full on + off cycle)
 * @param dev Pointer to the device structure
 * @param period_ms Blink period in milliseconds, must be greater than 0
 * @return 0 on success, -EINVAL if period_ms is 0
 */
static inline int custom_led_set_period(const struct device *dev, uint32_t period_ms) {
  const struct custom_led_driver_api *api = (const struct custom_led_driver_api *)dev->api;
  return api->set_period(dev, period_ms);
}

/**
 * @brief Get the LED's blink period
 * @param dev Pointer to the device structure
 * @return Blink period in milliseconds
 */
static inline uint32_t custom_led_get_period(const struct device *dev) {
  const struct custom_led_driver_api *api = (const struct custom_led_driver_api *)dev->api;
  return api->get_period(dev);
}

#endif