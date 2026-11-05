# l4-task1: heartbeat LED

## Task
Add a configurable heartbeat LED to the blinky app:
1. `app/app.overlay` adds the alias `app-led` pointing at the board's LED.
2. `app/Kconfig` adds `int APP_HEARTBEAT_PERIOD_MS` with `default 500` and `range 100 2000`.
3. The C code gets the GPIO from `DT_ALIAS(app_led)` and sleeps for
   `CONFIG_APP_HEARTBEAT_PERIOD_MS`.

## Automatic checks
- `APP_HEARTBEAT_PERIOD_MS` is an `int` with `default 500` and `range 100 2000`.
- The app builds for the board in `board.txt`, and the built devicetree has an `app-led` alias
  pointing at a GPIO node. The overlay must be `app/app.overlay` or `app/boards/<board>.overlay`.
- A build with `CONFIG_APP_HEARTBEAT_PERIOD_MS=200` succeeds.
- `main.c` / `main.cpp` uses `DT_ALIAS(app_led)` and `CONFIG_APP_HEARTBEAT_PERIOD_MS`.

## AI checks
- The period sets the time between LED toggles: `CONFIG_APP_HEARTBEAT_PERIOD_MS` reaches the
  sleep call (directly, through a variable or constant, or through `K_MSEC()`), not only a log
  message. Toggling once per period or turning on and off within each period are both fine.
- The LED that is toggled is the one from the alias: the `gpio_dt_spec` (or device and pin) used
  by the toggle comes from `DT_ALIAS(app_led)`, not from `led0` or a hard-coded pin.
- A board without an LED may add its own node in the overlay and point `app-led` at it.

## Not checked
- The blink speed on the board, and changing the period in `menuconfig`.
