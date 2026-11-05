# l5-task1: custom board, copy/rename

## Task
Create a custom board by copying and renaming an existing board, place it in `boards/` at the
repository root, and build `samples/hello_world` for it.

## Automatic checks
- A board folder with `board.yml`, a `.dts`, `Kconfig.<board>` and `<board>_defconfig`, named
  after the board in `board.yml`. Each missing or misnamed file is one change.
- Zephyr can find the board: `boards/` at the root, `app/boards/`, or a folder added to
  `BOARD_ROOT` (in `app/CMakeLists.txt` before `find_package(Zephyr)`, or in `zephyr/module.yml`).
- The board's name doesn't clash with a Zephyr board.
- `samples/hello_world` builds for the board.

## Not checked
- Which method was used to create the board.
