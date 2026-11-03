/* Exercise the actual producer boundary without running a neural graph.
 * Function-section GC discards the renamed worker main and graph entry paths. */
#define XQ_NATIVE_COACH
#define XQ_NATIVE_VISION32
#define main xqcoach_original_worker_main
#include "../../artifacts/vision-model-20261020-adapter/runtime/xq_native_worker.c"
#undef main
#include <assert.h>

int main(int argc,char **argv)
{
    static const unsigned expected[10]={0,1,5,3,4,5,5,7,8,9};
    xqcoach_identity identity;xqv_result ignored={0};xqr_box boxes[300]={{0}};
    double corners[4][2]={{100,100},{900,100},{900,600},{100,600}};
    assert(argc==2 && xqcoach_identity_init(&identity,8123,52,0x52c44a22));
    {uint8_t rgb[1024];float actual[1024],expected_rgb[1024];
     for(unsigned i=0;i<1024;i++){rgb[i]=(uint8_t)(i*71);expected_rgb[i]=(float)rgb[i]/255.f;}
     normalize_rgb(rgb,1024,actual);assert(!memcmp(actual,expected_rgb,sizeof(actual)));}
    puts("XQCOACH_ALL_256_RGB_NORMALIZATION_BITS_UNCHANGED_PASS");
    memset(&coach_pending,0,sizeof(coach_pending));coach_pending.identity=identity;
    memcpy(coach_pending.corners,corners,sizeof(corners));
    for(unsigned native=0;native<10;native++){
        unsigned remote=99;xqcoach_result out,before;memset(&before,0x5a,sizeof(before));out=before;
        assert(xqcoach_native_status(native)==expected[native]);
        assert(result_packet(argv[1],identity.token,identity.frame,identity.crc,
            "ignored-by-coach-only",native,&ignored,boxes,corners));
        xqcoach_parse_status status=xqcoach_read_result(argv[1],&identity,&out,&remote);
        assert(remote==expected[native]);
        if(native){assert(status==XQCOACH_REJECTED && !memcmp(&out,&before,sizeof(out)));}
        else assert(status==XQCOACH_ACCEPTED && out.status==0 && out.count==0);
    }
    assert(xqcoach_native_status(10)==10 && !result_packet(argv[1],identity.token,identity.frame,
        identity.crc,"ignored",10,&ignored,boxes,corners));
    coach_partial.identity=identity;coach_partial.status=5;coach_partial.count=1;
    coach_partial.candidates[0]=(xqcoach_candidate){10,255,255,750,.75f,20,30,60,70};
    for(unsigned native=5;native<=6;native++){
        assert(result_packet(argv[1],identity.token,identity.frame,identity.crc,"ignored",native,&ignored,boxes,corners));
        FILE *f=fopen(argv[1],"r");char text[XQCOACH_PACKET_BYTES];assert(f);
        size_t n=fread(text,1,sizeof(text),f);assert(!ferror(f) && !fclose(f));
        xqcoach_result partial;unsigned remote=99;
        assert(xqcoach_parse_result(text,n,&identity,&partial,&remote)==XQCOACH_INVALID && remote==99);
        assert(xqcoach_parse_partial(text,n,&identity,&partial)==XQCOACH_ACCEPTED && partial.count==1 && partial.candidates[0].file==255);
    }
    puts("XQCOACH_ACTUAL_PRODUCER_UNMAPPED_PARTIAL_NEVER_MAPPED_PASS");
    puts("XQCOACH_ACTUAL_PRODUCER_GEOMETRY_2_5_6_TO_5_ONLY_DIAGNOSTICS_UNCHANGED_PASS");return 0;
}
