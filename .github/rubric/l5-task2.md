# l5-task2: custom board, from scratch

## Task
Create a custom board from scratch and build `samples/hello_world` for it. The board prints
"Board Initialized" before the application's `main()` runs.

## Automatic checks
- Everything in l5-task1, for this board.
- The text "Board Initialized" is in a source file in the board folder (case and punctuation
  don't matter; the British "Initialised" is fine).
- The built `hello_world` image contains the text, so the file is compiled into the build.

## AI checks
- The message is printed before `main()`: from a function registered with `SYS_INIT()` (any
  init level and priority), or from `board_early_init_hook()` / `board_late_init_hook()` with
  `CONFIG_BOARD_EARLY_INIT_HOOK` / `CONFIG_BOARD_LATE_INIT_HOOK` enabled by the board (in
  `Kconfig.<board>`, `Kconfig.defconfig` or `<board>_defconfig`). Printing it from `main()` or from
  application code doesn't count.
- `printk()`, `printf()` and the logging API are all fine.

## Not checked
- That the board was written from scratch. Never compare it with the l5-task1 board; identical
  files are fine.
