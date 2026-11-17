#include <zephyr/kernel.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

int main(void) {

    const struct device *ledr = DEVICE_DT_GET(DT_ALIAS(ledr));
    const struct device *ledg = DEVICE_DT_GET(DT_ALIAS(ledg));
    const struct device *ledb = DEVICE_DT_GET(DT_ALIAS(ledb));

    if (!device_is_ready(ledr) || !device_is_ready(ledg) || !device_is_ready(ledb)) {
        LOG_ERR("Custom LED device not ready");
        return 0;
    }

    struct sensor_value val;
    while (1) {
        sensor_sample_fetch(ledb);
        k_msleep(CONFIG_BLINKY_SLEEP_MS);
        sensor_channel_get(ledb, SENSOR_CHAN_ALL, &val);
        k_msleep(CONFIG_BLINKY_SLEEP_MS);
    }
    return 0;
}