/* A changed measurement must not rewrite the unchanged title/background.
 * The protected header catches redundant stores even when final pixels match. */
#define _GNU_SOURCE
#include "../xinyi/xinyi_fb.c"
#include <assert.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static int microphone(void *unused,int on){(void)unused;(void)on;return 1;}
int main(void)
{
    long page=sysconf(_SC_PAGESIZE);assert(page>0);
    size_t bytes=(VIDEO_FB_FRAME_BYTES+(size_t)page-1)/(size_t)page*(size_t)page;
    uint16_t *pixels=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(pixels!=MAP_FAILED);xy_backend backend={.microphone=microphone};xy_app app;
    xy_app_init(&app,&backend);xy_fb_invalidate();xy_fb_render(&app,pixels);
    size_t header=300u*3840u/(size_t)page*(size_t)page;
    assert(!mprotect(pixels,header,PROT_READ));
    app.coremark_measured=1;app.coremark_cpu_hz=60000000;app.coremark_per_mhz=.4012345;
    strcpy(app.coremark_identity,"e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b");
    fflush(NULL);pid_t child=fork();assert(child>=0);
    if(!child){xy_fb_render(&app,pixels);_exit(0);}
    int status=0;assert(waitpid(child,&status,0)==child);
    int wrote=!WIFEXITED(status) || WEXITSTATUS(status)!=0;
    printf("R19_REAL_METRIC_HEADER_GUARD candidate=%u unchanged_header_write=%d signal=%d\n",XINYI_GUI_METRIC_DELTAS,wrote,WIFSIGNALED(status)?WTERMSIG(status):0);
#if XINYI_GUI_METRIC_DELTAS
    assert(!wrote);
#else
    assert(wrote && WIFSIGNALED(status) && WTERMSIG(status)==SIGSEGV);
#endif
    assert(!mprotect(pixels,header,PROT_READ|PROT_WRITE));assert(!munmap(pixels,bytes));
    return 0;
}
