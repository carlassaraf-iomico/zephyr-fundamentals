/*
 * Ring buffer Module - Public API
 *
 * Note on naming: Zephyr's kernel provides its own `ring_buf_*` API in <zephyr/sys/ring_buffer.h>.
 * To avoid symbol collisions, this module uses an `rb_` prefix for its public API.
 */

#ifndef RING_BUF_H
#define RING_BUF_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RING_BUF_MAX_CAPACITY 16U

/**
 * Initialise the ring buffer with the given capacity.
 *
 * @param capacity  Number of elements the buffer can hold [1, RING_BUF_MAX_CAPACITY].
 * @return 0 on success, -EINVAL if capacity is 0 or > RING_BUF_MAX_CAPACITY.
 */
int rb_init(uint32_t capacity);

/**
 * Push a value onto the back of the buffer.
 *
 * @return 0 on success, -ENOSPC if the buffer is full.
 */
int rb_push(int value);

/**
 * Pop the oldest value from the front of the buffer.
 *
 * @param value  Output pointer; must not be NULL.
 * @return 0 on success, -EINVAL if value is NULL, -ENODATA if the buffer is empty.
 */
int rb_pop(int *value);

/**
 * Peek at the oldest value without consuming it.
 *
 * @param value  Output pointer; must not be NULL.
 * @return 0 on success, -EINVAL if value is NULL, -ENODATA if the buffer is empty.
 */
int rb_peek(int *value);

/** Returns true if the buffer has no room for more elements. */
bool rb_is_full(void);

/** Returns true if the buffer contains no elements. */
bool rb_is_empty(void);

/** Returns the number of elements currently in the buffer. */
uint32_t rb_count(void);

#ifdef __cplusplus
}
#endif

#endif /* RING_BUF_H */
