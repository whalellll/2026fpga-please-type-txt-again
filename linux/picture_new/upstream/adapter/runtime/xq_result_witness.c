#define _POSIX_C_SOURCE 200809L
/* Diagnostic candidate only; excluded from the native worker build. */
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <unistd.h>
/* One atomic result publication only. No polling, inference or GUI writes.
 * Retain a hard link before the GUI unlinks its consumed result. All files
 * remain in ordinary /run RAM and are never part of a delivery package. */
int main(int argc,char **argv)
{
    char source[512],events[4096];struct stat st;char *end;int fd=-1,rc=2;
    if(argc!=4 || strncmp(argv[1],"/run/",5) || strncmp(argv[2],"/run/",5) ||
       strstr(argv[1],"..") || strstr(argv[2],".."))return 2;
    long seconds=strtol(argv[3],&end,10);
    if(*end || seconds<1 || seconds>900 ||
       snprintf(source,sizeof(source),"%s/result.txt",argv[1])>=(int)sizeof(source) ||
       !lstat(argv[2],&st) || errno!=ENOENT)return 2;
    fd=inotify_init1(IN_CLOEXEC);if(fd<0)goto done;
    if(inotify_add_watch(fd,argv[1],IN_MOVED_TO)<0)goto done;
    puts("RESULT_WITNESS_READY");fflush(stdout);
    struct pollfd p={fd,POLLIN,0};
    int ready=poll(&p,1,(int)seconds*1000);
    if(ready<=0){rc=3;goto done;}
    ssize_t got=read(fd,events,sizeof(events));
    if(got<=0)goto done;
    for(size_t offset=0;offset+(size_t)sizeof(struct inotify_event)<=(size_t)got;){
        struct inotify_event *event=(void *)(events+offset);
        if(event->len && !strcmp(event->name,"result.txt") && (event->mask&IN_MOVED_TO)) {
            if(!lstat(source,&st) && S_ISREG(st.st_mode) && link(source,argv[2])==0){rc=0;break;}
            rc=4;break;
        }
        offset+=sizeof(*event)+event->len;
    }
done:
    if(fd>=0)close(fd);
    printf("RESULT_WITNESS_EXIT=%d\n",rc);return rc;
}
