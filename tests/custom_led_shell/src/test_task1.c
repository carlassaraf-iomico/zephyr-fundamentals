/*
 * l7-task1: the `sensor` shell command (fetch, read, info), run through the shell's
 * dummy backend. The LED is pin 5 of an emulated GPIO controller (app.overlay).
 */
#include <ctype.h>
#include <string.h>
#include <zephyr/ztest.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/gpio/gpio_emul.h>
#include <zephyr/shell/shell.h>
#include <zephyr/shell/shell_dummy.h>

#define LED_NODE DT_NODELABEL(custom_led)

static const struct device *const dev = DEVICE_DT_GET(LED_NODE);
static const struct gpio_dt_spec pin = GPIO_DT_SPEC_GET(LED_NODE, gpios);

int led_level(void)
{
	return gpio_emul_output_get(pin.port, pin.pin);
}

/* The dummy backend records line breaks even when a command prints nothing. */
static bool has_text(const char *out)
{
	for (; *out; out++) {
		if (isalnum((unsigned char)*out)) {
			return true;
		}
	}
	return false;
}

/* Runs a shell command; returns its result and leaves its output in *out. */
int run(const char *cmd, const char **out)
{
	const struct shell *sh = shell_backend_dummy_get_ptr();
	size_t size;
	int ret;

	shell_backend_dummy_clear_output(sh);
	ret = shell_execute_cmd(sh, cmd);
	*out = shell_backend_dummy_get_output(sh, &size);
	return ret;
}

ZTEST(custom_led_shell, test_fetch_turns_led_on)
{
	const char *out;

	zassert_ok(run("sensor read", &out));
	zassert_ok(run("sensor fetch", &out), "`sensor fetch` failed");
	zassert_equal(led_level(), 1, "the LED is off after `sensor fetch`");
}

ZTEST(custom_led_shell, test_read_turns_led_off_and_prints)
{
	const char *out;

	zassert_ok(run("sensor fetch", &out));
	zassert_ok(run("sensor read", &out), "`sensor read` failed");
	zassert_equal(led_level(), 0, "the LED is on after `sensor read`");
	zassert_true(has_text(out), "`sensor read` prints nothing");
}

ZTEST(custom_led_shell, test_info_prints_name_and_ready)
{
	const char *out;

	zassert_ok(run("sensor info", &out), "`sensor info` failed");
	zassert_not_null(strstr(out, dev->name), "`sensor info` doesn't print the device name (%s)", dev->name);
	zassert_not_null(strstr(out, "ready"), "`sensor info` doesn't print the ready state");
}

static void *setup(void)
{
	k_usleep(10); /* let the shell backend start */
	return NULL;
}

ZTEST_SUITE(custom_led_shell, NULL, setup, NULL, NULL, NULL);
