#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "xq_grid.h"
int main(void)
{
    static const char opening[]="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
    const double corners[4][2]={{180,630},{1040,590},{990,70},{240,100}};
    const double bad[4][2]={{0,0},{0,0},{0,0},{0,0}};
    xqg_grid truth={ {0},0 }, fitted={ {0},0 };
    xqg_detection d[32], saved;
    xq_search_board_t b,checked;
    xqv_result r,mapped;
    unsigned i;
    assert(xqv_parse_fen(opening,&b));
    xqv_board_result(&b,7,900,&r);
    xqg_stub_geometry(&r,d);
    assert(xqg_corners(&truth,corners));
    for (i=0; i<32; ++i) {
        assert(xqg_project(&truth,r.pieces[i].file,r.pieces[i].rank,&d[i].x,&d[i].y));
        d[i].x+=(int)(i%3)-1; d[i].y+=(int)(i%5)-2;
    }
    assert(xqg_fit(&fitted,d,32,&b,7));
    assert(xqg_map(&fitted,d,32,7,&mapped));
    assert(xqv_result_board(&mapped,7,&checked));
    assert(!memcmp(b.squares,checked.squares,90));
    assert(!xqg_fit(&fitted,d,31,&b,7));
    saved=d[0]; d[0].x=1279; d[0].y=719;
    assert(!xqg_fit(&fitted,d,32,&b,7)); d[0]=saved;
    d[0].class_id=6;
    assert(!xqg_fit(&fitted,d,32,&b,7)); d[0]=saved;
    assert(!xqg_corners(&truth,bad));
    /* A 180 degree camera orientation still maps to red a0 correctly. */
    for (i=0; i<32; ++i) { d[i].x=1279-d[i].x; d[i].y=719-d[i].y; }
    fitted.valid=0;
    assert(xqg_fit(&fitted,d,32,&b,7));
    puts("XQ_GRID_TEST_PASS perspective jitter rotated missing outlier wrong-class degenerate");
    return 0;
}
