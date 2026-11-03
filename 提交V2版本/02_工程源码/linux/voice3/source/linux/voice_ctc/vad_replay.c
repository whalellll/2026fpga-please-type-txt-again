#include "xqvoice_capture.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
    int16_t pcm[64000],chunk[160]={0};xqvoice_capture_state state;FILE *f;unsigned i;size_t n;int rc=0;
    if(argc!=3)return 1;
    f=fopen(argv[1],"rb");if(!f)return 2;
    xqvoice_capture_init(&state,pcm,64000);
    for(i=0;i<30;i++)xqvoice_capture_feed(&state,chunk);
    while(!state.done && (n=fread(chunk,2,160,f))>0) {
        if(n<160)memset(chunk+n,0,(160-n)*2);
        rc=xqvoice_capture_feed(&state,chunk);
    }
    fclose(f);memset(chunk,0,sizeof(chunk));
    for(i=0;!state.done && i<100;i++)rc=xqvoice_capture_feed(&state,chunk);
    if(rc!=2){fprintf(stderr,"VAD rc=%d\n",rc);return 3;}
    f=fopen(argv[2],"wb");if(!f)return 2;
    if(fwrite(pcm,2,state.count,f)!=state.count)return 4;
    return fclose(f)!=0;
}
