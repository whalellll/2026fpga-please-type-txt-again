/* Reconstruct a checked RAM payload from a read-only base and copy/literal
 * records. Never patch an executable in place or write SD/Flash. */
#define _POSIX_C_SOURCE 200809L
#include "crc32_fast.h"
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static int word(FILE *f,uint32_t *out)
{
    unsigned char b[4];if(fread(b,1,4,f)!=4)return 0;
    *out=(uint32_t)b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;return 1;
}
int main(int argc,char **argv)
{
    FILE *base=NULL,*patch=NULL,*out=NULL;int fd=-1,rc=1,created=0;
    uint32_t oldbytes,oldcrc,newbytes,newcrc,actual=0xffffffffu,got=0xffffffffu,written=0;
    unsigned char data[4096],magic[8];
    if(argc!=4 || (strncmp(argv[3],"/tmp/",5) && strncmp(argv[3],"/run/",5)) ||
       strstr(argv[3],"..") || !strcmp(argv[1],argv[3]) || !strcmp(argv[2],argv[3]))return 2;
    base=fopen(argv[1],"rb");patch=fopen(argv[2],"rb");if(!base || !patch)goto done;
    if(fread(magic,1,8,patch)!=8 || memcmp(magic,"XQPATCH1",8) ||
       !word(patch,&oldbytes) || !word(patch,&oldcrc) || !word(patch,&newbytes) || !word(patch,&newcrc) ||
       !oldbytes || oldbytes>16u*1024u*1024u || !newbytes || newbytes>16u*1024u*1024u)goto done;
    for(uint32_t at=0;at<oldbytes;) {
        size_t n=oldbytes-at<sizeof(data)?oldbytes-at:sizeof(data);
        if(fread(data,1,n,base)!=n)goto done;
        actual=crc32_fast(actual,data,(uint32_t)n);at+=(uint32_t)n;
    }
    if(fgetc(base)!=EOF || ferror(base) || (actual^0xffffffffu)!=oldcrc)goto done;
    fd=open(argv[3],O_WRONLY|O_CREAT|O_EXCL,0700);if(fd<0)goto done;
    created=1;out=fdopen(fd,"wb");if(!out)goto done;fd=-1;
    while(written<newbytes) {
        int op=fgetc(patch);uint32_t n,offset=0;
        if((op!=0 && op!=1) || !word(patch,&n) || !n || n>newbytes-written)goto done;
        if(op==0 && (!word(patch,&offset) || offset>oldbytes || n>oldbytes-offset || fseek(base,(long)offset,SEEK_SET)))goto done;
        while(n) {
            size_t chunk=n<sizeof(data)?n:sizeof(data);
            if(fread(data,1,chunk,op?patch:base)!=chunk || fwrite(data,1,chunk,out)!=chunk)goto done;
            got=crc32_fast(got,data,(uint32_t)chunk);written+=(uint32_t)chunk;n-=(uint32_t)chunk;
        }
    }
    if(fgetc(patch)!=EOF || ferror(patch) || (got^0xffffffffu)!=newcrc)goto done;
    if(fclose(out)){out=NULL;goto done;}out=NULL;rc=0;
done:
    if(base)fclose(base);
    if(patch)fclose(patch);
    if(out)fclose(out);
    if(fd>=0)close(fd);
    if(rc && created)unlink(argv[3]);
    printf("XQ_RAM_PATCH_%s bytes=%u\n",rc?"FAIL":"PASS",written);return rc;
}
