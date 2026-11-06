/*
 * l6-task1: the LED sensor driver. sensor_sample_fetch() turns the LED on and
 * sensor_channel_get() turns it off. The LED is pin 5 of an emulated GPIO controller
 * (app.overlay), so the test reads the pin the driver drives.
 */
#include <zephyr/ztest.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/gpio/gpio_emul.h>

#define LED_NODE DT_NODELABEL(custom_led)

static const struct device *const dev = DEVICE_DT_GET(LED_NODE);
static const struct gpio_dt_spec pin = GPIO_DT_SPEC_GET(LED_NODE, gpios);

static int led_level(void)
{
	return gpio_emul_output_get(pin.port, pin.pin);
}

static void fetch(void)
{
	zassert_ok(sensor_sample_fetch(dev), "sensor_sample_fetch() failed");
}

static void channel_get(void)
{
	struct sensor_value val;

	zassert_ok(sensor_channel_get(dev, SENSOR_CHAN_ALL, &val), "sensor_channel_get() failed");
}

ZTEST(custom_led, test_device_ready)
{
	zassert_true(device_is_ready(dev), "the course,custom-led device is not ready");
}

ZTEST(custom_led, test_fetch_turns_led_on)
{
	channel_get();
	fetch();
	zassert_equal(led_level(), 1, "the LED is off after sensor_sample_fetch()");
}

ZTEST(custom_led, test_fetch_twice_keeps_led_on)
{
	/* A toggle gives different levels on two calls in a row, whatever the start. */
	fetch();
	zassert_equal(led_level(), 1, "the LED is off after sensor_sample_fetch()");
	fetch();
	zassert_equal(led_level(), 1, "the LED is off after a second sensor_sample_fetch() (a toggle?)");
}

ZTEST(custom_led, test_channel_get_turns_led_off)
{
	fetch();
	channel_get();
	zassert_equal(led_level(), 0, "the LED is on after sensor_channel_get()");
}

ZTEST(custom_led, test_channel_get_twice_keeps_led_off)
{
	channel_get();
	zassert_equal(led_level(), 0, "the LED is on after sensor_channel_get()");
	channel_get();
	zassert_equal(led_level(), 0, "the LED is on after a second sensor_channel_get() (a toggle?)");
}

ZTEST_SUITE(custom_led, NULL, NULL, NULL, NULL, NULL);
