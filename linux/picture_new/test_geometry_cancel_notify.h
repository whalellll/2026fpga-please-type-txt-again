#ifndef XQGC_TEST_NOTIFY_H
#define XQGC_TEST_NOTIFY_H
#include <stddef.h>
void xqgc_test_note(unsigned,size_t);
#define XQGC_NOTE(phase,index) xqgc_test_note(phase,index)
#endif
