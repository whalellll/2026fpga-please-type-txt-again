/* Host-only device transaction oracle; emits every actual tile for RTL replay. */
#include "../../voice_accel/pango_voice_uapi.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdint.h>
#include <unistd.h>
static struct pango_voice_cnn_model model;
static unsigned generation,job_count;
static FILE *dump;
extern int __real_close(int);
static void word(uint32_t v){if(dump && fwrite(&v,4,1,dump)!=1)abort();}
int __wrap_open(const char *path,int flags,...){
 (void)flags;
 if(strcmp(path,"/dev/pango-voice0")){errno=ENOENT;return -1;}
 if(getenv("VOICE2_NO_CAPABILITY"))return 701;
 if(getenv("VOICE2_RTL_DUMP")){dump=fopen(getenv("VOICE2_RTL_DUMP"),"wb");if(!dump)abort();word(0);}
 return 701;
}
int __wrap_close(int fd){
 if(fd!=701)return __real_close(fd);
 if(dump){fseek(dump,0,SEEK_SET);word(job_count);fclose(dump);dump=NULL;}return 0;
}
int __wrap_ioctl(int fd,unsigned long cmd,...){
 va_list ap;void *arg;unsigned p,n,j;
 if(fd!=701){errno=EBADF;return -1;}
 va_start(ap,cmd);arg=va_arg(ap,void*);va_end(ap);
 if(cmd==PANGO_VOICE_IOC_INFO){struct pango_voice_info *i=arg;memset(i,0,sizeof(*i));i->abi_version=1;i->device_id=PANGO_VOICE_ID;i->device_version=PANGO_VOICE_VERSION;i->features=getenv("VOICE2_NO_CAPABILITY")?0:PANGO_VOICE_FEATURE_CNN_TILE;return 0;}
 if(cmd==PANGO_VOICE_IOC_CNN_MODEL){
  struct pango_voice_cnn_model *m=arg;
  if(getenv("VOICE2_MODEL_FAIL")){errno=EIO;return -1;}
  if(m->abi_version!=1 || m->k<4 || m->k>256 || m->k%4 || !m->cout || m->cout>32)abort();
  model=*m;m->generation=++generation;return 0;
 }
 if(cmd==PANGO_VOICE_IOC_CNN_TILE){
  struct pango_voice_cnn_tile *t=arg;
  if(getenv("VOICE2_TILE_TIMEOUT")){errno=ETIMEDOUT;return -1;}
  if(t->abi_version!=1 || t->generation!=generation || !t->pixels || t->pixels>16)abort();
  word(model.k);word(model.cout);word(t->pixels);
  for(j=0;j<model.k*model.cout;j+=4){uint32_t v;memcpy(&v,model.weights+j,4);word(v);}
  for(j=0;j<model.k*t->pixels;j+=4){uint32_t v;memcpy(&v,t->input+j,4);word(v);}
  for(p=0;p<t->pixels;p++)for(n=0;n<model.cout;n++){
   int32_t sum=0;
   for(j=0;j<model.k;j++)sum+=(int8_t)t->input[p*model.k+j]*(int8_t)model.weights[n*model.k+j];
   memcpy(&t->output[p*model.cout+n],&sum,4);word((uint32_t)sum);
  }
  t->status=2;t->cycles=3*(model.k/4)*model.cout*t->pixels;job_count++;return 0;
 }
 errno=ENOTTY;return -1;
}
