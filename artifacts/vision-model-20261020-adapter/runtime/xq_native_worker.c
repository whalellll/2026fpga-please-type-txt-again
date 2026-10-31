#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "xq_native_post.h"
#include "xq_native_geometry.h"
#include "xq_resident_matrix.h"
#include "xq_native_timing.h"
#include "crc32_fast.h"
#include "native_parameters.h"
#ifdef XQ_NATIVE_COACH
#include "coach_geometry.h"
#include "coach_driver_guard.h"
static xqcoach_result coach_pending;
static xqcoach_result coach_partial;
#endif
#ifndef XQ_NATIVE_DETECTOR_SIDE
#define XQ_NATIVE_DETECTOR_SIDE 640u
#endif
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stop_requested;
static const char *live_request;
#ifdef XQ_NATIVE_TIMING
static unsigned observer_checks;
#endif
static void checks(void *context,unsigned layer,const int8_t *q,size_t qn,const int16_t *out,size_t on,const int32_t *acc,const int16_t *pre)
{
    FILE *f=context;
    fprintf(f,"%u %zu %zu %08x %08x %08x %08x\n",layer,qn,on,
        crc32_fast(0xffffffffu,q,(uint32_t)qn)^0xffffffffu,
        crc32_fast(0xffffffffu,acc,(uint32_t)(on*4))^0xffffffffu,
        crc32_fast(0xffffffffu,pre,(uint32_t)(on*2))^0xffffffffu,
        crc32_fast(0xffffffffu,out,(uint32_t)(on*2))^0xffffffffu);
}
static void stop(int s){(void)s;stop_requested=1;}
static int cancelled(void *unused){(void)unused;return stop_requested || (live_request && access(live_request,F_OK));}
static uint64_t now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
/* All 256 exact binary32 quotients, instead of a software float divide for
 * every RGB byte. The quotient expression/rounding is unchanged. */
