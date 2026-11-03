/* Protocol-only ASR child. No model, microphone or accelerator access. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <string.h>
static void result(unsigned id)
{
    printf("XQW1 RESULT %u 0 e9a9ace4ba8ce8bf9be4b889 request_us=9000000 cnn_us=10000 decode_us=1000 tail_valid=1 endpoint_to_result_us=20000 last_voice_to_result_us=470000 feature_tail_us=9000\n",id);
    printf("XQW1 IDLE %u\n",id);
}
int main(int argc,char **argv)
{
    char line[2300],kind,path[2050],mode[1025];unsigned id,active=0;
    (void)argv;if(argc!=5)return 2;setvbuf(stdout,NULL,_IOLBF,0);
    puts("XQW1 READY pid=1 model_loads=1 model_checks=1 mac_opens=0");
    while(fgets(line,sizeof(line),stdin)){
        if(sscanf(line,"XQW1 %c %u %2049s",&kind,&id,path)!=3)return 3;
        if(kind=='Q'){puts("XQW1 BYE");return 0;}
        if(kind=='C'){if(active==id){result(id);active=0;}continue;}
        size_t n=strlen(path);if(n%2u || n/2u>=sizeof(mode))return 4;
        for(size_t i=0;i<n;i+=2u){unsigned x;if(sscanf(path+i,"%2x",&x)!=1)return 5;mode[i/2u]=(char)x;}
        mode[n/2u]=0;active=id;printf("XQW1 STAGE %u LISTENING\n",id);
        if(!strcmp(mode,"idle"))continue;
        printf("XQW1 STAGE %u INFERENCING\n",id);result(id);active=0;
    }
    return 0;
}
