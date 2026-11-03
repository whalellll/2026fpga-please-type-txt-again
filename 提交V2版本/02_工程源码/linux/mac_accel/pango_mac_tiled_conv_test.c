/* Layer probe using the existing private-shadow dense ABI. No /dev/mem path.
 * DCT1 input: 20-byte LE header (magic,version,count,payload_size,CRC32),
 * then cases: name[32], 8 u32 geometry/shift fields, I32 bias, NHWC S8 input,
 * OIHW S8 weights, NHWC I32 golden, NHWC S8 golden. All parsing precedes RUN.
 * DENSE_CONV_EMULATED is a separate host build; device builds never fall back.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include "pango_mac_uapi.h"

#define INPUT_OFFSET 0u
#define WEIGHT_OFFSET 8192u
#define OUTPUT_OFFSET 73728u
#define SCRATCH_NEEDED 90112u
#define FILE_LIMIT (16u*1024u*1024u+20u)

struct probe_case {
    char name[33];
    unsigned w,h,ci,co,kernel,stride,pad,shift,ow,oh,k,elements;
    const unsigned char *bias,*input,*weight,*gold32,*gold8;
};
struct backend { int fd; unsigned char *shadow; size_t bytes; };
struct counters {
    uint64_t jobs,cycles,staged_bytes,pack_ns,submit_ns,merge_ns,verify_ns,total_ns;
    uint32_t packed_crc;
};
static uint32_t u32(const unsigned char *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static int s8(unsigned char value) { return value < 128 ? value : (int)value-256; }
static uint64_t now_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC,&ts)) { perror("clock_gettime"); exit(1); }
    return (uint64_t)ts.tv_sec*1000000000u+(uint64_t)ts.tv_nsec;
}
static uint32_t crc_update(uint32_t crc,const unsigned char *p,size_t n) {
    size_t i; unsigned b;
    for (i=0;i<n;i++) {
        crc^=p[i];
        for (b=0;b<8;b++) crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
    }
    return crc;
}
static int parse_cases(const unsigned char *data,size_t bytes,
                       struct probe_case *cases,unsigned *count) {
    size_t cursor=20; unsigned i;
    if (bytes<20 || u32(data)!=0x31544344u || u32(data+4)!=1 ||
        !u32(data+8) || u32(data+8)>16 || u32(data+12)!=bytes-20 ||
        ~crc_update(~0u,data+20,bytes-20)!=u32(data+16)) return -1;
    *count=u32(data+8);
    for (i=0;i<*count;i++) {
        struct probe_case *c=&cases[i];
        uint64_t in,wn,on,needed;
        if (cursor>bytes || bytes-cursor<64) return -1;
        memcpy(c->name,data+cursor,32);c->name[32]=0;
        if (!memchr(data+cursor,0,32)) return -1;
        c->w=u32(data+cursor+32);c->h=u32(data+cursor+36);
        c->ci=u32(data+cursor+40);c->co=u32(data+cursor+44);
        c->kernel=u32(data+cursor+48);c->stride=u32(data+cursor+52);
        c->pad=u32(data+cursor+56);c->shift=u32(data+cursor+60);
        if (!c->w || c->w>320 || !c->h || c->h>320 ||
            !c->ci || c->ci>512 || !c->co || c->co>512 ||
            (c->kernel!=1 && c->kernel!=3 && c->kernel!=6) ||
            (c->stride!=1 && c->stride!=2) || c->pad>=c->kernel ||
            c->shift>30 || c->w+2*c->pad<c->kernel || c->h+2*c->pad<c->kernel) return -1;
        c->ow=(c->w+2*c->pad-c->kernel)/c->stride+1;
        c->oh=(c->h+2*c->pad-c->kernel)/c->stride+1;
        c->k=c->ci*c->kernel*c->kernel;
        c->elements=c->ow*c->oh*c->co;
        in=(uint64_t)c->w*c->h*c->ci;wn=(uint64_t)c->co*c->k;on=c->elements;
        needed=(uint64_t)c->co*4+in+wn+on*5;
        cursor+=64;
        if (needed>bytes-cursor) return -1;
        c->bias=data+cursor;cursor+=c->co*4;
        c->input=data+cursor;cursor+=(size_t)in;
        c->weight=data+cursor;cursor+=(size_t)wn;
        c->gold32=data+cursor;cursor+=(size_t)on*4;
        c->gold8=data+cursor;cursor+=(size_t)on;
    }
    return cursor==bytes ? 0 : -1;
}
static int backend_open(struct backend *b) {
#ifdef DENSE_CONV_EMULATED
    b->fd=-1;b->bytes=1024u*1024u;b->shadow=calloc(1,b->bytes);
    return b->shadow ? 0 : -1;
#else
    struct pango_mac_info info;
    uint32_t features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED;
    b->fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);
    if (b->fd<0) { fprintf(stderr,"open /dev/pango-mac0 failed: %s\n",strerror(errno));return -1; }
    memset(&info,0,sizeof(info));
    if (ioctl(b->fd,PANGO_MAC_IOC_GET_INFO,&info) ||
        info.abi_version!=PANGO_MAC_ABI_VERSION || info.device_id!=PANGO_MAC_ID ||
        info.device_version!=PANGO_MAC_VERSION || info.scratch_bytes<SCRATCH_NEEDED ||
        info.max_pixels<16 || info.max_channels<256 || info.max_timeout_us<1000000u ||
        (info.features&features)!=features) {
        fprintf(stderr,"invalid /dev/pango-mac0 identity/capabilities\n");close(b->fd);return -1;
    }
    b->bytes=info.scratch_bytes;
    b->shadow=mmap(NULL,b->bytes,PROT_READ|PROT_WRITE,MAP_SHARED,b->fd,0);
    if (b->shadow==MAP_FAILED) { perror("private shadow mmap");close(b->fd);return -1; }
    printf("DENSE_TILED_DEVICE abi=%u id=%08x version=%08x features=%08x scratch=%u pixels=%u channels=%u\n",
           info.abi_version,info.device_id,info.device_version,info.features,
           info.scratch_bytes,info.max_pixels,info.max_channels);
    return 0;
#endif
}
static void backend_close(struct backend *b) {
#ifdef DENSE_CONV_EMULATED
    free(b->shadow);
#else
    munmap(b->shadow,b->bytes);close(b->fd);
#endif
}
static int backend_submit(struct backend *b,struct pango_mac_job *j) {
#ifdef DENSE_CONV_EMULATED
    unsigned p,co,k,tiles=(j->cin+3u)/4u;
    for (p=0;p<j->pixels;p++) for (co=0;co<j->cout;co++) {
        int32_t sum=0;
        for (k=0;k<j->cin;k++) {
            unsigned ai=j->input_offset+(p*tiles*4+k)*2;
            unsigned wi=j->weight_offset+(co/32*tiles+k/4)*128+(co%32/2*4+k%4)*2+co%2;
            sum+=s8(b->shadow[ai])*s8(b->shadow[wi]);
        }
        memcpy(b->shadow+j->output_offset+(p*j->cout+co)*4,&sum,4);
    }
    j->cycles=0;j->status=2;return 0;
#else
    if (ioctl(b->fd,PANGO_MAC_IOC_RUN,j)) {
        fprintf(stderr,"RUN failed: errno=%d status=%08x error=%u\n",errno,j->status,j->error_code);
        return -1;
    }
    if (!(j->status&2u) || (j->status&4u) || j->error_code) return -1;
    return 0;
#endif
}
static int input_value(const struct probe_case *c,unsigned position,unsigned k) {
    unsigned ci=k/(c->kernel*c->kernel),offset=k%(c->kernel*c->kernel);
    int y=(int)(position/c->ow*c->stride)-(int)c->pad+(int)(offset/c->kernel);
    int x=(int)(position%c->ow*c->stride)-(int)c->pad+(int)(offset%c->kernel);
    if (x<0 || y<0 || x>=(int)c->w || y>=(int)c->h) return 0;
    return s8(c->input[((unsigned)y*c->w+(unsigned)x)*c->ci+ci]);
}
static int requant(int64_t value,unsigned shift) {
    uint64_t magnitude=(uint64_t)(value<0 ? -value : value);
    int64_t scaled=(int64_t)((magnitude+(shift ? (1ull<<(shift-1)) : 0))>>shift);
    if (value<0) scaled=-scaled;
    return scaled<-128 ? -128 : scaled>127 ? 127 : (int)scaled;
}
static int run_case(struct backend *b,const struct probe_case *c,struct counters *stats) {
    int64_t *accum=calloc(c->elements,sizeof(*accum));
    unsigned char *quantized=malloc(c->elements);
    unsigned p0,co0,k0,position,co,k;
    uint64_t started=now_ns(),t;
    if (!accum || !quantized) { free(accum);free(quantized);return -1; }
    memset(stats,0,sizeof(*stats));stats->packed_crc=~0u;
    for (p0=0;p0<c->ow*c->oh;p0+=16) for (co0=0;co0<c->co;co0+=256) for (k0=0;k0<c->k;k0+=256) {
        struct pango_mac_job job;
        unsigned pixels=c->ow*c->oh-p0,cout=c->co-co0,cin=c->k-k0,tiles,in,wn,on;
        uint64_t t=now_ns();
        if (pixels>16) pixels=16;
        if (cout>256) cout=256;
        if (cin>256) cin=256;
        tiles=(cin+3)/4;in=pixels*tiles*8;wn=((cout+31)/32)*tiles*128;on=pixels*cout*4;
        memset(b->shadow+INPUT_OFFSET,0,in);memset(b->shadow+WEIGHT_OFFSET,0,wn);
        memset(b->shadow+OUTPUT_OFFSET,0x5a,on);
        for (position=0;position<pixels;position++) for (k=0;k<cin;k++) {
            uint16_t value=(uint16_t)(int16_t)input_value(c,p0+position,k0+k);
            unsigned ai=(position*tiles*4+k)*2;
            b->shadow[INPUT_OFFSET+ai]=(unsigned char)value;
            b->shadow[INPUT_OFFSET+ai+1]=(unsigned char)(value>>8);
        }
        for (co=0;co<cout;co++) for (k=0;k<cin;k++) {
            unsigned wi=(co/32*tiles+k/4)*128+(co%32/2*4+k%4)*2+co%2;
            b->shadow[WEIGHT_OFFSET+wi]=c->weight[(co0+co)*c->k+k0+k];
        }
        stats->pack_ns+=now_ns()-t;
        /* CRC is acceptance overhead, separated from packing/submit timings. */
        t=now_ns();
        stats->packed_crc=crc_update(stats->packed_crc,b->shadow+INPUT_OFFSET,in);
        stats->packed_crc=crc_update(stats->packed_crc,b->shadow+WEIGHT_OFFSET,wn);
        stats->verify_ns+=now_ns()-t;
        memset(&job,0,sizeof(job));job.abi_version=PANGO_MAC_ABI_VERSION;
        job.pixels=(uint16_t)pixels;job.cin=(uint16_t)cin;job.cout=(uint16_t)cout;
        job.compute_mode=1;job.output_format=3;job.zero_bias=1;
        job.input_offset=INPUT_OFFSET;job.weight_offset=WEIGHT_OFFSET;job.output_offset=OUTPUT_OFFSET;
        job.timeout_us=1000000u;
        t=now_ns();
        if (backend_submit(b,&job)) { free(accum);free(quantized);return -1; }
        stats->submit_ns+=now_ns()-t;stats->jobs++;stats->cycles+=job.cycles;
        stats->staged_bytes+=in+wn+on;
        t=now_ns();
        for (position=0;position<pixels;position++) for (co=0;co<cout;co++)
            accum[(p0+position)*c->co+co0+co]+=(int32_t)u32(b->shadow+OUTPUT_OFFSET+(position*cout+co)*4);
        stats->merge_ns+=now_ns()-t;
    }
    t=now_ns();
    for (position=0;position<c->elements;position++) {
        accum[position]+=(int32_t)u32(c->bias+position%c->co*4);
        if (accum[position]<INT32_MIN || accum[position]>INT32_MAX) {
            fprintf(stderr,"final INT32 overflow\n");free(accum);free(quantized);return -1;
        }
        quantized[position]=(unsigned char)requant(accum[position],c->shift);
    }
    stats->merge_ns+=now_ns()-t;t=now_ns();
    for (position=0;position<c->elements;position++) {
        if (accum[position]!=(int32_t)u32(c->gold32+position*4) || quantized[position]!=c->gold8[position]) {
            fprintf(stderr,"%s mismatch element=%u got=%" PRId64 " expected=%d\n",
                    c->name,position,accum[position],(int32_t)u32(c->gold32+position*4));
            free(accum);free(quantized);return -1;
        }
    }
    stats->verify_ns+=now_ns()-t;
    stats->packed_crc=~stats->packed_crc;
    stats->total_ns=now_ns()-started;free(accum);free(quantized);return 0;
}
int main(int argc,char **argv) {
    FILE *file;long length;unsigned char *data;struct probe_case cases[16];
    struct backend b;unsigned count,i,repeat,repeats=3;char *end=NULL;
    uint64_t total_jobs=0;
    if (argc<2 || argc>3) { fprintf(stderr,"usage: %s cases.bin [repeats]\n",argv[0]);return 2; }
    if (argc==3) {
        unsigned long parsed=strtoul(argv[2],&end,10);
        if (!*argv[2] || *end || !parsed || parsed>100) return 2;
        repeats=(unsigned)parsed;
    }
    file=fopen(argv[1],"rb");
    if (!file) { perror("cases file");return 1; }
    if (fseek(file,0,SEEK_END) || (length=ftell(file))<20 || length>(long)FILE_LIMIT || fseek(file,0,SEEK_SET)) {
        fclose(file);return 1;
    }
    data=malloc((size_t)length);
    if (!data || fread(data,1,(size_t)length,file)!=(size_t)length) { free(data);fclose(file);return 1; }
    fclose(file);
    if (parse_cases(data,(size_t)length,cases,&count)) { fprintf(stderr,"invalid probe file/CRC/geometry\n");free(data);return 1; }
    if (backend_open(&b)) { free(data);return 1; }
    for (i=0;i<count;i++) {
        struct counters sum={0},last;
        for (repeat=0;repeat<repeats;repeat++) {
            if (run_case(&b,&cases[i],&last)) { backend_close(&b);free(data);return 1; }
            sum.jobs+=last.jobs;sum.cycles+=last.cycles;sum.staged_bytes+=last.staged_bytes;
            sum.pack_ns+=last.pack_ns;sum.submit_ns+=last.submit_ns;sum.merge_ns+=last.merge_ns;
            sum.verify_ns+=last.verify_ns;sum.total_ns+=last.total_ns;total_jobs+=last.jobs;
        }
        printf("DENSE_TILED_CASE_PASS name=%s repeats=%u jobs_per_run=%" PRIu64
               " elements=%u packed_crc32=%08x cycles_mean=%" PRIu64 " staged_bytes_per_run=%" PRIu64
               " pack_us=%" PRIu64 " submit_us=%" PRIu64 " merge_us=%" PRIu64
               " verify_us=%" PRIu64 " total_us=%" PRIu64 "\n",
               cases[i].name,repeats,sum.jobs/repeats,cases[i].elements,last.packed_crc,
               sum.cycles/repeats,sum.staged_bytes/repeats,sum.pack_ns/repeats/1000,
               sum.submit_ns/repeats/1000,sum.merge_ns/repeats/1000,
               sum.verify_ns/repeats/1000,sum.total_ns/repeats/1000);
    }
#ifdef DENSE_CONV_EMULATED
    printf("DENSE_TILED_CONV_HOST_PASS cases=%u repeats=%u jobs=%" PRIu64 "\n",count,repeats,total_jobs);
#else
    printf("DENSE_TILED_CONV_BOARD_PASS cases=%u repeats=%u jobs=%" PRIu64 "\n",count,repeats,total_jobs);
#endif
    backend_close(&b);free(data);return 0;
}
