/* l7-task2: `sensor set <ms>` passes a valid period to the extension API and rejects the rest. */
#include <zephyr/ztest.h>
#include <custom_led/custom_led.h>

static const struct device *const dev = DEVICE_DT_GET(DT_NODELABEL(custom_led));

int run(const char *cmd, const char **out);

ZTEST(custom_led_set, test_set_valid_period)
{
	const char *out;

	zassert_ok(run("sensor set 250", &out), "`sensor set 250` failed");
	zassert_equal(custom_led_get_period(dev), 250, "`sensor set 250` didn't set the period to 250");
}

ZTEST(custom_led_set, test_set_rejects_missing_value)
{
	const char *out;

	zassert_not_equal(run("sensor set", &out), 0, "`sensor set` with no value succeeds");
}

ZTEST(custom_led_set, test_set_rejects_out_of_range)
{
	const char *out;

	zassert_ok(run("sensor set 300", &out));
	zassert_not_equal(run("sensor set 99", &out), 0, "`sensor set 99` (below 100) succeeds");
	zassert_not_equal(run("sensor set 5001", &out), 0, "`sensor set 5001` (above 5000) succeeds");
	zassert_equal(custom_led_get_period(dev), 300, "a rejected value changed the period");
}

ZTEST(custom_led_set, test_set_rejects_non_number)
{
	const char *out;

	zassert_not_equal(run("sensor set abc", &out), 0, "`sensor set abc` succeeds");
}

ZTEST_SUITE(custom_led_set, NULL, NULL, NULL, NULL, NULL);