static void normalize_rgb(const uint8_t *source,size_t count,float *out)
{
    float unit[256];for(unsigned i=0;i<256;i++)unit[i]=(float)i/255.f;
    for(size_t i=0;i<count;i++)out[i]=unit[source[i]];
}
typedef struct {xqr_box box;unsigned order;} proposal;
static int compare_proposal(const void *a,const void *b)
{
    const proposal *x=a,*y=b;
    if(x->box.score!=y->box.score)return x->box.score>y->box.score?-1:1;
    return x->order<y->order?-1:x->order>y->order;
}
static float sigmoid(float x){return 1.f/(1.f+expf(-x));}
static float overlap(const xqr_box *a,const xqr_box *b)
{
    float w=fmaxf(0,fminf(a->x1,b->x1)-fmaxf(a->x0,b->x0));
    float h=fmaxf(0,fminf(a->y1,b->y1)-fmaxf(a->y0,b->y0));
    float inter=w*h;return inter/((a->x1-a->x0)*(a->y1-a->y0)+(b->x1-b->x0)*(b->y1-b->y0)-inter);
}
static unsigned nms(proposal *p,unsigned n,xqr_box out[300])
{
    unsigned used=0;qsort(p,n,sizeof(*p),compare_proposal);if(n>30000)n=30000;
    for(unsigned i=0;i<n && used<300;i++) {
        int suppressed=0;
        for(unsigned j=0;j<used;j++)if(p[i].box.class_id==out[j].class_id && overlap(&p[i].box,&out[j])>.6f){suppressed=1;break;}
        if(!suppressed)out[used++]=p[i].box;
    }
    return used;
}
static int detector_boxes(xqn_model *m,xqr_box out[300],unsigned *count)
{
    proposal *p=malloc(352800*sizeof(*p));unsigned n=0,order=0;
    if(!p)return 0;
    for(unsigned head=0;head<3;head++) {
        unsigned d[4];const float *x=xqn_output(m,head,d);
        if(!x || d[0]!=1 || d[1]!=57 || d[2]!=d[3] || d[2]!=(XQ_NATIVE_DETECTOR_SIDE/8u)/(1u<<head)){free(p);return 0;}
        unsigned side=d[2],area=side*side;
        for(unsigned anchor=0;anchor<3;anchor++)for(unsigned y=0;y<side;y++)for(unsigned xx=0;xx<side;xx++,order+=14) {
            const float *q=x+(anchor*19*area+y*side+xx);
            float obj=sigmoid(q[4*area]);if(obj<=.001f)continue;
            float cx=(sigmoid(q[0])*2.f+(xx-.5f))*native_strides[head];
            float cy=(sigmoid(q[area])*2.f+(y-.5f))*native_strides[head];
            float w=sigmoid(q[2*area])*2.f,h=sigmoid(q[3*area])*2.f;
            w=w*w*native_anchors[head][anchor][0];h=h*h*native_anchors[head][anchor][1];
            for(unsigned cls=0;cls<14;cls++) {
                float score=obj*sigmoid(q[(cls+5)*area]);
                if(score>.001f) {if(n>=352800){free(p);return 0;}
                    p[n++]=(proposal){{cx-w/2.f,cy-h/2.f,cx+w/2.f,cy+h/2.f,score,cls},order+cls};}
            }
        }
    }
    *count=nms(p,n,out);free(p);return 1;
}
static int result_packet(const char *path,uint64_t token,uint32_t frame,uint32_t crc,const char *backend,
                         unsigned status,const xqv_result *r,const xqr_box *boxes,const double corners[4][2])
{
#ifdef XQ_NATIVE_COACH
    xqcoach_result packet={0};
    (void)backend;(void)r;(void)boxes;(void)corners;
    if(!xqcoach_identity_init(&packet.identity,token,frame,crc))return 0;
    if(!status){
        if(coach_pending.identity.token!=token || coach_pending.identity.frame!=frame || coach_pending.identity.crc!=crc)return 0;
        packet=coach_pending;
    } else {
        packet.status=xqcoach_native_status(status);
        if((status==5 || status==6) && coach_partial.count && coach_partial.identity.token==token &&
           coach_partial.identity.frame==frame && coach_partial.identity.crc==crc)
            return xqcoach_write_partial_atomic(path,&coach_partial);
    }
    return xqcoach_write_result_atomic(path,&packet);
#else
    char tmp[600];FILE *f;
    if(snprintf(tmp,sizeof(tmp),"%s.part",path)>=(int)sizeof(tmp))return 0;
    f=fopen(tmp,"w");if(!f)return 0;
    fprintf(f,"XQ_MODEL_RESULT_V1 %llu %u %08x %s %u %u\n",(unsigned long long)token,frame,crc,backend,status,status?0:r->piece_count);
    if(!status) {
        fprintf(f,"%s\n",r->fen);
        for(unsigned i=0;i<r->piece_count;i++)fprintf(f,"%u %u %u %u %.9g %.9g %.9g %.9g\n",
            r->pieces[i].class_id,r->pieces[i].file,r->pieces[i].rank,r->pieces[i].confidence,
            boxes[i].x0,boxes[i].y0,boxes[i].x1,boxes[i].y1);
        for(unsigned i=0;i<4;i++)fprintf(f,"%.17g %.17g\n",corners[i][0],corners[i][1]);
    }
    if(ferror(f)){fclose(f);unlink(tmp);return 0;}
    if(fclose(f) || rename(tmp,path)){unlink(tmp);return 0;}return 1;
#endif
}
static unsigned recognize(xqn_model *models[3],const xqm_transport *io,int cpu,const uint8_t rng[91][240][4],
                           const xqv_frame *frame,xqv_result *result,xqr_box fixed[300],double gui[4][2],
                           xng_state *geometry,const char *manual_path)
{
    uint8_t *rgb=NULL,*image=NULL,*patches=NULL;float *tensor=NULL,*probabilities=NULL;
    xqr_box boxes[300],fused[300];unsigned count=0,nfused=0,nfixed=0,status=1,executed=0;
    xqr_letterbox plan;xqr_roi roi;double coarse[4][2],refined[4][2],ih[9];float corners[8];
    xng_geometry chosen={0};xng_event geometry_event=XNG_BAD_REQUEST;int coarse_valid=0,manual=0;
    uint64_t start=now_ms(),mark=start;uint64_t times[5]={0};xqm_stats st,total={0};xnp_refinement refinement={0};
    xnt_profile timing;xnt_begin(&timing);xqn_resident_profile_reset();
#ifdef XQ_NATIVE_COACH
    memset(&coach_partial,0,sizeof(coach_partial));
#endif
    rgb=malloc(1280u*720u*3u);image=malloc(3u*640u*640u);tensor=malloc(3u*640u*640u*sizeof(float));
    if(!rgb || !image || !tensor || !xqr_rgb565(frame,rgb,1280u*720u*3u) ||
       !xqr_resize_rgb(rgb,1280,720,3840,0,0,1280,720,192,192,image,3u*640u*640u))goto done;
    normalize_rgb(image,3u*192u*192u,tensor);
    xnt_step(&timing,XNT_GRAPH);
    if(!xqn_run(models[0],io,1,tensor,cpu,&st))goto done;
    xnt_step(&timing,XNT_POST);
    if(!xqn_board_corners(models[0],corners))goto done;
    executed|=1;
    total.jobs+=st.jobs;total.cycles+=st.cycles;
    for(unsigned i=0;i<4;i++){coarse[i][0]=(double)corners[2*i]*1280-.5;coarse[i][1]=(double)corners[2*i+1]*720-.5;}
    status=2;coarse_valid=xnp_coarse(coarse,ih,&roi);
#ifndef XQ_NATIVE_COACH
    if(manual_path && !access(manual_path,F_OK)) {
        if(!xng_read_manual(manual_path,geometry->token,frame->frame_id,geometry->crc,coarse) ||
           (geometry_event=xng_manual(geometry,geometry->token,frame->frame_id,geometry->crc,coarse,&chosen))!=XNG_OK)goto done;
        coarse_valid=1;manual=1;
    }
#else
    (void)manual_path;
#endif
    if(!coarse_valid && geometry->failures<2) {
        geometry_event=xng_resolve(geometry,NULL,0,NULL,0,NULL,&chosen);goto done;
    }
    roi=(xqr_roi){0,0,1280,720};
    if(coarse_valid) {
        double x0=1280,x1=0,y0=720,y1=0;
        for(unsigned i=0;i<4;i++){x0=fmin(x0,coarse[i][0]);x1=fmax(x1,coarse[i][0]);y0=fmin(y0,coarse[i][1]);y1=fmax(y1,coarse[i][1]);}
        double w=x1-x0,h=y1-y0;
        roi=(xqr_roi){(int)fmax(0,floor(x0-native_roi_margins[0]*w)),(int)fmax(0,floor(y0-native_roi_margins[1]*h)),
                      (int)fmin(1280,ceil(x1+native_roi_margins[2]*w)),(int)fmin(720,ceil(y1+native_roi_margins[3]*h))};
    }
    times[0]=now_ms()-mark;mark=now_ms();
    printf("XQ_NATIVE_STAGE board_done ms=%llu jobs=%llu\n",(unsigned long long)times[0],(unsigned long long)st.jobs);fflush(stdout);
    xnt_step(&timing,XNT_PREPARE);
    status=3;if(xqn_input_side(models[1])!=XQ_NATIVE_DETECTOR_SIDE || cancelled(NULL) ||
       !xqr_detector_input(rgb,roi,XQ_NATIVE_DETECTOR_SIDE,image,3u*640u*640u,&plan))goto done;
    normalize_rgb(image,3u*XQ_NATIVE_DETECTOR_SIDE*XQ_NATIVE_DETECTOR_SIDE,tensor);
    xnt_step(&timing,XNT_GRAPH);
    if(!xqn_run(models[1],io,1,tensor,cpu,&st))goto done;
    xnt_step(&timing,XNT_POST);
    if(!detector_boxes(models[1],boxes,&count))goto done;
    executed|=2;
    total.jobs+=st.jobs;total.cycles+=st.cycles;
    for(unsigned i=0,used=0;i<count;i++) {
        xqr_box box=boxes[i];if(xqr_box_original(&plan,&box))boxes[used++]=box;
        if(i+1==count)count=used;
    }
    times[1]=now_ms()-mark;mark=now_ms();status=4;
    printf("XQ_NATIVE_STAGE detector_done ms=%llu jobs=%llu proposals=%u\n",(unsigned long long)times[1],(unsigned long long)st.jobs,count);fflush(stdout);
    { unsigned before=count;
#ifndef XQ_DISABLE_CANDIDATE_FILTER
      if(!xnp_filter_candidates(boxes,&count))goto done;
#endif
      printf("XQ_NATIVE_CANDIDATES before=%u classifier_batch=%u threshold=0.05\n",before,count);fflush(stdout); }
    free(tensor);tensor=NULL;
    if(count) {
        xnt_step(&timing,XNT_PREPARE);
        patches=malloc((size_t)count*3072);probabilities=malloc((size_t)count*15*4);
        if(!patches || !probabilities)goto done;
        for(unsigned i=0;i<count;i++)if(!xqr_piece_crop(rgb,&boxes[i],patches+(size_t)i*3072,3072))goto done;
        tensor=malloc((size_t)(count<256?count:256)*3072*4);if(!tensor)goto done;
        for(unsigned begin=0;begin<count;begin+=256) {
            unsigned batch=count-begin<256?count-begin:256;
            normalize_rgb(patches+(size_t)begin*3072,(size_t)batch*3072,tensor);
            if(cancelled(NULL))goto done;
            xnt_step(&timing,XNT_GRAPH);
            if(!xqn_run(models[2],io,batch,tensor,cpu,&st))goto done;
            xnt_step(&timing,XNT_POST);
            executed|=4;
            total.jobs+=st.jobs;total.cycles+=st.cycles;
            const float *logits=xqn_output(models[2],0,NULL);if(!logits)goto done;
            for(unsigned b=0;b<batch;b++) {
                float maximum=-INFINITY,sum=0;
                for(unsigned c=0;c<15;c++)maximum=fmaxf(maximum,logits[b*15+c]);
                for(unsigned c=0;c<15;c++){float v=expf(logits[b*15+c]-maximum);probabilities[(begin+b)*15+c]=v;sum+=v;}
                for(unsigned c=0;c<15;c++)probabilities[(begin+b)*15+c]/=sum;
            }
            if(begin+batch<count)xnt_step(&timing,XNT_PREPARE);
        }
        if(!xqr_fuse(boxes,probabilities,count,fused,&nfused))goto done;
        proposal p[300];for(unsigned i=0;i<nfused;i++)p[i]=(proposal){fused[i],i};
        nfused=nms(p,nfused,boxes);
        for(unsigned i=0;i<nfused;i++)if(boxes[i].score>=.05f)fixed[nfixed++]=boxes[i];
    }
    times[2]=now_ms()-mark;mark=now_ms();status=5;
    printf("XQ_NATIVE_STAGE classifier_done ms=%llu fixed=%u\n",(unsigned long long)times[2],nfixed);fflush(stdout);
#ifdef XQ_NATIVE_COACH
    if(nfixed && xqcoach_identity_init(&coach_partial.identity,geometry->token,frame->frame_id,geometry->crc)) {
        coach_partial.status=5;coach_partial.count=nfixed;
        for(unsigned i=0;i<nfixed;i++) {
            const xqr_box *b=&fixed[i];
            coach_partial.candidates[i]=(xqcoach_candidate){b->class_id,255,255,
                (uint16_t)floor((double)b->score*1000.),b->score,b->x0,b->y0,b->x1,b->y1};
        }
        xqcoach_result estimate;
        if(coarse_valid && xqcoach_estimate_candidates(coarse,fixed,nfixed,&coach_partial.identity,&estimate))coach_partial=estimate;
    }
#endif
    xnt_step(&timing,XNT_REFINE);
    if(cancelled(NULL))goto done;
    if(!manual) {
        int refined_valid=coarse_valid && xnp_refine(rgb,coarse,fixed,nfixed,rng,refined,&refinement);
        geometry_event=xng_resolve(geometry,refined,refined_valid,fixed,nfixed,coarse_valid?coarse:NULL,&chosen);
        if(geometry_event!=XNG_OK)goto done;
    }
    memcpy(refined,chosen.corners,sizeof(refined));
    times[3]=now_ms()-mark;mark=now_ms();status=6;
    xnt_step(&timing,XNT_ASSIGN);
#ifdef XQ_NATIVE_COACH
    {
        xqcoach_identity identity;
        (void)result;
        if(!xqcoach_identity_init(&identity,geometry->token,frame->frame_id,geometry->crc) ||
           !xqcoach_map_candidates(refined,fixed,nfixed,&identity,&coach_pending))goto done;
        memcpy(gui,coach_pending.corners,sizeof(coach_pending.corners));
    }
#else
    if(!xnp_finish(refined,fixed,nfixed,frame->frame_id,result,gui))goto done;
#endif
    times[4]=now_ms()-mark;status=0;
done:
    xnt_step(&timing,XNT_STOP);
    if(status==5)times[3]=now_ms()-mark;
    if(status==6)times[4]=now_ms()-mark;
    if(status && geometry_event==XNG_MANUAL_REQUIRED)status=8;
    printf("XQ_NATIVE_GEOMETRY event=%u source=%s failures=%u kept=%u\n",(unsigned)geometry_event,
        xng_source_name(chosen.source),geometry->failures,chosen.kept);
    printf("XQ_NATIVE_RECOGNITION status=%u models_loaded=3 executed_mask=%u cpu_reference=%d board_ms=%llu detector_ms=%llu classifier_ms=%llu refine_ms=%llu assign_ms=%llu total_ms=%llu proposals=%u fixed=%u crossings=%u inliers=%u jobs=%llu cycles=%llu\n",
        status,executed,cpu,(unsigned long long)times[0],(unsigned long long)times[1],(unsigned long long)times[2],(unsigned long long)times[3],
        (unsigned long long)times[4],(unsigned long long)(now_ms()-start),count,nfixed,refinement.crossings,refinement.inliers,
        (unsigned long long)total.jobs,(unsigned long long)total.cycles);fflush(stdout);
#ifdef XQ_NATIVE_TIMING
    {
        xqn_resident_profile p;xqn_resident_profile_read(&p);
        printf("XQ_NATIVE_PROFILE prepare_ms=%llu graph_ms=%llu ioctl_ms=%llu post_ms=%llu refine_ms=%llu assign_ms=%llu\n",
            (unsigned long long)(timing.ns[XNT_PREPARE]/1000000),(unsigned long long)(timing.ns[XNT_GRAPH]/1000000),
            (unsigned long long)(p.ioctl_ns/1000000),(unsigned long long)(timing.ns[XNT_POST]/1000000),
            (unsigned long long)(timing.ns[XNT_REFINE]/1000000),(unsigned long long)(timing.ns[XNT_ASSIGN]/1000000));
        fflush(stdout);
        unsigned valid=!timing.clock_errors && !p.clock_failures && p.enabled &&
            (!cpu?p.runs==total.jobs && p.cycles==total.cycles:!p.runs) && p.ioctl_ns<=timing.ns[XNT_GRAPH];
        printf("XQ_NATIVE_TIMING token=%llu valid=%u observer_checks=%u prepare_us=%llu graph_us=%llu driver_us=%llu post_us=%llu refine_us=%llu assign_us=%llu worker_us=%llu ioctl_calls=%llu registrations=%llu ioctl_errors=%llu jobs=%llu cycles=%llu\n",
            (unsigned long long)geometry->token,valid,observer_checks,
            (unsigned long long)(timing.ns[XNT_PREPARE]/1000),(unsigned long long)(timing.ns[XNT_GRAPH]/1000),
            (unsigned long long)(p.ioctl_ns/1000),(unsigned long long)(timing.ns[XNT_POST]/1000),
            (unsigned long long)(timing.ns[XNT_REFINE]/1000),(unsigned long long)(timing.ns[XNT_ASSIGN]/1000),
            (unsigned long long)((timing.last_ns-timing.start_ns)/1000),(unsigned long long)p.calls,
            (unsigned long long)p.registrations,(unsigned long long)p.errors,
            (unsigned long long)total.jobs,(unsigned long long)total.cycles);fflush(stdout);
    }
#endif
    free(rgb);free(image);free(patches);free(tensor);free(probabilities);return status;
}
int main(int argc,char **argv)
{
    const char *directory=NULL,*models_dir=NULL,*request_file=NULL,*raw_path=NULL,*out_path=NULL,*checks_path=NULL,*manual_path=NULL;
    int cpu=0,serve=0,driver=0,rc=2;char path[600],request[600],raw[600],output[600];
    xqn_model *models[3]={0};xqm_linux mac[3];uint8_t (*rng)[240][4]=NULL;uint32_t *pixels=NULL;xng_state geometry={0};
#ifndef XQ_NATIVE_COACH
    char manual_file[600];
#endif
    FILE *check_file=NULL;
    const char *names[3]={"board.xqm","detector.xqm","classifier.xqm"};
    memset(mac,0,sizeof(mac));for(unsigned i=0;i<3;i++)mac[i].fd=-1;
    for(int i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--cpu-reference"))cpu=1;
        else if(!strcmp(argv[i],"--driver"))driver=1;
        else if(!strcmp(argv[i],"--models") && i+1<argc)models_dir=argv[++i];
        else if(!strcmp(argv[i],"--serve") && i+1<argc){directory=argv[++i];serve=1;}
        else if(!strcmp(argv[i],"--request") && i+1<argc)request_file=argv[++i];
        else if(!strcmp(argv[i],"--input") && i+1<argc)raw_path=argv[++i];
        else if(!strcmp(argv[i],"--output") && i+1<argc)out_path=argv[++i];
        else if(!strcmp(argv[i],"--checks") && i+1<argc)checks_path=argv[++i];
        else if(!strcmp(argv[i],"--manual-corners") && i+1<argc) {
#ifdef XQ_NATIVE_COACH
            goto done;
#else
            manual_path=argv[++i];
#endif
        }
        else goto done;
    }
    if(!models_dir || cpu+driver!=1 || (serve && cpu) || (!serve && (!request_file || !raw_path || !out_path)))goto done;
    if(checks_path && (serve || !(check_file=fopen(checks_path,"wx"))))goto done;
#ifdef XQ_NATIVE_TIMING
    observer_checks=check_file!=NULL;
#endif
    if(check_file)fputs("XQ_NATIVE_CHECKS_V1\n",check_file);
    if(driver)for(unsigned i=0;i<3;i++) {
        if(!xqm_linux_open(&mac[i])){fputs("XQ_NATIVE_DRIVER_REQUIRED no_fallback=1\n",stderr);goto done;}
        mac[i].io.cancelled=cancelled;
#ifndef XQ_NATIVE_VISION32
        const char *gray=getenv("XQ_NATIVE_CONV");mac[i].conv_enabled=gray && !strcmp(gray,"gray");
#endif
    }
    for(unsigned i=0;i<3;i++) {
        if(snprintf(path,sizeof(path),"%s/%s",models_dir,names[i])>=(int)sizeof(path) || !(models[i]=xqn_load(path)))goto done;
        if(check_file)xqn_observe(models[i],checks,check_file);
    }
#if XQ_HWC_DETECTOR
    if(!driver || !xqv_exact_available(&mac[1].io)){
        fputs("XQ_NATIVE_HWC_EXACT_DRIVER_REQUIRED no_fallback=1\n",stderr);goto done;
    }
#endif
#ifndef XQ_NATIVE_VISION32
    if(driver && (!xqn_pin_resident(models[0],&mac[0].io) || !xqn_pin_resident(models[2],&mac[2].io))) {
        fputs("XQ_NATIVE_MODEL_RESIDENCY_FAILED no_fallback=1\n",stderr);goto done;
    }
#endif
    rng=malloc(91*240*4);pixels=malloc(XQV_FRAME_BYTES);if(!rng || !pixels)goto done;
    if(snprintf(path,sizeof(path),"%s/refinement_rng.bin",models_dir)>=(int)sizeof(path) || !xnp_load_rng(path,rng))goto done;
    if(serve) {
        if(snprintf(request,sizeof(request),"%s/request.txt",directory)>=(int)sizeof(request) ||
           snprintf(raw,sizeof(raw),"%s/frame.rgb565",directory)>=(int)sizeof(raw) ||
           snprintf(output,sizeof(output),"%s/result.txt",directory)>=(int)sizeof(output))goto done;
        request_file=request;raw_path=raw;out_path=output;
#ifndef XQ_NATIVE_COACH
        if(!manual_path) {
            if(snprintf(manual_file,sizeof(manual_file),"%s/manual-corners.txt",directory)>=(int)sizeof(manual_file))goto done;
            manual_path=manual_file;
        }
#endif
    }
    signal(SIGINT,stop);signal(SIGTERM,stop);
#ifdef XQ_NATIVE_COACH
    puts(driver?"XQ_COACH_READY models=3 backend=rv32-v321-coach stateless=1 EXPERIMENTAL":"XQ_COACH_READY models=3 backend=CPU_REFERENCE stateless=1 EXPERIMENTAL");
#else
    puts(driver?"XQ_NATIVE_READY models=3 backend=rv32-driver-quantized-mac EXPERIMENTAL":"XQ_NATIVE_READY models=3 backend=CPU_REFERENCE EXPERIMENTAL");
#endif
#ifdef XQ_NATIVE_VISION32
    puts("XQ_NATIVE_DEVICE backend=vision32 raw_i32=1 dense_pin=0 no_fallback=1");
#endif
#ifdef XQ_NATIVE_COACH
    if(serve)fputs(XQCOACH_IDLE,stdout);
#endif
    fflush(stdout);rc=0;
    while(!stop_requested) {
        FILE *f=fopen(request_file,"r");char backend[64];unsigned long long token;unsigned fid,crc;
        if(!f){if(!serve){rc=2;break;}const struct timespec t={0,100000000};nanosleep(&t,NULL);continue;}
#ifdef XQ_NATIVE_COACH
        char request_text[256];xqcoach_identity identity;
        size_t request_bytes=fread(request_text,1,sizeof(request_text),f);
        int valid=!ferror(f) && request_bytes<sizeof(request_text) &&
            xqcoach_parse_request(request_text,request_bytes,&identity);fclose(f);
        if(!valid){rc=2;break;}
        token=(unsigned long long)identity.token;fid=identity.frame;crc=identity.crc;
        memcpy(backend,XQCOACH_BACKEND,sizeof(XQCOACH_BACKEND));
        /* Each coach photo is independent: no previous geometry, failure
         * counter, manual sidecar or tracked board may influence this shot. */
        memset(&geometry,0,sizeof(geometry));memset(&coach_pending,0,sizeof(coach_pending));
#else
        char magic[32];
        int valid=fscanf(f,"%31s %llu %u %x %63s",magic,&token,&fid,&crc,backend)==5 && !strcmp(magic,"XQ_MODEL_REQUEST_V1") &&
            (!driver || !strcmp(backend,"rv32-driver-quantized-mac"));fclose(f);
        if(!valid){rc=2;break;}
#endif
        f=fopen(raw_path,"rb");if(!f){rc=2;break;}
        valid=fread(pixels,1,XQV_FRAME_BYTES,f)==XQV_FRAME_BYTES && fgetc(f)==EOF && !ferror(f) &&
            (crc32_fast(0xffffffffu,pixels,XQV_FRAME_BYTES)^0xffffffffu)==crc;fclose(f);
        xqv_result result={0};xqr_box boxes[300];double corners[4][2];
        xqv_frame frame={pixels,XQV_FRAME_BYTES,fid,0};unsigned status=7;
        live_request=serve?request_file:NULL;
        if(valid && xng_begin(&geometry,(uint64_t)token,fid,crc))
            status=recognize(models,driver?&mac[1].io:NULL,cpu,rng,&frame,&result,boxes,corners,&geometry,manual_path);
#ifdef XQ_NATIVE_COACH
        /* recognize has returned and freed its per-shot buffers. A timeout
         * can still leave accepted AXI traffic draining: never acknowledge
         * reuse unless every submitted V321 job proved DONE with BUSY clear. */
        if(!xqcoach_driver_quiescent()){
            fputs("XQ_COACH_DRAIN_UNPROVEN no_release_ack=1\n",stderr);rc=2;break;
        }
        if(stop_requested)break; /* Parent must waitpid; no cancellation ACK. */
        if(!cancelled(NULL) && !result_packet(out_path,(uint64_t)token,fid,crc,backend,status,&result,boxes,corners)){rc=2;break;}
        if(!serve){rc=status?1:0;break;}
        while(!stop_requested && !access(request_file,F_OK)){const struct timespec t={0,100000000};nanosleep(&t,NULL);}
        if(stop_requested)break;
        /* Release ACK also follows ordinary result consumption. It closes
         * cancellation-vs-result races and binds reuse to the old identity.
         * The client must wait for this packet AND IDLE before creating B. */
        if(!result_packet(out_path,(uint64_t)token,fid,crc,backend,XQCOACH_CANCELLED,&result,boxes,corners)){rc=2;break;}
        live_request=NULL;
        fputs(XQCOACH_IDLE,stdout);fflush(stdout);
#else
        if(!cancelled(NULL) && !result_packet(out_path,(uint64_t)token,fid,crc,driver?"rv32-driver-quantized-mac":backend,status,&result,boxes,corners)){rc=2;break;}
        if(!serve){rc=status?1:0;break;}
        while(!stop_requested && !access(request_file,F_OK)){const struct timespec t={0,100000000};nanosleep(&t,NULL);}
        live_request=NULL;
#endif
    }
done:
    for(unsigned i=0;i<3;i++)xqn_free(models[i]);
    free(rng);free(pixels);for(unsigned i=0;i<3;i++)xqm_linux_close(&mac[i]);
    if(check_file && fclose(check_file))rc=2;
    return rc;
}
