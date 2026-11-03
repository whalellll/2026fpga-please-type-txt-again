/* Volatile /run uploads only. The packet state machine is the same bounded
 * 64 KiB CRC16 receiver used by the tested PN03 installer. No SD/MMIO access. */
#define _GNU_SOURCE
#include "xmodem_linux/soc.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

uint32_t pn03_xmodem_receive(uint32_t,uint32_t);
_Static_assert(sizeof(uintptr_t)==4,"Linux RAM receiver requires RV32");
static volatile sig_atomic_t cancelled;
static unsigned char incoming[4096];
static size_t next_byte,buffered;
static uint64_t whole_deadline;
static uint64_t microseconds(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000000u+(unsigned)t.tv_nsec/1000u;
}
uint32_t read_mtime_ticks32(void){return (uint32_t)microseconds();}
static void stop(int sig){(void)sig;cancelled=1;}
int console_getc_timeout(uint32_t ticks)
{
    uint64_t end=microseconds()+ticks;
    while(!cancelled && microseconds()<whole_deadline){
        if(next_byte<buffered)return incoming[next_byte++];
        uint64_t now=microseconds();
        if(now>=end)return -1;
        struct pollfd p={STDIN_FILENO,POLLIN,0};
        int wait=(int)((end-now+999u)/1000u);
        if(wait>1000)wait=1000;
        int ready=poll(&p,1,wait);
        if(ready<0){if(errno==EINTR)continue;return -1;}
        if(!ready)continue;
        ssize_t n=read(STDIN_FILENO,incoming,sizeof(incoming));
        if(n<0){if(errno==EINTR || errno==EAGAIN)continue;return -1;}
        if(!n)return -1;
        next_byte=0;buffered=(size_t)n;
    }
    return -1;
}
void console_putc(char c){if(write(STDOUT_FILENO,&c,1)!=1)cancelled=1;}
void console_puts(const char *p){while(*p)console_putc(*p++);}
static int write_all(int fd,const void *buffer,size_t bytes)
{
    const unsigned char *p=buffer;
    while(bytes){
        ssize_t n=write(fd,p,bytes);
        if(n<0 && errno==EINTR)continue;
        if(n<=0)return 0;
        p+=n;bytes-=(size_t)n;
    }
    return 1;
}
int main(int argc,char **argv)
{
    int fd=-1,rc=2,terminal_saved=0,created=0;
    char part[256],*end;struct termios saved,raw;
    struct stat st;struct statfs fs;
    unsigned char *memory=MAP_FAILED;
    setvbuf(stdout,NULL,_IONBF,0);
    if(argc!=3 || strncmp(argv[1],"/run/xinyi-",11) || strlen(argv[1])>180)return 2;
    for(const char *p=argv[1]+11;*p;p++)
        if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='.'||*p=='-'))return 2;
    errno=0;unsigned long bytes=strtoul(argv[2],&end,10);
    if(errno || *end || !bytes || bytes>4194304u || statfs("/run",&fs) ||
       (unsigned long)fs.f_type!=0x01021994u)return 2;
    if(!lstat(argv[1],&st) || errno!=ENOENT)return 2;
    if(snprintf(part,sizeof(part),"%s.part",argv[1])>=(int)sizeof(part))return 2;
    fd=open(part,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0700);
    if(fd<0)goto done;
    created=1;
    memory=mmap(NULL,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(memory==MAP_FAILED || tcgetattr(STDIN_FILENO,&saved))goto done;
    raw=saved;cfmakeraw(&raw);
    if(tcsetattr(STDIN_FILENO,TCSANOW,&raw))goto done;
    terminal_saved=1;
    struct sigaction a={0};a.sa_handler=stop;sigemptyset(&a.sa_mask);
    if(sigaction(SIGINT,&a,NULL)||sigaction(SIGTERM,&a,NULL)||sigaction(SIGHUP,&a,NULL))goto done;
    whole_deadline=microseconds()+600000000u;
    for(uint32_t offset=0;offset<(uint32_t)bytes;){
        uint32_t n=(uint32_t)bytes-offset;if(n>65536u)n=65536u;
        uint32_t padded=(n+1023u)&~1023u;
        printf("XINYI_LINUX_RX_CHUNK offset=%u bytes=%u\n",offset,n);
        if(pn03_xmodem_receive((uint32_t)(uintptr_t)memory,padded)!=padded ||
           cancelled || !write_all(fd,memory,n))goto done;
        offset+=n;
    }
    if(fsync(fd))goto done;
    if(close(fd)){fd=-1;goto done;}fd=-1;
    /* Atomic create-only publication, even if a name appears during RX. */
    if(link(part,argv[1]))goto done;
    if(unlink(part))goto done;
    created=0;rc=0;
done:
    if(terminal_saved)(void)tcsetattr(STDIN_FILENO,TCSANOW,&saved);
    if(memory!=MAP_FAILED)munmap(memory,65536);
    if(fd>=0)close(fd);
    if(created)unlink(part);
    printf(rc?"XINYI_LINUX_RAM_RX_FAIL no_sd_write=1\n":"XINYI_LINUX_RAM_RX_PASS bytes=%lu no_sd_write=1\n",bytes);
    return rc;
}
