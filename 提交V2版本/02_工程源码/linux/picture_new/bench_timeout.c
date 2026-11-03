#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static unsigned long long seconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(125);return (unsigned long long)t.tv_sec;}
int main(int argc,char **argv)
{
    if(argc<3)return 125;
    char *end;unsigned long limit=strtoul(argv[1],&end,10);
    if(*end || !limit || limit>86400)return 125;
    pid_t child=fork();if(child<0)return 125;
    if(!child){setpgid(0,0);execvp(argv[2],argv+2);perror("execvp");_exit(127);}
    setpgid(child,child);
    unsigned long long until=seconds()+limit;int timed=0,killed=0,status;
    for(;;){
        pid_t r=waitpid(child,&status,WNOHANG);
        if(r==child)return timed?124:WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
        if(r<0 && errno!=EINTR)return 125;
        if(seconds()>=until){
            if(!timed){kill(-child,SIGTERM);timed=1;until=seconds()+5;}
            else if(!killed){kill(-child,SIGKILL);killed=1;}
        }
        struct timespec nap={0,100000000};nanosleep(&nap,NULL);
    }
}
