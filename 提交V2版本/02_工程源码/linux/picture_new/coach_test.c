#include "coach_geometry.h"
#include "xinyi_product.h"
#include "crc32_fast.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const double quad[4][2]={{200,100},{920,100},{920,612},{200,612}};
static xqr_box box(unsigned cid,unsigned file,unsigned rank,float score)
{
    float x=200.f+80.f*rank,y=100.f+64.f*file;
    return (xqr_box){x-12,y-12,x+12,y+12,score,cid};
}
static unsigned base(xqr_box *b)
{
    b[0]=box(0,4,0,.999f);b[1]=box(7,4,9,.998f);b[2]=box(6,4,3,.95f);return 3;
}
static xy_repair_result repair(const xqcoach_result *r)
{
    xy_detection d[XY_MAX_DETECTIONS];xy_repair_result result;
    for(unsigned i=0;i<r->count;i++){
        const xqcoach_candidate *c=&r->candidates[i];
        d[i]=(xy_detection){c->class_id,c->file,c->rank,c->confidence};
    }
    assert(xy_repair(d,r->count,&result));return result;
}
static void roundtrip(const xqcoach_result *r,char *text,xqcoach_result *out)
{
    size_t n=xqcoach_encode_result(r,text,XQCOACH_PACKET_BYTES);assert(n);
    unsigned remote=99;
    assert(xqcoach_parse_result(text,n,&r->identity,out,&remote)==XQCOACH_ACCEPTED && !remote);
    assert(out->count==r->count && !memcmp(out->corners,r->corners,sizeof(r->corners)));
    for(unsigned i=0;i<r->count;i++)assert(!memcmp(&out->candidates[i],&r->candidates[i],sizeof(r->candidates[i])));
}
static void invalid_packet(const char *text,size_t bytes,const xqcoach_identity *expected,const xqcoach_result *previous)
{
    xqcoach_result out=*previous;unsigned status=99;
    assert(xqcoach_parse_result(text,bytes,expected,&out,&status)==XQCOACH_INVALID);
    assert(!memcmp(&out,previous,sizeof(out)) && status==99);
}
static size_t custom(char *text,const xqcoach_identity *id,unsigned count,const char *body)
{
    uint32_t crc=crc32_fast(0xffffffffu,body,(uint32_t)strlen(body))^0xffffffffu;
    int n=snprintf(text,XQCOACH_PACKET_BYTES,"XQ_COACH_RESULT_V1 %llu %u %08x %s 0 %u %08x\n%s",
        (unsigned long long)id->token,id->frame,id->crc,id->backend,count,crc,body);assert(n>0);return (size_t)n;
}
int main(int argc,char **argv)
{
    xqr_box boxes[301];xqcoach_identity id;unsigned n=base(boxes);
    xqcoach_result mapped={0},parsed={0},before;
    char *text=malloc(XQCOACH_PACKET_BYTES),*bad=malloc(XQCOACH_PACKET_BYTES);assert(text && bad);
    assert(xqcoach_identity_init(&id,321,52,0x8153af02));
    assert(xqcoach_map_candidates(quad,boxes,n,&id,&mapped));
    for(unsigned i=0;i<n;i++){
        assert(mapped.candidates[i].class_id==boxes[i].class_id);
        assert(mapped.candidates[i].file==4 && mapped.candidates[i].rank==(i==0?0u:i==1?9u:3u));
    }
    xy_repair_result fixed=repair(&mapped);assert(fixed.reason==XY_POSITION_VALID && !fixed.removed_count);
    /* All 90 synthetic grid centers preserve the original xnp_finish math.
     * Feed each separately with the orientation anchors, retaining duplicates. */
    for(unsigned r=0;r<10;r++)for(unsigned f=0;f<9;f++){
        boxes[3]=box(4,f,r,.8759f);
        assert(xqcoach_map_candidates(quad,boxes,4,&id,&mapped));
        assert(mapped.candidates[3].file==f && mapped.candidates[3].rank==r && mapped.candidates[3].confidence==875);
        roundtrip(&mapped,text,&parsed);
    }
    puts("XQCOACH_90_GRID_AND_REAL_CONFIDENCE_PASS");
    n=base(boxes);boxes[n++]=box(4,0,0,.95f);boxes[n++]=box(4,8,0,.9f);boxes[n++]=box(4,0,4,.2f);
    xqv_result legacy;double gui[4][2];
    assert(!xnp_finish(quad,boxes,n,id.frame,&legacy,gui)); /* Original status6 guard retained. */
    assert(xqcoach_map_candidates(quad,boxes,n,&id,&mapped) && mapped.count==6);
    roundtrip(&mapped,text,&parsed);fixed=repair(&parsed);
    assert(fixed.reason==XY_POSITION_VALID && fixed.removed_count==1 && !fixed.board.squares[36] && fixed.corrected[36]);
    puts("XQCOACH_THREE_ROOKS_DELETE_ONLY_LEGACY_REJECT_PASS");
    boxes[n-1]=box(3,0,0,.6f);
    assert(xqcoach_map_candidates(quad,boxes,n,&id,&mapped));fixed=repair(&mapped);
    assert(fixed.reason==XY_POSITION_VALID && fixed.removed_count==1 && fixed.corrected[0]);
    n=base(boxes);boxes[n++]=box(0,3,0,.7f);
    assert(!xnp_finish(quad,boxes,n,id.frame,&legacy,gui));
    assert(xqcoach_map_candidates(quad,boxes,n,&id,&mapped));fixed=repair(&mapped);
    assert(fixed.reason==XY_POSITION_VALID && fixed.removed_count==1 && !fixed.board.squares[3]);
    boxes[1]=boxes[2]; /* One king is missing, orientation still has red's vote. */
    assert(xqcoach_map_candidates(quad,boxes,2,&id,&mapped));fixed=repair(&mapped);
    assert(fixed.reason==XY_POSITION_MISSING_KING);
    puts("XQCOACH_DUPLICATE_CELL_SAME_SIDE_KINGS_AND_MISSING_KING_PASS");
    n=base(boxes);before=mapped;
    boxes[n++]=box(0,4,9,.05f); /* Conflicting orientation, even at low confidence. */
    assert(!xqcoach_map_candidates(quad,boxes,n,&id,&mapped) && !memcmp(&mapped,&before,sizeof(mapped)));
    boxes[0]=box(4,0,0,.9f);boxes[1]=box(4,8,0,.8f);
    assert(!xqcoach_map_candidates(quad,boxes,2,&id,&mapped));
    n=base(boxes);boxes[3]=box(4,0,0,.9f);boxes[3].x0+=31.92f;boxes[3].x1+=31.92f;
    assert(xqcoach_map_candidates(quad,boxes,4,&id,&mapped));
    assert(xnp_finish(quad,boxes,4,id.frame,&legacy,gui));
    for(unsigned i=0;i<4;i++)assert(legacy.pieces[i].file==mapped.candidates[i].file && legacy.pieces[i].rank==mapped.candidates[i].rank);
    boxes[3].x0+=.16f;boxes[3].x1+=.16f;
    assert(!xqcoach_map_candidates(quad,boxes,4,&id,&mapped) && !xnp_finish(quad,boxes,4,id.frame,&legacy,gui));
    assert(xqcoach_estimate_candidates(quad,boxes,4,&id,&mapped) && mapped.estimated && mapped.status==5);
    assert(mapped.candidates[3].file==0 && mapped.candidates[3].rank==0);
    boxes[3].x0=1100;boxes[3].x1=1124;
    assert(xqcoach_estimate_candidates(quad,boxes,4,&id,&mapped) && mapped.candidates[3].file==255 && mapped.candidates[3].rank==255);
    puts("XQCOACH_COARSE_ESTIMATE_SEPARATE_FROM_STRICT_GRID_UNMAPPED_OUTSIDE_PASS");
    double collapsed[4][2]={{0}};assert(!xqcoach_map_candidates(collapsed,boxes,3,&id,&mapped));
    puts("XQCOACH_ORIENTATION_NO_VOTES_CONFLICT_AND_UNCHANGED_MARGIN_REJECT_PASS");
    base(boxes);for(unsigned i=3;i<301;i++)boxes[i]=box(4,0,0,.1234567f);
    assert(xqcoach_map_candidates(quad,boxes,300,&id,&mapped) && mapped.count==300);
    roundtrip(&mapped,text,&parsed);before=mapped;
    assert(!xqcoach_map_candidates(quad,boxes,301,&id,&mapped) && !memcmp(&mapped,&before,sizeof(mapped)));
    size_t bytes=xqcoach_encode_result(&mapped,text,XQCOACH_PACKET_BYTES);assert(bytes);
    xqcoach_identity wrong=id;wrong.token++;invalid_packet(text,bytes,&wrong,&before);
    wrong=id;wrong.frame++;invalid_packet(text,bytes,&wrong,&before);
    wrong=id;wrong.crc^=1;invalid_packet(text,bytes,&wrong,&before);
    wrong=id;strcpy(wrong.backend,"rv32-driver-quantized-mac");invalid_packet(text,bytes,&wrong,&before);
    memcpy(bad,text,bytes);bad[bytes-2]^=1;invalid_packet(bad,bytes,&id,&before);
    invalid_packet(text,bytes-1,&id,&before);
    const char *old_result="XQ_MODEL_RESULT_V1 321 52 8153af02 rv32-driver-quantized-mac 0 0\n";
    invalid_packet(old_result,strlen(old_result),&id,&before);
    const char *body="Q 200 100\nQ 920 100\nQ 920 612\nQ 200 612\nD 4 0 0 900 nan 188 88 212 112\n";
    bytes=custom(bad,&id,1,body);invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,301,"");invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,1,"Q 200 100\nQ 920 100\nQ 920 612\nQ 200 612\nD 256 0 0 900 .9 188 88 212 112\n");invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,1,"Q 200 100\nQ 920 100\nQ 920 612\nQ 200 612\nD 4 9 0 900 .9 188 88 212 112\n");invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,1,"Q 200 100\nQ 920 100\nQ 920 612\nQ 200 612\nD 4 0 10 900 .9 188 88 212 112\n");invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,1,"Q 200 100\nQ 920 100\nQ 920 612\nQ 200 612\nD 4 0 0 950 .9 188 88 212 112\n");invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,0,"Q nan 100\nQ 920 100\nQ 920 612\nQ 200 612\n");invalid_packet(bad,bytes,&id,&before);
    bytes=custom(bad,&id,0,"Q 200 100\nQ 920 100\nQ 920 612\nQ 200 612\ntrailing\n");invalid_packet(bad,bytes,&id,&before);
    puts("XQCOACH_IDENTITY_RAW_BODY_CRC_RANGES_FINITE_AND_OLD_PROTOCOL_REJECT_PASS");
    xqcoach_result rejected={0};rejected.identity=id;rejected.status=5;
    bytes=xqcoach_encode_result(&rejected,text,XQCOACH_PACKET_BYTES);assert(bytes);parsed=before;unsigned remote=99;
    assert(xqcoach_parse_result(text,bytes,&id,&parsed,&remote)==XQCOACH_REJECTED && remote==5 && !memcmp(&parsed,&before,sizeof(parsed)));
    rejected.status=XQCOACH_CANCELLED;
    bytes=xqcoach_encode_result(&rejected,text,XQCOACH_PACKET_BYTES);assert(bytes);remote=99;
    assert(xqcoach_parse_result(text,bytes,&id,&parsed,&remote)==XQCOACH_REJECTED && remote==9 && !memcmp(&parsed,&before,sizeof(parsed)));
    wrong=id;wrong.token++;invalid_packet(text,bytes,&wrong,&before);
    rejected.count=1;assert(!xqcoach_encode_result(&rejected,text,XQCOACH_PACKET_BYTES));rejected.count=0;
    rejected.status=10;assert(!xqcoach_encode_result(&rejected,text,XQCOACH_PACKET_BYTES));rejected.status=XQCOACH_CANCELLED;
    puts("XQCOACH_RELEASE9_EMPTY_IDENTITY_AND_KEEP_PREVIOUS_PASS");
    char request[256];bytes=xqcoach_encode_request(&id,request,sizeof(request));assert(bytes);xqcoach_identity request_id;
    assert(xqcoach_parse_request(request,bytes,&request_id) && request_id.token==id.token && request_id.crc==id.crc);
    const char *old_request="XQ_MODEL_REQUEST_V1 321 52 8153af02 rv32-v321-coach\n";
    assert(!xqcoach_parse_request(old_request,strlen(old_request),&request_id));
    if(argc==2){
        assert(xqcoach_write_result_atomic(argv[1],&before));parsed=(xqcoach_result){0};
        assert(xqcoach_read_result(argv[1],&id,&parsed,&remote)==XQCOACH_ACCEPTED && parsed.count==300);
        assert(xqcoach_write_result_atomic(argv[1],&rejected));parsed=before;
        assert(xqcoach_read_result(argv[1],&id,&parsed,&remote)==XQCOACH_REJECTED && !memcmp(&parsed,&before,sizeof(parsed)));
    }
    puts("XQCOACH_GEOMETRY_REJECT_KEEP_PREVIOUS_AND_ATOMIC_IPC_PASS");
    free(text);free(bad);return 0;
}
