#include <assert.h>
#include <stdio.h>
#include "xq_picture.h"
#define SPACE 0x0020002cu
int main(void)
{
    xqp_hid h;
    xqp_hid_init(&h, 100, 0);
    assert(!xqp_hid_poll(&h, 101, SPACE, 10));
    assert(!xqp_hid_poll(&h, 102, SPACE, 50));
    assert(!xqp_hid_poll(&h, 102, SPACE, 299));
    assert(xqp_hid_poll(&h, 102, SPACE, 300) == 1);
    assert(h.first_ms == 10);
    assert(!xqp_hid_poll(&h, 102, SPACE, 600));
    assert(!xqp_hid_poll(&h, 103, SPACE, 800));
    assert(!xqp_hid_poll(&h, 103, SPACE, 1300)); /* held: no false photo */
    assert(!xqp_hid_poll(&h, 104, SPACE, 1500));
    assert(xqp_hid_poll(&h, 104, SPACE, 1750) == 1);
    assert(!xqp_hid_poll(&h, 105, SPACE, 2000));
    assert(xqp_hid_poll(&h, 105, SPACE, 4000) == -1); /* missing release */
    assert(!xqp_hid_poll(&h, 105, SPACE, 5000));
    assert(xqp_hid_poll(&h, 109, SPACE, 5100) == -1); /* burst, no queue */
    xqp_hid_init(&h, 0xffffffffu, 6000);
    assert(!xqp_hid_poll(&h, 0, SPACE, 6010));
    assert(!xqp_hid_poll(&h, 1, SPACE, 6020));
    assert(xqp_hid_poll(&h, 1, SPACE, 6270) == 1);
    xqp_hid_init(&h, 10, 7000); /* busy work drops all old reports */
    assert(!xqp_hid_poll(&h, 10, SPACE, 8000));
    assert(!xqp_hid_poll(&h, 11, 0x00610004u, 8100));
    assert(!xqp_hid_poll(&h, 12, 0x00610004u, 8200));
    assert(!xqp_hid_poll(&h, 12, 0x00610004u, 8500));
    xqp_hid_init(&h,0,0);
    assert(!xqp_hid_poll_key(&h,2,0x00720015u,10));
    assert(xqp_hid_poll_key(&h,2,0x00720015u,260)=='r');
    assert(!xqp_hid_poll_key(&h,4,0x00430206u,300)); /* Shift+C */
    assert(xqp_hid_poll_key(&h,4,0x00430206u,550)=='c');
    assert(!xqp_hid_poll_key(&h,6,0x001b0029u,600));
    assert(xqp_hid_poll_key(&h,6,0x001b0029u,850)==27);
    assert(!xqp_hid_poll_key(&h,7,SPACE,900));
    assert(xqp_hid_poll_key(&h,8,0x00720015u,950)==-1); /* mixed keys */
    assert(!xqp_hid_poll_key(&h,10,0x00720415u,1000)); /* Ctrl+R rejected */
    assert(!xqp_hid_poll_key(&h,11,SPACE,1200));
    assert(xqp_hid_poll_key(&h,12,SPACE,3400)==-1); /* late release */
    puts("XQ_PICTURE_HID_TEST_PASS report-pair quiet-window packed-ASCII wrap busy-discard");
    return 0;
}
