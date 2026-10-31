#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void result(unsigned id,int code,const char *text) {
    printf("XQW1 RESULT %u %d ",id,code);
    if(!*text)putchar('-');
    for(const unsigned char *p=(const unsigned char *)text;*p;p++)printf("%02x",*p);
    puts(" model_loads=1 model_checks=1 mac_opens=0");
}
int main(int argc,char **argv) {
    char line[2300],kind,path[2050],mode[1025];unsigned id,active=0;int held=0,late=0;
    (void)argv;if(argc!=5)return 2;
    setvbuf(stdout,NULL,_IOLBF,0);
    fputs("VOICE2_SMALL_ACCEL_ACTIVE device=/dev/pango-voice0 lanes=4 strict=1\n",stderr);
    puts("XQW1 READY pid=1 model_loads=1 model_checks=1 mac_opens=0");
    while(fgets(line,sizeof(line),stdin)) {
        if(sscanf(line,"XQW1 %c %u %2049s",&kind,&id,path)!=3)return 3;
        if(kind=='Q'){puts("XQW1 BYE");return 0;}
        if(kind=='C') {
            if(active==id) {
                if(!held)result(id,late?0:26,late?"马二进三":"");
                printf("XQW1 IDLE %u\n",id);active=0;held=0;
            }
            continue;
        }
        size_t n=strlen(path);if(n%2u || n/2u>=sizeof(mode))return 4;
        for(size_t i=0;i<n;i+=2u){unsigned x;if(sscanf(path+i,"%2x",&x)!=1)return 5;mode[i/2u]=(char)x;}
        mode[n/2u]=0;active=id;held=late=0;
        printf("XQW1 STAGE %u LISTENING\n",id);
        if(!strcmp(mode,"idle"))continue;
        if(!strcmp(mode,"late")){late=1;continue;}
        if(!strcmp(mode,"crash"))return 7;
        if(!strcmp(mode,"overflow")){for(unsigned i=0;i<2200;i++)putchar('x');putchar('\n');continue;}
        if(!strcmp(mode,"bad")){puts("unexpected output");continue;}
        printf("XQW1 STAGE %u INFERENCING\n",id);
        if(!strcmp(mode,"illegal"))result(id,0,"帅五进九");
        else if(!strcmp(mode,"wrongside"))result(id,0,"卒一进一");
        else if(!strcmp(mode,"empty"))result(id,0,"");
        else if(!strcmp(mode,"failure"))result(id,-20,"");
        else if(!strcmp(mode,"ambiguous"))result(id,0,"车九平八");
        else result(id,0,"马二进三");
        if(!strcmp(mode,"hold")){held=1;continue;}
        printf("XQW1 IDLE %u\n",id);active=0;
    }
    return 0;
}
