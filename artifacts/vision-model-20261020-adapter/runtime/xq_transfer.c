#define _DEFAULT_SOURCE
#include "crc32_fast.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static void stop(int s){(void)s;stopped=1;}
static int transfer(int fd,void *data,size_t n,int writing)
{
    uint8_t *p=data;
    while(n && !stopped) {
        struct pollfd q={fd,writing?POLLOUT:POLLIN,0};
        ssize_t got;
        if(poll(&q,1,15000)<=0)return 0;
        got=writing?write(fd,p,n):read(fd,p,n);
        if(got<0 && errno==EINTR)continue;
        if(got<=0)return 0;
        p+=got;n-=(size_t)got;
    }
    return n==0;
}
int main(int argc,char **argv)
{
    struct termios old,raw;
    FILE *f=NULL;
    char temporary[512],header[128],*end;
    unsigned long length=0,expected=0;
    uint32_t crc=0xffffffffu;
    unsigned char buffer[1024];
    int receive,rc=1,changed=0;
    if(argc<3 || (strcmp(argv[1],"send") && strcmp(argv[1],"receive")) ||
       (strncmp(argv[2],"/run/",5) && strncmp(argv[2],"/tmp/",5)))return 2;
    receive=!strcmp(argv[1],"receive");
    if(receive) {
        if(argc!=5 || snprintf(temporary,sizeof(temporary),"%s.transfer",argv[2])>=(int)sizeof(temporary))return 2;
        length=strtoul(argv[3],&end,10);if(*end || !length || length>32u*1024u*1024u)return 2;
        expected=strtoul(argv[4],&end,16);if(*end || expected>UINT32_MAX)return 2;
        f=fopen(temporary,"wb");
    } else {
        if(argc!=3)return 2;
        f=fopen(argv[2],"rb");
        if(f) {
            size_t n;
            while((n=fread(buffer,1,sizeof(buffer),f))) {length+=(unsigned long)n;crc=crc32_fast(crc,buffer,(uint32_t)n);}
            if(ferror(f) || !length || length>32u*1024u*1024u){fclose(f);return 2;}
            rewind(f);expected=crc^0xffffffffu;crc=0xffffffffu;
        }
    }
    if(!f)return 2;
    if(tcgetattr(0,&old)){fclose(f);return 2;}
    raw=old;cfmakeraw(&raw);raw.c_cc[VMIN]=1;raw.c_cc[VTIME]=0;
    signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGHUP,stop);
    if(tcsetattr(0,TCSADRAIN,&raw))goto done;
    changed=1;
    snprintf(header,sizeof(header),"XQT1 %lu %08lx\n",length,expected);
    if(!transfer(1,header,strlen(header),1))goto done;
    for(unsigned long offset=0;offset<length;) {
        size_t n=length-offset<sizeof(buffer)?length-offset:sizeof(buffer);
        unsigned char ack=6;
        if(receive) {
            if(!transfer(0,buffer,n,0) || fwrite(buffer,1,n,f)!=n)goto done;
            crc=crc32_fast(crc,buffer,(uint32_t)n);
            if(!transfer(1,&ack,1,1))goto done;
        } else {
            if(fread(buffer,1,n,f)!=n || !transfer(1,buffer,n,1) || !transfer(0,&ack,1,0) || ack!=6)goto done;
        }
        offset+=(unsigned long)n;
    }
    if(receive && (crc^0xffffffffu)!=expected)goto done;
    if(fclose(f)){f=NULL;goto done;}f=NULL;
    if(receive && rename(temporary,argv[2]))goto done;
    rc=0;
done:
    if(f)fclose(f);
    if(receive && rc)unlink(temporary);
    if(changed){tcdrain(1);tcsetattr(0,TCSADRAIN,&old);}
    printf("\nXQ_TRANSFER_EXIT=%d\n",rc);fflush(stdout);
    return rc;
}
