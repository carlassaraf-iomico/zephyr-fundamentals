# l3-task1: Kconfig menu

## Task
Reproduce the "LED Subsystem" menu in `app/Kconfig`: a `menuconfig` top-level toggle, a `choice`
for the blink sleep time (250 ms, 500 ms, 1 s, 2 s) with a hidden `int` that follows it, a
`menuconfig` for Advanced LED settings with brightness (`range 0 100`, default 100) and fade
duration (`range 0 5000`, default 500), and an Expert settings `menu` with `visible if` holding
two `bool` options.

## Automatic checks
- Every rule above, by parsing the Kconfig with kconfiglib: the menu tree, the 4 choice options,
  the hidden int's value for each option, both ranges, and Expert settings hidden while Advanced
  LED settings is off.
