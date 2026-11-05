# l6-task2: extension API

## Task
Add a custom extension API function to the l6-task1 driver and call it from `main.c`. The
function changes a parameter of the student's choice in the driver's dynamic data struct.

## Automatic checks
None yet: the AI judges every rule below.

## AI checks
- The function is declared in a header the app includes (for example
  `include/drivers/sensor/<name>.h` or next to the driver) and defined in the driver.
- The app calls it, from `app/src/main.c` or `main.cpp`, with the driver's device.
- It changes a field of the driver's data struct through the device (`dev->data`), not a global
  or static variable. A syscall-style wrapper (`__syscall` plus `z_impl_...`) or a plain function
  are both fine.
- The rest of the l6-task1 driver still works: the sensor API struct is unchanged in spirit.
