/* The unmapped packet must never become a mapped board or a recommendation. */
#include "coach_protocol.h"
#include "xinyi_product.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static int recommend(void *p,uint32_t token,const xq_search_board_t *b)
{assert(token==100 && b->side==0);++*(unsigned *)p;return 1;}
int main(void)
{
    xqcoach_result p={0},out,before;char wire[XQCOACH_PACKET_BYTES];unsigned status=99;
    assert(xqcoach_identity_init(&p.identity,100,20,123));p.status=5;p.count=2;
    p.candidates[0]=(xqcoach_candidate){0,255,255,750,.75f,20,30,60,70};
    p.candidates[1]=(xqcoach_candidate){13,255,255,500,.5f,100,30,140,70};
    memset(&before,0xa5,sizeof(before));out=before;
    size_t n=xqcoach_encode_partial(&p,wire,sizeof(wire));assert(n);
    assert(!xqcoach_encode_result(&p,wire,sizeof(wire)));
    assert(xqcoach_parse_result(wire,n,&p.identity,&out,&status)==XQCOACH_INVALID);
    assert(status==99 && !memcmp(&out,&before,sizeof(out)));
    assert(xqcoach_parse_partial(wire,n,&p.identity,&out)==XQCOACH_ACCEPTED);
    assert(out.status==5 && out.count==2 && out.candidates[0].file==255);
    xqcoach_identity wrong=p.identity;wrong.token++;out=before;
    assert(xqcoach_parse_partial(wire,n,&wrong,&out)==XQCOACH_INVALID && !memcmp(&out,&before,sizeof(out)));
    wire[n-2]^=1;
    assert(xqcoach_parse_partial(wire,n,&p.identity,&out)==XQCOACH_INVALID && !memcmp(&out,&before,sizeof(out)));
    p.candidates[0].file=0;assert(!xqcoach_encode_partial(&p,wire,sizeof(wire)));
    p.candidates[0].file=255;p.status=0;assert(!xqcoach_encode_partial(&p,wire,sizeof(wire)));
    p.status=9;assert(!xqcoach_encode_partial(&p,wire,sizeof(wire)));
    p.status=5;p.count=0;assert(!xqcoach_encode_partial(&p,wire,sizeof(wire)));
    p.count=2;p.estimated=1;p.candidates[0].file=4;p.candidates[0].rank=0;
    for(unsigned i=0;i<4;i++){p.corners[i][0]=i>=2?100:900;p.corners[i][1]=i%2?100:600;}
    n=xqcoach_encode_partial(&p,wire,sizeof(wire));assert(n);
    assert(xqcoach_parse_result(wire,n,&p.identity,&out,&status)==XQCOACH_INVALID);
    assert(xqcoach_parse_partial(wire,n,&p.identity,&out)==XQCOACH_ACCEPTED && out.estimated && out.candidates[1].file==255);
    xy_app a;xy_app_init(&a,NULL);a.page=XY_GAME;a.mode=XY_COACH;a.job=XY_CAPTURE;a.token=100;
    unsigned classes[14]={0};classes[0]=1;classes[13]=1;
    assert(!xy_capture_partial(&a,101,classes,2,1000));
    assert(xy_capture_partial(&a,100,classes,2,1000));
    assert(a.job==XY_IDLE && a.geometry_failed && a.partial_count==2 && !a.current_photo_valid && !a.has_recommendation && !a.has_board);
    assert(a.partial_classes[0]==1 && a.partial_classes[13]==1 && a.photo_latency_ms==1000);
    unsigned calls=0;xy_backend backend={0};backend.context=&calls;backend.recommend=recommend;
    xy_app_init(&a,&backend);a.page=XY_GAME;a.mode=XY_COACH;a.job=XY_CAPTURE;a.token=100;
    xy_scored_detection pieces[]={{0,4,0,750,.75f},{7,4,9,750,.75f},{6,4,3,750,.75f},{2,4,7,750,.75f}};
    assert(xy_capture_estimated(&a,100,pieces,4,1000));
    assert(a.estimated_position && a.current_photo_valid && a.has_board && a.job==XY_RECOMMEND && calls==1);
    assert(a.photo.removed_count==1 && !a.photo.board.squares[67] && a.photo.reason==XY_POSITION_VALID);
    puts("XQCOACH_UNMAPPED_PARTIAL_IDENTITY_CRC_NO_BOARD_NO_RECOMMEND_PASS");return 0;
}
