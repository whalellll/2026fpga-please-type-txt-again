#ifndef TEST_V321_MOCK_H
#define TEST_V321_MOCK_H
#include "xq_mac.h"
/* Host/QEMU numerical transport only. This is never a hardware fallback. */
typedef struct {
    uint64_t attempts,jobs,cycles,fail_at;
    unsigned errors,unexpected;
} v321_mock_counts;
int v321_mock_open(xqm_linux *);
void v321_mock_close(xqm_linux *);
void v321_mock_reset(uint64_t fail_at);
void v321_mock_read(v321_mock_counts *);
#endif
