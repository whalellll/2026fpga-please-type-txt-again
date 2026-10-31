#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int main(int argc,char **argv)
{
    uint32_t *pixels=NULL,row[160];struct stat st;int input=-1,output=-1,rc=2;size_t used=0;
    if(argc!=3 || strncmp(argv[1],"/run/",5) || strncmp(argv[2],"/run/",5))return 2;
    input=open(argv[1],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(input<0 || fstat(input,&st) || st.st_size!=1843200)goto done;
    pixels=malloc(1843200);if(!pixels)goto done;
    while(used<1843200){ssize_t n=read(input,(uint8_t *)pixels+used,1843200-used);if(n<=0)goto done;used+=(size_t)n;}
    output=open(argv[2],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(output<0)goto done;
    for(unsigned y=0;y<720;y+=4){
        for(unsigned x=0;x<320;x+=2){
            unsigned a=y*1280+4*x,b=a+4;
            row[x/2]=((pixels[a/2]>>(16*(a%2)))&65535u)|(((pixels[b/2]>>(16*(b%2)))&65535u)<<16);
        }
        used=0;while(used<sizeof(row)){ssize_t n=write(output,(const uint8_t *)row+used,sizeof(row)-used);if(n<=0)goto done;used+=(size_t)n;}
    }
    rc=0;(void)write(1,"FRAME_THUMB_PASS\n",17);
done:
    if(input>=0)close(input);
    if(output>=0){close(output);if(rc)unlink(argv[2]);}
    free(pixels);return rc;
}
