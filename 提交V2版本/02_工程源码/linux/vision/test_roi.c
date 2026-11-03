#include "xq_roi.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
    xqr_roi roi={0,0,1280,720};
    xqr_letterbox plan;
    xqr_box in[34]={{10,20,30,40,.9f,0},{10,20,30,40,.8f,0},{10,20,30,40,.7f,1}};
    xqr_box out[300],work[300];
    float prob[45]={0};
    unsigned n,i,count,outside;
    double c[4][2]={{200,650},{1000,650},{1000,50},{200,50}};
    xqr_manual manual;
    xqv_result result;
    xq_search_board_t board,actual;
    const char *opening="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
    assert(xqr_letterbox_plan((xqr_roi){490,40,1200,719},640,&plan));
    assert(plan.width==640 && plan.height==612 && plan.top==14 && plan.left==0);
    assert(xqr_letterbox_plan(roi,416,&plan));
    assert(plan.width==416 && plan.height==234 && plan.top==91 && plan.left==0);
    assert(xqr_letterbox_plan((xqr_roi){0,0,31,20},320,&plan));
    assert(plan.width==31 && plan.height==20 && plan.left==144 && plan.pad_x==144.5);
    assert(!xqr_letterbox_plan(roi,192,&plan) && !xqr_roi_valid((xqr_roi){0,0,1281,720}));
    assert(xqr_nms(in,3,.001f,.6f,300,work,300,out,&n) && n==2 && out[1].class_id==1);
    assert(!xqr_nms(in,3,.001f,.6f,300,work,2,out,&n) && n==0);
    assert(!xqr_nms(in,3,.001f,.6f,300,in,34,out,&n) && n==0);
    prob[2]=1;prob[15+14]=1;prob[30+1]=1;
    assert(xqr_fuse(in,prob,3,out,&n) && n==2 && out[0].class_id==2 && out[1].class_id==1);
    prob[15]=NAN;
    assert(!xqr_fuse(in,prob,3,out,&n) && n==0);
    assert(xqr_fuse(NULL,NULL,0,out,&n) && n==0);
    assert(xqr_manual_init(&manual,roi,c,17));
    assert(xqv_parse_fen(opening,&board));
    count=0;
    for(i=0;i<90;i++)if(board.squares[i]) {
        double x,y;
        unsigned piece=board.squares[i];
        assert(xqg_project(&manual.grid,i%9,i/9,&x,&y));
        in[count++]=(xqr_box){(float)x-4,(float)y-4,(float)x+4,(float)y+4,.9f,
            (piece&7u)-1u+((piece&SIDE_BLACK)?7u:0u)};
    }
    assert(count==32);
    in[32]=(xqr_box){150,600,160,610,.99f,4};
    assert(xqr_map(&manual,17,in,33,51,.05f,&result,&outside));
    assert(outside==1 && result.piece_count==32 && !result.is_stub && result.frame_id==51);
    assert(xqv_result_board(&result,51,&actual) && !memcmp(board.squares,actual.squares,90));
    assert(!xqr_map(&manual,18,in,32,52,.05f,&result,&outside) && !result.abi_version);
    in[32]=in[0];
    assert(!xqr_map(&manual,17,in,33,53,.05f,&result,&outside) && !result.abi_version);
    in[1]=in[0];
    assert(!xqr_map(&manual,17,in,32,54,.05f,&result,&outside) && !result.abi_version);
    {
        uint32_t *pixels=calloc(XQV_FRAME_BYTES,1),*rectified=malloc(320u*360u*2u);
        uint8_t *rgb=malloc(1280u*720u*3u);
        xqv_frame frame={pixels,XQV_FRAME_BYTES,55,0};
        unsigned at[4]={650*1280+200,650*1280+1000,50*1280+1000,50*1280+200};
        uint16_t colors[4]={0xf800,0x07e0,0x001f,0xffff};
        assert(pixels && rectified && rgb);
        for(i=0;i<4;i++)pixels[at[i]/2]=colors[i];
        assert(xqr_rectify(&manual,&frame,rectified,320,360,320u*360u*2u));
        assert((rectified[0]&65535)==0xffff && (rectified[159]>>16)==0x001f);
        assert((rectified[359*160]&65535)==0xf800 && (rectified[360*160-1]>>16)==0x07e0);
        assert(xqr_rgb565(&frame,rgb,1280u*720u*3u));
        assert(rgb[at[0]*3]==255 && !rgb[at[0]*3+1] && !rgb[at[0]*3+2]);
        assert(rgb[at[1]*3+1]==255 && rgb[at[2]*3+2]==255);
        free(pixels);free(rectified);free(rgb);
    }
    assert(!xqr_manual_init(&manual,roi,c,0));
    puts("XQ_ROI_TEST_PASS scope=synthetic_no_model_or_accuracy_acceptance");
    return 0;
}
