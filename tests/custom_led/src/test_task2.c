/* l6-task2: the extension API stores the blink period in the driver's data. */
#include <zephyr/ztest.h>
#include <custom_led/custom_led.h>

static const struct device *const dev = DEVICE_DT_GET(DT_NODELABEL(custom_led));

ZTEST(custom_led_period, test_set_then_get_period)
{
	zassert_ok(custom_led_set_period(dev, 250), "custom_led_set_period(dev, 250) failed");
	zassert_equal(custom_led_get_period(dev), 250, "custom_led_get_period() doesn't return 250");
	zassert_ok(custom_led_set_period(dev, 1000), "custom_led_set_period(dev, 1000) failed");
	zassert_equal(custom_led_get_period(dev), 1000, "custom_led_get_period() doesn't return 1000");
}

ZTEST_SUITE(custom_led_period, NULL, NULL, NULL, NULL, NULL);
