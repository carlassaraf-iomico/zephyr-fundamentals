/*
 * Ring Buffer Module - Homework Test Skeleton
 *
 * test_fresh_state is provided as a worked example; the remaining 7 ZTEST
 * bodies implement TEST_SPEC.md.
 *
 * Run:
 *   west twister -T tests/ring_buf -p native_sim
 */

#include <zephyr/ztest.h>
#include <errno.h>

#include "ring_buf.h"

/*
 * Shared before hook: every suite reinitialises the ring buffer with a
 * capacity of 4 so tests start from a clean, known state. Capacity 4 is
 * enough to exercise FIFO order (push 1, 2, 3) and overflow (full at 4).
 */
static void before(void *f)
{
	ARG_UNUSED(f);
	rb_init(4);
}

/*
 * ============================================================================
 * Test Suite: ring_buf_init
 *
 * Initial state and re-initialization behaviour.
 * ============================================================================
 */
ZTEST_SUITE(ring_buf_init, NULL, NULL, before, NULL, NULL);

/* PROVIDED — study this test before writing the rest. */
ZTEST(ring_buf_init, test_fresh_state)
{
	zassert_true(rb_is_empty(), "Fresh buffer must be empty");
	zassert_equal(rb_count(), 0, "Fresh buffer count must be 0");
}

ZTEST(ring_buf_init, test_reinit_clears_state)
{
	zassert_ok(rb_push(99), "push(99) must succeed on an empty buffer");

	zassert_ok(rb_init(4), "rb_init(4) must succeed");

	zassert_true(rb_is_empty(), "Buffer must be empty after reinit");
	zassert_equal(rb_count(), 0, "Count must be 0 after reinit");
}

/*
 * ============================================================================
 * Test Suite: ring_buf_push_pop
 *
 * Single push/pop round-trip, FIFO order, full error path.
 * ============================================================================
 */
ZTEST_SUITE(ring_buf_push_pop, NULL, NULL, before, NULL, NULL);

ZTEST(ring_buf_push_pop, test_single_push_pop)
{
	int v = 0;

	zassert_ok(rb_push(42), "push(42) must return 0");
	zassert_ok(rb_pop(&v), "pop(&v) must return 0");
	zassert_equal(v, 42, "Popped value must be 42, got %d", v);
	zassert_true(rb_is_empty(), "Buffer must be empty after popping its only value");
}

ZTEST(ring_buf_push_pop, test_fifo_order)
{
	int v = 0;

	zassert_ok(rb_push(1), "push(1) must return 0");
	zassert_ok(rb_push(2), "push(2) must return 0");
	zassert_ok(rb_push(3), "push(3) must return 0");

	zassert_ok(rb_pop(&v), "First pop must return 0");
	zassert_equal(v, 1, "First pop must yield 1, got %d", v);
	zassert_ok(rb_pop(&v), "Second pop must return 0");
	zassert_equal(v, 2, "Second pop must yield 2, got %d", v);
	zassert_ok(rb_pop(&v), "Third pop must return 0");
	zassert_equal(v, 3, "Third pop must yield 3, got %d", v);

	zassert_true(rb_is_empty(), "Buffer must be empty after three pops");
}

ZTEST(ring_buf_push_pop, test_push_full_returns_enospc)
{
	for (int i = 1; i <= 4; i++) {
		zassert_ok(rb_push(i), "push(%d) must return 0", i);
	}
	zassert_true(rb_is_full(), "Buffer must be full after 4 pushes");

	zassert_equal(rb_push(99), -ENOSPC, "push(99) on a full buffer must return -ENOSPC");
	zassert_equal(rb_count(), 4, "A rejected push must not change the count");
}

/*
 * ============================================================================
 * Test Suite: ring_buf_boundaries
 *
 * Peek semantics and NULL-pointer boundary conditions.
 * ============================================================================
 */
ZTEST_SUITE(ring_buf_boundaries, NULL, NULL, before, NULL, NULL);

ZTEST(ring_buf_boundaries, test_peek_does_not_consume)
{
	int v = 0;

	zassert_ok(rb_push(7), "push(7) must return 0");

	zassert_ok(rb_peek(&v), "First peek must return 0");
	zassert_equal(v, 7, "First peek must yield 7, got %d", v);

	v = 0;
	zassert_ok(rb_peek(&v), "Second peek must return 0");
	zassert_equal(v, 7, "Second peek must yield 7, got %d", v);

	zassert_equal(rb_count(), 1, "Peek must not consume: count must still be 1");
}

ZTEST(ring_buf_boundaries, test_pop_null_returns_einval)
{
	zassert_equal(rb_pop(NULL), -EINVAL, "rb_pop(NULL) must return -EINVAL");
}

ZTEST(ring_buf_boundaries, test_is_full_after_fill)
{
	for (int i = 1; i <= 4; i++) {
		zassert_ok(rb_push(i), "push(%d) must return 0", i);
	}

	zassert_true(rb_is_full(), "Buffer must be full after 4 pushes");
	zassert_equal(rb_count(), 4, "Count must be 4 after 4 pushes");
}
