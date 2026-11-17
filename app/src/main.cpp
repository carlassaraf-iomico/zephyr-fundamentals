#include <zephyr/kernel.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>

#include <custom_led/custom_led.h>

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

int main(void) {
    const struct device *ledr = DEVICE_DT_GET(DT_ALIAS(ledr));
    const struct device *ledg = DEVICE_DT_GET(DT_ALIAS(ledg));
    const struct device *ledb = DEVICE_DT_GET(DT_ALIAS(ledb));

    if (!device_is_ready(ledr) || !device_is_ready(ledg) || !device_is_ready(ledb)) {
        LOG_ERR("Custom LED device not ready");
        return 0;
    }

    custom_led_set_name(ledr, "red");
    custom_led_set_name(ledg, "green");
    custom_led_set_name(ledb, "blue");
    LOG_INF("LED names set via custom extension API");

    // Log them
    char name[32] = "";
    custom_led_get_name(ledr, name);
    LOG_INF("ledr name is %s", name);

    custom_led_get_name(ledg, name);
    LOG_INF("ledg name is %s", name);

    custom_led_get_name(ledb, name);
    LOG_INF("ledb name is %s", name);

    // One blink period is a full on + off cycle: CONFIG_BLINKY_SLEEP_MS on, then off
    int ret = custom_led_set_period(ledb, 2 * CONFIG_BLINKY_SLEEP_MS);
    if (ret < 0) {
        LOG_ERR("Failed to set ledb blink period (%d)", ret);
        return 0;
    }
    LOG_INF("ledb blink period is %u ms", custom_led_get_period(ledb));

    struct sensor_value val;
    while (1) {
        // Read the period every cycle so a change (e.g. from the shell) applies right away
        uint32_t half_period_ms = custom_led_get_period(ledb) / 2;
        sensor_sample_fetch(ledb);
        k_msleep(half_period_ms);
        sensor_channel_get(ledb, SENSOR_CHAN_ALL, &val);
        k_msleep(half_period_ms);
    }
    return 0;
}