#include <zephyr/drivers/gpio.h>

/* Defined in main.cpp. */
extern const struct gpio_dt_spec led;

int blink(void) { return gpio_pin_toggle_dt(&led); }
