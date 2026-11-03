#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <errno.h>
static unsigned file_opens;static int deny_files;
static FILE *tracked_fopen(const char *path,const char *mode) {
    ++file_opens;if(deny_files){errno=EACCES;return NULL;}return fopen(path,mode);
}
#define fopen tracked_fopen
#include "xq_speech_linux.c"
#undef fopen
int main(int argc,char **argv) {
    assert(argc==2);uint64_t begin=wall_us();
    assert(xqs_linux_prepare(argv[1]));uint64_t cold=wall_us()-begin;
    assert(file_opens==XQS_MIDDLE+1u && pcm_cache_bytes<2097152u);
    for(unsigned i=0;i<=XQS_MIDDLE;i++) {
        char path[1024];snprintf(path,sizeof(path),"%s/%s.pcm",argv[1],xqs_names[i]);
        FILE *f=fopen(path,"rb");assert(f);unsigned n=pcm_cache[i].count;
        int16_t *expected=malloc(n*2u);assert(expected);
        assert(fread(expected,2,n,f)==n && fgetc(f)==EOF && !fclose(f));
        assert(!memcmp(expected,pcm_cache[i].samples,n*2u));free(expected);
    }
    unsigned before=file_opens;deny_files=1;begin=wall_us();
    for(unsigned i=0;i<1000;i++)assert(xqs_linux_prepare(argv[1]));
    uint64_t warm=wall_us()-begin;assert(file_opens==before);
    /* A changed directory cannot reuse clips from the old one or touch devices. */
    assert(!xqs_linux_prepare("/nonexistent/xq-pcm-test"));
    assert(!pcm_cache_bytes && !pcm_directory[0]);
    for(unsigned i=0;i<XQS_COUNT;i++)assert(!pcm_cache[i].samples);
    xqs_linux_release();
    printf("PCM_CACHE_PASS preload31 exactPCM,1000 warm preparations zero file opens,cold_us=%llu,warm1000_us=%llu; no devices\n",
           (unsigned long long)cold,(unsigned long long)warm);return 0;
}
