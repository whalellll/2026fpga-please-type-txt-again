#define _POSIX_C_SOURCE 200809L
#include "coach_protocol.h"
#include "crc32_fast.h"
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void pause_ms(void){struct timespec t={0,1000000};nanosleep(&t,NULL);}
static int frame_crc(uint32_t expected)
{
    unsigned char data[4096];uint32_t crc=0xffffffffu;size_t total=0,n;
    FILE *f=fopen("frame.rgb565","rb");if(!f)return 0;
    while((n=fread(data,1,sizeof(data),f))){total+=n;crc=crc32_fast(crc,data,(uint32_t)n);}
    int okay=!ferror(f) && total==1843200u && (crc^0xffffffffu)==expected;
    fclose(f);return okay;
}
int main(int argc,char **argv)
{
    if(argc!=6 || strcmp(argv[1],"--driver") || strcmp(argv[2],"--models") || strcmp(argv[4],"--serve"))return 2;
    const char *mode=strrchr(argv[3],'/');mode=mode?mode+1:argv[3];
    if(chdir(argv[5]))return 3;
    if(!strcmp(mode,"startup-exit"))return 7;
    if(!strcmp(mode,"stall"))signal(SIGTERM,SIG_IGN);
    puts("XQ_COACH_READY models=3 backend=" XQCOACH_BACKEND " stateless=1 EXPERIMENTAL");
    fputs(XQCOACH_IDLE,stdout);fflush(stdout);
    unsigned requests=0;
    for(;;){
        char request[256];FILE *f=fopen("request.txt","r");
        if(!f){pause_ms();continue;}
        size_t bytes=fread(request,1,sizeof(request),f);fclose(f);
        xqcoach_identity identity;if(!xqcoach_parse_request(request,bytes,&identity) || !frame_crc(identity.crc))return 4;
        ++requests;
        if(!strcmp(mode,"stall") || !strcmp(mode,"cancel")){
            f=fopen("result.txt.part","w");if(!f)return 6;fclose(f);
        }
        if(!strcmp(mode,"stall"))for(;;)pause_ms();
        xqcoach_result r={0};r.identity=identity;
        if(!strcmp(mode,"cancel")){
            while(!access("request.txt",F_OK))pause_ms();
        }else{
            r.count=300;
            for(unsigned i=0;i<4;++i){r.corners[i][0]=(i==1 || i==2)?1100:100;r.corners[i][1]=i>=2?650:50;}
            for(unsigned i=0;i<r.count;++i)r.candidates[i]=(xqcoach_candidate){6,(uint8_t)(i%9),3,750,.75f,20,30,70,80};
            if(!strcmp(mode,"geometry") || (!strcmp(mode,"geometry-once") && requests==1)){r.status=5;r.count=0;}
            if(!strcmp(mode,"status6")){r.status=6;r.count=0;}
            if(!strcmp(mode,"unsolicited9")){r.status=9;r.count=0;}
            int partial=(!strcmp(mode,"partial-once") || !strcmp(mode,"estimated-once")) && requests==1;
            if(partial){
                r.status=5;r.count=3;r.estimated=!strcmp(mode,"estimated-once");
                r.candidates[0]=(xqcoach_candidate){0,4,0,750,.75f,20,30,70,80};
                r.candidates[1]=(xqcoach_candidate){7,4,9,750,.75f,20,30,70,80};
                r.candidates[2]=(xqcoach_candidate){6,4,3,750,.75f,20,30,70,80};
                if(!r.estimated)for(unsigned i=0;i<r.count;i++)r.candidates[i].file=r.candidates[i].rank=255;
            }
            if(!strcmp(mode,"token"))++r.identity.token;
            if(!strcmp(mode,"frame"))++r.identity.frame;
            if(!strcmp(mode,"raw-crc"))++r.identity.crc;
            if(!strcmp(mode,"body-crc") || !strcmp(mode,"backend") || !strcmp(mode,"truncate")){
                char packet[XQCOACH_PACKET_BYTES];bytes=xqcoach_encode_result(&r,packet,sizeof(packet));if(!bytes)return 6;
                if(!strcmp(mode,"body-crc"))packet[bytes-2]^=1;
                if(!strcmp(mode,"backend")){char *p=strstr(packet,XQCOACH_BACKEND);if(!p)return 6;p[0]='x';}
                if(!strcmp(mode,"truncate"))--bytes;
                f=fopen("result.txt.part","w");if(!f)return 6;
                if(fwrite(packet,1,bytes,f)!=bytes || fclose(f) || rename("result.txt.part","result.txt"))return 6;
            }else if(partial?!xqcoach_write_partial_atomic("result.txt",&r):!xqcoach_write_result_atomic("result.txt",&r))return 5;
            while(!access("request.txt",F_OK))pause_ms();
        }
        memset(&r,0,sizeof(r));r.identity=identity;r.status=XQCOACH_CANCELLED;
        if(!xqcoach_write_result_atomic("result.txt",&r))return 8;
        fputs(XQCOACH_IDLE,stdout);fflush(stdout);
    }
}
