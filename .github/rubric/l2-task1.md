# l2-task1: workspace and blinky

## Task
Fork `iomico-public/zephyr-course`, set up the west workspace, and build, flash and run the blinky
app in `app/`. The LED toggles every second. Name the board in `board.txt` at the repository root.

## Automatic checks
- `app/CMakeLists.txt` and `west.yml` are at the repository root. The root is not a copy of the
  Zephyr tree and not the west workspace around the repository.
- `board.txt` names one board target that Zephyr knows, with the CPU when the board has several
  (`esp32_devkitc/esp32/procpu`). `native_sim` is fine without hardware.
- The app builds for that board.
- Notes only: the code toggles no LED (a board may have none), or waits something other than
  1000 ms between toggles.

## Not checked
- Flashing, and the LED blinking on the board.
