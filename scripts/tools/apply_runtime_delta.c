/* RAM-only diagnostics: reconstruct an exact ELF from a verified old ELF.
 * The caller must SHA-256 both inputs and the final output before execution.
 * Never overwrites inputs or an existing output. No device or SD access. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>
#include <string.h>

static int exact_read(int fd,void *buffer,size_t bytes)
{
    unsigned char *p=buffer;
    while(bytes){ssize_t n=read(fd,p,bytes);if(n<0&&errno==EINTR)continue;if(n<=0)return 0;p+=n;bytes-=(size_t)n;}
    return 1;
}
static int exact_write(int fd,const void *buffer,size_t bytes)
{
    const unsigned char *p=buffer;
    while(bytes){ssize_t n=write(fd,p,bytes);if(n<0&&errno==EINTR)continue;if(n<=0)return 0;p+=n;bytes-=(size_t)n;}
    return 1;
}
static uint32_t checksum(int fd,uint32_t bytes,int *ok)
{
    unsigned char buffer[4096];uint32_t crc=~0u;*ok=0;
    if(lseek(fd,0,SEEK_SET)!=0)return 0;
    while(bytes){uint32_t count=bytes>sizeof(buffer)?sizeof(buffer):bytes;if(!exact_read(fd,buffer,count))return 0;
        for(uint32_t i=0;i<count;i++){crc^=buffer[i];for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&-(crc&1u));}bytes-=count;}
    *ok=1;return ~crc;
}
static int copy_bytes(int from,int to,uint32_t count)
{
    unsigned char buffer[4096];
    while(count){uint32_t n=count>sizeof(buffer)?sizeof(buffer):count;if(!exact_read(from,buffer,n)||!exact_write(to,buffer,n))return 0;count-=n;}
    return 1;
}
int main(int argc,char **argv)
{
    int old=-1,patch=-1,out=-1,rc=2,ok;struct stat st;uint32_t h[7],op[4],cursor=0;
    if(argc!=4)return 2;
    old=open(argv[1],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);patch=open(argv[2],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(old<0||patch<0||!exact_read(patch,h,sizeof(h))||h[0]!=0x31505958u||!h[1]||!h[2]||h[1]>2097152u||h[2]>2097152u||h[5]>131072u||!h[6]||h[6]>4096u)goto done;
    if(fstat(old,&st)||!S_ISREG(st.st_mode)||st.st_size!=h[1])goto done;
    if(fstat(patch,&st)||!S_ISREG(st.st_mode)||st.st_size!=(off_t)(28u+16u*h[6]+h[5]))goto done;
    if(checksum(old,h[1],&ok)!=h[3]||!ok)goto done;
    /* Validate the complete copy plan before creating any output. */
    for(uint32_t i=0;i<h[6];i++){
        if(!exact_read(patch,op,sizeof(op))||op[0]>1u||!op[3]||op[2]!=cursor||op[3]>h[2]-cursor)goto done;
        uint32_t limit=op[0]?h[5]:h[1];if(op[1]>limit||op[3]>limit-op[1])goto done;cursor+=op[3];
    }
    if(cursor!=h[2])goto done;
    out=open(argv[3],O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0700);if(out<0)goto done;
    for(uint32_t i=0;i<h[6];i++){
        if(lseek(patch,28u+16u*i,SEEK_SET)<0||!exact_read(patch,op,sizeof(op)))goto done;
        int source=op[0]?patch:old;off_t offset=op[1]+(op[0]?28u+16u*h[6]:0u);
        if(lseek(source,offset,SEEK_SET)!=offset||!copy_bytes(source,out,op[3]))goto done;
    }
    if(checksum(out,h[2],&ok)!=h[4]||!ok||fsync(out))goto done;
    static const char message[]="EXACT_RUNTIME_DELTA_APPLIED_NOT_SD_DELIVERY\n";
    if(!exact_write(1,message,sizeof(message)-1))goto done;
    rc=0;
done:
    if(out>=0)close(out);
    if(patch>=0)close(patch);
    if(old>=0)close(old);
    return rc;
}
