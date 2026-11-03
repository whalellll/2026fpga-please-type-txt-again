/* Explicit runtime integration fixtures: no camera, DDR, MMIO or FPGA access. */
#include "runtime.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

struct xy_platform { uint32_t token;int active,cancelled,pending,pinned,releases;xy_platform_event event; };
struct xy_coach_task {
    uint32_t token;int ready,active,consumed,cancelled,pending;
    xy_coach_event event;xqcoach_result result;
};
static struct xy_platform platform;
static struct xy_coach_task coach;
static int accelerator_busy;
static int precise_scores;
static unsigned geometry_native_status=2;
static unsigned client_opens,client_closes;
static const uint32_t synthetic_frame[1280u*720u/2u];

xy_platform *runtime_fixture_reset(void)
{memset(&platform,0,sizeof(platform));memset(&coach,0,sizeof(coach));accelerator_busy=0;precise_scores=0;geometry_native_status=2;client_opens=client_closes=0;return &platform;}
unsigned runtime_fixture_client_opens(void){return client_opens;}
unsigned runtime_fixture_client_closes(void){return client_closes;}
void runtime_fixture_exact_scores(int mode){precise_scores=mode;}
void runtime_fixture_geometry_stage(unsigned status){assert(status==2 || status==5 || status==6);geometry_native_status=status;}
void runtime_fixture_busy(int busy){accelerator_busy=busy;}
int runtime_fixture_pinned(void){return platform.pinned;}
int runtime_fixture_releases(void){return platform.releases;}
int runtime_fixture_camera_cancelled(void){return platform.cancelled;}
int runtime_fixture_coach_cancelled(void){return coach.cancelled;}
void runtime_fixture_camera_done(int cancelled)
{
    assert(platform.active && !platform.pending);
    platform.event=(xy_platform_event){platform.token,XY_PLATFORM_CAPTURE,
        cancelled?XY_PLATFORM_CANCELLED:XY_PLATFORM_OK,0,1,1,0};platform.pending=1;
}
void runtime_fixture_consumed(void){assert(coach.active);coach.consumed=1;}
static xqcoach_candidate candidate(unsigned cid,unsigned file,unsigned rank,float score)
{
    return (xqcoach_candidate){(uint8_t)cid,(uint8_t)file,(uint8_t)rank,
        (uint16_t)floor((double)score*1000.),score,10.f+file*50,10.f+rank*50,30.f+file*50,30.f+rank*50};
}
void runtime_fixture_coach_done(int kind)
{
    assert(coach.active && !coach.pending);
    coach.event=(xy_coach_event){(xy_coach_event_type)kind,coach.token,0,coach.consumed,kind!=XY_COACH_UNDRAINED,1,0};
    if(kind==XY_COACH_RESULT || kind==XY_COACH_PARTIAL){
        static const unsigned back[9]={4,3,2,1,0,1,2,3,4};
        xqcoach_result result={0},parsed={0};char *wire=malloc(XQCOACH_PACKET_BYTES);unsigned remote=99,n=0;
        assert(wire && xqcoach_identity_init(&result.identity,coach.token,81,0x52c44a22));
        const double corners[4][2]={{100,100},{900,100},{900,600},{100,600}};
        memcpy(result.corners,corners,sizeof(corners));
        for(unsigned i=0;i<9;i++){
            result.candidates[n++]=candidate(back[i],i,0,.875f);
            result.candidates[n++]=candidate(back[i]+7,i,9,.875f);
        }
        for(unsigned i=0;i<9;i+=2){
            result.candidates[n++]=candidate(6,i,3,.875f);
            result.candidates[n++]=candidate(13,i,6,.875f);
        }
        result.candidates[n++]=candidate(5,1,2,.875f);result.candidates[n++]=candidate(5,7,2,.875f);
        result.candidates[n++]=candidate(12,1,7,.875f);result.candidates[n++]=candidate(12,7,7,.875f);
        assert(n==32);
        if(precise_scores==1){
            result.candidates[0]=candidate(4,0,0,.8751f);
            result.candidates[16]=candidate(4,8,0,.8758f);
            result.candidates[n++]=candidate(4,0,4,.8759f);
        }else if(precise_scores==2){
            result.candidates[6]=candidate(1,3,0,.8751f);
            result.candidates[n++]=candidate(0,3,0,.8759f);
        }else result.candidates[n++]=candidate(4,0,4,.125f); /* Third red rook. */
        while(n<300)result.candidates[n++]=candidate(4,0,0,.0625f); /* Same-cell extras. */
        result.count=n;size_t bytes;
        if(kind==XY_COACH_PARTIAL){
            result.estimated=1;result.status=5;
            result.candidates[n-1]=candidate(2,4,7,.75f); /* Delete impossible elephant before legal recommendation. */
            bytes=xqcoach_encode_partial(&result,wire,XQCOACH_PACKET_BYTES);assert(bytes);
            assert(xqcoach_parse_result(wire,bytes,&result.identity,&parsed,&remote)==XQCOACH_INVALID && remote==99);
            assert(xqcoach_parse_partial(wire,bytes,&result.identity,&parsed)==XQCOACH_ACCEPTED);
            coach.event.remote_status=5;
        }else{
            bytes=xqcoach_encode_result(&result,wire,XQCOACH_PACKET_BYTES);assert(bytes);
            assert(xqcoach_parse_result(wire,bytes,&result.identity,&parsed,&remote)==XQCOACH_ACCEPTED && !remote);
        }
        free(wire);coach.result=parsed;
    }else if(kind==XY_COACH_GEOMETRY_REJECT){
        xqcoach_result rejected={0},previous,out;char *wire=malloc(XQCOACH_PACKET_BYTES);unsigned remote=99;
        assert(wire && xqcoach_identity_init(&rejected.identity,coach.token,81,0x52c44a22));
        rejected.status=xqcoach_native_status(geometry_native_status);
        size_t bytes=xqcoach_encode_result(&rejected,wire,XQCOACH_PACKET_BYTES);assert(bytes);
        memset(&previous,0x5a,sizeof(previous));out=previous;
        assert(xqcoach_parse_result(wire,bytes,&rejected.identity,&out,&remote)==XQCOACH_REJECTED);
        assert(remote==5 && !memcmp(&out,&previous,sizeof(out)));free(wire);coach.event.remote_status=remote;
    }
    coach.pending=1;
}
void runtime_fixture_reaped_cancel(void)
{
    runtime_fixture_coach_done(XY_COACH_CANCELLED);
    coach.ready=0;coach.event.resident_ready=0;coach.event.worker_reaped=1;
}
void runtime_fixture_worker_ready(void)
{
    assert(client_opens==2 && !coach.ready && !coach.pending && !coach.active);
    coach.ready=1;coach.pending=1;coach.event=(xy_coach_event){XY_COACH_READY,0,0,0,1,1,0};
}
int xy_platform_capture_start(xy_platform *p,uint32_t token)
{assert(p==&platform);if(p->active || p->pinned)return 0;p->active=1;p->token=token;p->cancelled=0;return 1;}
int xy_platform_cancel(xy_platform *p,uint32_t token)
{if(!p->active || p->token!=token)return 0;p->cancelled=1;return 1;}
int xy_platform_poll(xy_platform *p,xy_platform_event *event)
{if(!p->pending)return 0;*event=p->event;p->pending=p->active=0;return 1;}
int xy_platform_frame_acquire(xy_platform *p,uint32_t token,xy_platform_frame *frame)
{
    if(p->token!=token || p->active || p->pinned)return 0;
    p->pinned=1;*frame=(xy_platform_frame){token,81,0x52c44a22,1,synthetic_frame,sizeof(synthetic_frame)};return 1;
}
int xy_platform_frame_release(xy_platform *p,uint32_t token)
{if(!p->pinned || p->token!=token || !coach.consumed)return 0;p->pinned=0;p->releases++;return 1;}
uint32_t xy_platform_cpu_hz(const xy_platform *p){(void)p;return XINYI_CPU_HZ;}
int xy_accelerator_open(xy_accelerator *a){a->fd=-1;a->regs=NULL;return 1;}
int xy_accelerator_idle(const xy_accelerator *a){(void)a;return !accelerator_busy;}
void xy_accelerator_close(xy_accelerator *a){a->fd=-1;a->regs=NULL;}
xy_coach_task *xy_coach_open(const xy_coach_config *config)
{
    assert(config->vision_drained);client_opens++;memset(&coach,0,sizeof(coach));
    coach.ready=client_opens==1; /* Reopened client explicitly waits for READY. */
    return &coach;
}
int xy_coach_ready(const xy_coach_task *c){return c->ready && !c->active;}
int xy_coach_start(xy_coach_task *c,uint32_t token,const xy_platform_frame *frame)
{
    if(!xy_coach_ready(c) || !frame || frame->token!=token || frame->rgb565!=synthetic_frame)return 0;
    c->active=1;c->token=token;c->consumed=c->cancelled=0;return 1;
}
int xy_coach_consumed(xy_coach_task *c,uint32_t token){return c->token==token && c->consumed;}
int xy_coach_cancel(xy_coach_task *c,uint32_t token)
{if(!c->active || c->token!=token)return 0;c->cancelled=1;return 1;}
int xy_coach_poll(xy_coach_task *c,xy_coach_event *event,xqcoach_result *out)
{
    if(!c->pending)return 0;
    *event=c->event;if(event->type==XY_COACH_RESULT || event->type==XY_COACH_PARTIAL)*out=c->result;
    c->pending=c->active=0;return 1;
}
int xy_coach_close(xy_coach_task *c){assert(!c->active && !platform.pinned);client_closes++;return 1;}
