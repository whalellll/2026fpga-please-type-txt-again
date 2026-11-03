/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef PG2L_TIMER_BRIDGE_H
#define PG2L_TIMER_BRIDGE_H

/* Generated per frozen clock configuration. TIME is CPU cycles; MTIME is
 * SYS cycles. Keep the reduced, exact PLL ratio, including fractional MHz. */
#if !defined(PG2L_TIME_NUMERATOR) || !defined(PG2L_TIME_DENOMINATOR)
#error "Generate the PG2L clock ratio before building OpenSBI"
#endif
#if PG2L_TIME_NUMERATOR < 1 || PG2L_TIME_DENOMINATOR < PG2L_TIME_NUMERATOR
#error "This bridge requires CPU frequency >= SYS frequency"
#endif

static inline u64 pg2l_timer_deadline(u64 event, u64 now_time, u64 now_mtime)
{
	u64 remaining, delta;
	const u64 maximum = (u64)-1;
	if (event == maximum)
		return maximum;
	remaining = event > now_time ? event - now_time : 0;
	/* Divide before multiplying to avoid overflow for distant deadlines. */
	delta = (remaining / PG2L_TIME_DENOMINATOR) * PG2L_TIME_NUMERATOR +
		(remaining % PG2L_TIME_DENOMINATOR) * PG2L_TIME_NUMERATOR /
		PG2L_TIME_DENOMINATOR;
	if (!delta)
		delta = 1;
	/* Never wrap a future physical deadline into the past. */
	if (delta >= maximum - now_mtime)
		return maximum;
	return now_mtime + delta;
}
#endif
