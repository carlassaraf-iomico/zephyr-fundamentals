# l6-task2: extension API

## Task
Add a custom extension API function to the l6-task1 driver and call it from `main.c`. The
function changes a parameter of the student's choice in the driver's dynamic data struct.

## Automatic checks
`.github/scripts/check_l6_l7.py --task l6-task2`.
- The driver offers a function besides the sensor API that takes the device: a plain function,
  a `__syscall` (`z_impl_...`), a header wrapper calling `api->member(dev, ...)`, or a member of
  an extended API struct.
- The app calls it.
- It is declared in a header the app includes, not in the app's source.
- It changes a field of the driver's data struct through the device (`dev->data`), not a global
  or static variable.
- The driver still has a sensor API struct. (l6-task1 judges `.sample_fetch` / `.channel_get`.)
- The app builds for the board in `board.txt`, and the driver is compiled into it.

## Decided by an instructor
- What the function changes, when the script can't follow it (it calls further functions, or
  writes through a pointer it got elsewhere).

## Not checked
- The parameter's effect on the hardware.
