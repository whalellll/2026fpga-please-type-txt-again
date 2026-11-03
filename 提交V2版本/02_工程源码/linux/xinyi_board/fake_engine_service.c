#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
int main(void)
{
    const char *mode=getenv("XY_ENGINE_TEST");if(!mode)return 2;
    FILE *out=fdopen(3,"w");if(!out)return 2;
    setvbuf(out,NULL,_IOLBF,0);
    if(!strcmp(mode,"exit"))return 0;
    if(!strcmp(mode,"unsolicited")){fputs("XQ_ENGINE_RESULT_V1 garbage\n",out);goto idle;}
    fputs("XQ_ENGINE_READY_V1\n",out);
    char line[256];
    while(fgets(line,sizeof(line),stdin)){
        unsigned token,revision,crc,nodes;
        if(sscanf(line,"XQ_ENGINE_REQUEST_V1 %u %u %x %u",&token,&revision,&crc,&nodes)!=4)return 2;
        if(!strcmp(mode,"hang"))goto idle;
        if(!strcmp(mode,"malformed")){fputs("WRONG\n",out);goto idle;}
        if(!strcmp(mode,"long-line")){for(unsigned i=0;i<700;i++)fputc('A',out);fputc('\n',out);goto idle;}
        token+=!strcmp(mode,"wrong-token");revision+=!strcmp(mode,"wrong-revision");crc+=!strcmp(mode,"wrong-crc");
        fprintf(out,"XQ_ENGINE_RESULT_V1 %u %u %08x 1 %s 120 128 500 200 300 123000 1\n",
                token,revision,crc,!strcmp(mode,"illegal")?"a0a9":strstr(line," b ")?"b9c7":"h2e2");
    }
    return 0;
idle:
    for(;;){struct timespec t={0,10000000};nanosleep(&t,NULL);}
}
