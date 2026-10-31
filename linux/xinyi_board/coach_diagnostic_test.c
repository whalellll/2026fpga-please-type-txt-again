/* Exercise the real child-pipe drain and privacy filter; no models/hardware. */
#include "coach_task.c"
#include <assert.h>
static void feed(xy_coach_task *t,int fd,const char *text)
{size_t n=strlen(text);assert(write(fd,text,n)==(ssize_t)n);assert(drain_pipe(t));}
int main(void)
{
    int input[2],output[2];assert(!pipe(input) && !pipe(output));
    assert(!fcntl(input[0],F_SETFL,O_NONBLOCK));
    fflush(stdout);int saved=dup(STDOUT_FILENO);assert(saved>=0);
    assert(dup2(output[1],STDOUT_FILENO)>=0);close(output[1]);
    xy_coach_task t={0};t.pipefd=input[0];t.state=ACTIVE;
    feed(&t,input[1],"XQ_NATIVE_STAGE board_done ms=1 jobs=44\n"); /* No READY. */
    feed(&t,input[1],"XQ_COACH_READY models=3 backend=" XQCOACH_BACKEND " stateless=1 EXPERIMENTAL\n");
    t.state=IDLE;
    feed(&t,input[1],"XQ_NATIVE_STAGE board_done ms=1 jobs=44\n"); /* Not active. */
    t.state=ACTIVE;
    feed(&t,input[1],"XQ_NATIVE_STAGE board_done ms=123 jobs=44\n"
        "XQ_NATIVE_STAGE detector_done ms=567 jobs=98 proposals=300\n"
        "XQ_NATIVE_STAGE classifier_done ms=890 fixed=32\n"
        "XQ_NATIVE_RECOGNITION status=5 models_loaded=3 executed_mask=7 cpu_reference=0 board_ms=123 SECRET_SYNTHETIC\n"
        "XQ_NATIVE_STAGE board_done ms=1 jobs=44 SECRET_SYNTHETIC\n"
        "XQ_NATIVE_STAGE board_done ms=99999999 jobs=44\n"
        "XQ_NATIVE_STAGE board_done ms=-1 jobs=44\n"
        "XQ_NATIVE_STAGE detector_done ms=1 jobs=98 proposals=301\n"
        "XQ_NATIVE_STAGE classifier_done ms=1 fixed=32 SECRET_SYNTHETIC\n"
        "XQ_NATIVE_RECOGNITION status=50 models_loaded=3 executed_mask=7 cpu_reference=0 board_ms=1\n"
        "SECRET_SYNTHETIC\n");
    feed(&t,input[1],"XQ_NATIVE_PROFILE prepare_ms=1 graph_ms=200 ioctl_ms=100 post_ms=2 refine_ms=3 assign_ms=4\n"
        "XQ_NATIVE_PROFILE prepare_ms=1 graph_ms=20 ioctl_ms=100 post_ms=2 refine_ms=3 assign_ms=4\n"
        "XQ_NATIVE_PROFILE prepare_ms=1 graph_ms=200 ioctl_ms=100 post_ms=2 refine_ms=3 assign_ms=4 SECRET_SYNTHETIC\n");
    char large[1200];memset(large,'x',sizeof(large));large[sizeof(large)-2]='\n';large[sizeof(large)-1]=0;
    feed(&t,input[1],large);
    fflush(stdout);assert(dup2(saved,STDOUT_FILENO)>=0);close(saved);
    char captured[2048];ssize_t size=read(output[0],captured,sizeof(captured)-1);assert(size>0);captured[size]=0;
    assert(strstr(captured,"phase=board elapsed_ms=123 jobs=44\n"));
    assert(strstr(captured,"phase=detector elapsed_ms=567 jobs=98 proposals=300\n"));
    assert(strstr(captured,"phase=classifier elapsed_ms=890 candidates=32\n"));
    assert(strstr(captured,"native_status=5 executed_mask=7 cpu_reference=0\n"));
    assert(!strstr(captured,"SECRET_SYNTHETIC") && !strstr(captured,"XQ_NATIVE"));
    assert(strstr(captured,"XINYI_COACH_PROFILE prepare_ms=1 graph_ms=200 ioctl_ms=100 post_ms=2 refine_ms=3 assign_ms=4\n"));
    unsigned lines=0;for(ssize_t i=0;i<size;++i)lines+=captured[i]=='\n';assert(lines==5);
    close(input[0]);close(input[1]);close(output[0]);
    puts("COACH_REAL_PIPE_STAGE_FILTER_ONLY_COUNTERS_NO_LIVE_TEXT_PASS_NOT_BOARD");return 0;
}
