# l8-task1: ring_buf tests

## Task
Fill in the 7 stub ZTEST bodies in `tests/ring_buf/src/test_ring_buf.c` and make all 8 tests
pass with `west twister -T tests/ring_buf -p native_sim`.

## Automatic checks
- The file at the repository root has no stub skips left, and every stub test has `zassert_*`
  assertions.
- All 8 tests pass under twister on `native_sim`.
