/* Bounded synthetic operator comparisons. No model file or camera/audio input.
 * Production uses the existing driver and read-only published-E42 idle check.
 * R18_MOCK is an explicitly different, never-board measurement executable. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "pango_mac_uapi.h"
#include "accelerator_idle.h"
#include "pf_mlp_stage_b.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define SHADOW_BYTES 0x100000u
#define MODEL_BASE 0x1000u
#define MODEL_BYTES 0x8a84u
#define VIEW_SOURCE 0xf0000u
#define VW 16u
#define VH 16u
#define VI 32u
#define VO 32u
#define VK 3u
#define NN_CASES 4u
#define WARM_PAIRS 3u
#define MEASURE_PAIRS 3u
static volatile sig_atomic_t stopped;
static void stop_signal(int signal_number){(void)signal_number;stopped=1;}
static uint64_t ns(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;}
#ifdef R18_MOCK
static uint32_t word(const void *p){uint32_t x;memcpy(&x,p,4);return x;}
static void put_word(void *p,int32_t v){memcpy(p,&v,4);}
#endif
typedef struct {
 int fd,lock_fd,sys_fd;uint8_t *shadow;volatile uint32_t *sys;
 xy_accelerator idle;struct pango_mac_info info;
 unsigned calls,model_registers,uploads;int idle_available;uint64_t cycles,mac_cycles,read_bytes,write_bytes;
#ifdef R18_MOCK
 uint8_t *snapshot;uint32_t tag[2],sequence;int16_t view[2][1024];
 unsigned busy_reads;
#endif
} device;
#ifdef R18_MOCK
static const char *mock_case;
static const char backend[]="mock_NOT_BOARD";
#else
static const char backend[]="published_E42_driver";
#endif
static int idle_now(device *d)
{
#ifdef R18_MOCK
 if(d->busy_reads){d->busy_reads--;return 0;}return 1;
#else
 return xy_accelerator_idle(&d->idle);
#endif
}
static int drain(device *d)
{
 uint64_t end=ns()+2000000000ull;
 do{if(idle_now(d))return 1;struct timespec t={0,1000000};nanosleep(&t,NULL);}while(ns()<end);
 return 0;
}
static int open_device(device *d,unsigned required)
{
 memset(d,0,sizeof(*d));d->fd=d->lock_fd=d->sys_fd=d->idle.fd=-1;
#ifdef R18_MOCK
 d->info=(struct pango_mac_info){.abi_version=1,.device_id=PANGO_MAC_PIKAFISH_ID,
  .device_version=PANGO_MAC_PIKAFISH_VERSION,.scratch_bytes=SHADOW_BYTES,.max_timeout_us=1000000,
  .features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|
  PANGO_MAC_FEATURE_PIKAFISH_DEDICATED|PANGO_MAC_FEATURE_RESIDENT_MODEL|
  PANGO_MAC_FEATURE_NNUE_PIPELINE|PANGO_MAC_FEATURE_VISION32};
 if(mock_case && !strcmp(mock_case,"badcaps"))d->info.features=0;
#else
 d->lock_fd=open("/run/xq-metrics-r18.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
 if(d->lock_fd<0 || flock(d->lock_fd,LOCK_EX|LOCK_NB))return 0;
 d->fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);
 if(d->fd<0 || ioctl(d->fd,PANGO_MAC_IOC_GET_INFO,&d->info))return 0;
#endif
 if(d->info.abi_version!=1 || d->info.device_id!=PANGO_MAC_PIKAFISH_ID ||
    d->info.device_version!=PANGO_MAC_PIKAFISH_VERSION || d->info.scratch_bytes!=SHADOW_BYTES ||
    d->info.max_timeout_us<1000000 || (d->info.features&required)!=required)return 0;
#ifdef R18_MOCK
 if(mock_case && !strcmp(mock_case,"badclock"))return 0;
 d->shadow=calloc(1,SHADOW_BYTES);if(!d->shadow)return 0;d->idle_available=1;
#else
 if(!xy_accelerator_open(&d->idle))return 0;d->idle_available=1;
 d->sys_fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(d->sys_fd<0)return 0;
 void *sys=mmap(NULL,4096,PROT_READ,MAP_SHARED,d->sys_fd,(off_t)0x1fe00000u);
 if(sys==MAP_FAILED)return 0;d->sys=sys;
 if(d->sys[0x314/4]!=60000000u || d->sys[0x308/4]!=49500000u)return 0;
 void *shadow=mmap(NULL,SHADOW_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED,d->fd,0);
 if(shadow==MAP_FAILED)return 0;d->shadow=shadow;
#endif
 printf("R18_CAPS backend=%s abi=%u id=%08x version=%08x features=%08x scratch=%u cpu_hz=60000000 sys_hz=49500000\n",
  backend,d->info.abi_version,d->info.device_id,d->info.device_version,d->info.features,d->info.scratch_bytes);
 return idle_now(d);
}
static int close_device(device *d)
{
 int proved=d->idle_available?drain(d):0;
#ifdef R18_MOCK
 free(d->snapshot);free(d->shadow);
#else
 if(d->shadow)munmap(d->shadow,SHADOW_BYTES);
 if(d->fd>=0)close(d->fd);
 if(d->idle.regs && !drain(d))proved=0;
 if(d->sys)munmap((void *)d->sys,4096);
 if(d->sys_fd>=0)close(d->sys_fd);
 xy_accelerator_close(&d->idle);
 if(d->lock_fd>=0)close(d->lock_fd);
#endif
 printf("R18_FINAL_IDLE backend=%s known=%d five_busy0=%d closed=1 calls=%u uploads=%u model_registers=%u\n",
  backend,d->idle_available,proved,d->calls,d->uploads,d->model_registers);
 return proved;
}
static unsigned clip255(int x){return x<0?0u:x>255?255u:(unsigned)x;}
static void features(const int16_t *a,const int16_t *b,unsigned first,uint8_t out[1024])
{
 const int16_t *v[2]={first?b:a,first?a:b};
 for(unsigned side=0;side<2;side++)for(unsigned i=0;i<512;i++)
  out[side*512+i]=(uint8_t)(clip255(v[side][i])*clip255(v[side][i+512])/512u);
}
static size_t fc0_offset(unsigned output,unsigned input)
{return 0x100u+(input/256u)*8192u+(input%256u/4u)*128u+(output/2u)*8u+(input%4u)*2u+output%2u;}
#ifdef R18_MOCK
/* Independent packed-layout dot loops; CPU timing calls the existing public
 * reference implementation and never this device-side mock arithmetic. */
static int32_t mock_nnue(device *d,unsigned first)
{
 uint8_t x[1024],a[64],b[128];int32_t f0[32],f1[32];
 features(d->view[0],d->view[1],first,x);const uint8_t *s=d->snapshot;
 for(unsigned o=0;o<32;o++){
  int32_t n=(int32_t)word(s+0x8100+o*4);
  for(unsigned i=0;i<1024;i++)n+=(int8_t)s[fc0_offset(o,i)]*x[i];f0[o]=n;
  int32_t t=n< -32768?-32768:n>32767?32767:n;
  uint32_t square=(uint32_t)((int64_t)t*t)>>21;
  a[o]=(uint8_t)(square>127?127:square);
  int32_t linear=n>>7;a[o+32]=(uint8_t)(linear<0?0:linear>127?127:linear);
 }
 memcpy(b,a,64);
 for(unsigned o=0;o<32;o++){
  int32_t n=(int32_t)word(s+0x8980+o*4);
  for(unsigned i=0;i<64;i++)n+=(int8_t)s[0x8180+o*64+i]*a[i];f1[o]=n;
  int32_t t=n< -32768?-32768:n>32767?32767:n;
  uint32_t square=(uint32_t)((int64_t)t*t)>>19;
  b[64+o]=(uint8_t)(square>127?127:square);
  int32_t linear=n>>6;b[96+o]=(uint8_t)(linear<0?0:linear>127?127:linear);
 }
 int32_t result=(int32_t)word(s+0x8a80)+f0[30]-f0[31];
 for(unsigned i=0;i<128;i++)result+=(int8_t)s[0x8a00+i]*b[i];
 (void)f1;return (int32_t)((int64_t)result*75/128);
}
#endif
static int request(device *d,unsigned long command,void *argument)
{
 if(stopped || !idle_now(d))return 0;
 d->calls++;
#ifdef R18_MOCK
 if(mock_case && !strcmp(mock_case,"iofail")){d->busy_reads=2;errno=EIO;return 0;}
 if(command==PANGO_MAC_IOC_RUN_VISION32){
  struct pango_vision32_job *j=argument;unsigned sizes[5];
  if(!pango_vision32_sizes(j,SHADOW_BYTES,sizes) || j->flags!=2)return 0;
  unsigned ow=(j->width+2*j->padding-j->kernel)/j->stride+1;
  unsigned oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
  unsigned aligned=(j->cin+3)&~3u,k=j->cin*j->kernel*j->kernel;
  for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++)for(unsigned o=0;o<j->cout;o++){
   int32_t total=0;
   for(unsigned ky=0;ky<j->kernel;ky++)for(unsigned kx=0;kx<j->kernel;kx++){
    int iy=(int)(y*j->stride+ky)-(int)j->padding,ix=(int)(x*j->stride+kx)-(int)j->padding;
    if(iy<0 || ix<0 || (unsigned)iy>=j->height || (unsigned)ix>=j->width)continue;
    for(unsigned i=0;i<j->cin;i++)total+=(int8_t)d->shadow[j->input+((unsigned)iy*j->width+(unsigned)ix)*aligned+i]*
      (int8_t)d->shadow[j->weights+((o/8)*k+(ky*j->kernel+kx)*j->cin+i)*8+o%8];
   }
   put_word(d->shadow+j->output+4*((y*ow+x)*j->cout+o),total);
  }
  if(mock_case && !strcmp(mock_case,"badoutput"))d->shadow[j->output]^=1;
  j->cycles=12345;j->mac_cycles=2345;j->read_bytes=sizes[0]+sizes[1]+sizes[3];j->write_bytes=sizes[2];j->status=2;
 }else if(command==PANGO_MAC_IOC_REGISTER_MODEL){
  struct pango_mac_model *m=argument;
  if(!pango_mac_model_valid(m,SHADOW_BYTES) || m->offset!=MODEL_BASE || m->bytes!=MODEL_BYTES)return 0;
  free(d->snapshot);d->snapshot=malloc(m->bytes);if(!d->snapshot)return 0;
  memcpy(d->snapshot,d->shadow+m->offset,m->bytes);d->tag[0]=d->tag[1]=0;
 }else if(command==PANGO_MAC_IOC_NNUE_UPLOAD){
  struct pango_mac_nnue_upload *u=argument;if(!pango_mac_nnue_upload_valid(u,SHADOW_BYTES))return 0;
  memcpy(d->view[u->view],d->shadow+u->source_offset,2048);d->tag[u->view]=u->tag=++d->sequence;
 }else if(command==PANGO_MAC_IOC_RUN_NNUE){
  struct pango_mac_nnue_job *j=argument;
  if(!pango_mac_nnue_job_valid(j) || !d->snapshot || j->tag0!=d->tag[0] || j->tag1!=d->tag[1])return 0;
  j->score=(uint32_t)mock_nnue(d,j->first_view);j->cycles=17000;j->jobs=6;j->status=2;
  if(mock_case && !strcmp(mock_case,"badoutput"))j->score^=1;
 }else return 0;
#else
 if(ioctl(d->fd,command,argument))return 0;
#endif
 return idle_now(d);
}
typedef struct {int8_t *input,*weights;int32_t *cpu,*accelerated;} vision_fixture;
static void vision_cpu(const vision_fixture *f)
{
 for(unsigned y=0;y<VH;y++)for(unsigned x=0;x<VW;x++)for(unsigned o=0;o<VO;o++){
  int32_t total=0;
  for(unsigned ky=0;ky<VK;ky++)for(unsigned kx=0;kx<VK;kx++){
   int iy=(int)y+(int)ky-1,ix=(int)x+(int)kx-1;
   if(iy<0 || ix<0 || iy>=(int)VH || ix>=(int)VW)continue;
   for(unsigned i=0;i<VI;i++)total+=f->input[((unsigned)iy*VW+(unsigned)ix)*VI+i]*
      f->weights[((o*VK+ky)*VK+kx)*VI+i];
  }
  f->cpu[(y*VW+x)*VO+o]=total;
 }
}
static int vision_accelerated(device *d,const vision_fixture *f)
{
 struct pango_vision32_job j={.abi_version=PANGO_VISION32_ABI,.input=0,.weights=0x10000,.params=0x4000,
  .output=0x20000,.width=VW,.height=VH,.cin=VI,.cout=VO,.kernel=VK,.stride=1,.padding=1,
  .flags=PANGO_VISION32_RAW_I32,.timeout_cycles=49500000,.timeout_us=1000000};
 unsigned sizes[5];if(!pango_vision32_sizes(&j,SHADOW_BYTES,sizes))return 0;
 memcpy(d->shadow+j.input,f->input,VW*VH*VI);memset(d->shadow+j.params,0,sizes[3]);
 for(unsigned o=0;o<VO;o++)for(unsigned k=0;k<VK*VK*VI;k++)
  d->shadow[j.weights+((o/8)*(VK*VK*VI)+k)*8+o%8]=(uint8_t)f->weights[o*(VK*VK*VI)+k];
 memset(d->shadow+j.output,0xa5,sizes[2]);
 if(!request(d,PANGO_MAC_IOC_RUN_VISION32,&j) || (j.status&7u)!=2u || j.error || !j.cycles)return 0;
 memcpy(f->accelerated,d->shadow+j.output,sizes[2]);
 d->cycles+=j.cycles;d->mac_cycles+=j.mac_cycles;d->read_bytes+=j.read_bytes;d->write_bytes+=j.write_bytes;return 1;
}
typedef struct {int8_t w0[32768],w1[2048],w2[128];int32_t b0[32],b1[32],b2;
 int16_t view[NN_CASES][2][1024];pf_mlp_model_t model;int32_t cpu[NN_CASES],accelerated[NN_CASES];} nnue_fixture;
static void nnue_init(nnue_fixture *f)
{
 for(unsigned o=0;o<32;o++){
  f->b0[o]=(int32_t)o*401-6000;f->b1[o]=(int32_t)o*117-1700;
  for(unsigned i=0;i<1024;i++)f->w0[o*1024+i]=(int8_t)((int)((o*17+i*7+i/256*3)%7)-3);
  for(unsigned i=0;i<64;i++)f->w1[o*64+i]=(int8_t)((int)((o*11+i*13)%7)-3);
 }
 for(unsigned i=0;i<128;i++)f->w2[i]=(int8_t)((int)((i*19)%7)-3);f->b2=311;
 for(unsigned c=0;c<NN_CASES;c++)for(unsigned v=0;v<2;v++)for(unsigned i=0;i<1024;i++)
  f->view[c][v][i]=(int16_t)((int)((i*29+c*19+v*41)%320)-32);
 f->model=(pf_mlp_model_t){.fc0_w=f->w0,.fc0_b=f->b0,.fc1_w=f->w1,.fc1_b=f->b1,.fc2_w=f->w2,.fc2_b=&f->b2};
}
static int nnue_register(device *d,const nnue_fixture *f)
{
 memset(d->shadow+MODEL_BASE,0,MODEL_BYTES);uint8_t *s=d->shadow+MODEL_BASE;
 for(unsigned o=0;o<32;o++)for(unsigned i=0;i<1024;i++)s[fc0_offset(o,i)]=(uint8_t)f->w0[o*1024+i];
 memcpy(s+0x8100,f->b0,128);memcpy(s+0x8180,f->w1,2048);memcpy(s+0x8980,f->b1,128);
 memcpy(s+0x8a00,f->w2,128);memcpy(s+0x8a80,&f->b2,4);
 struct pango_mac_model m={.abi_version=PANGO_MAC_MODEL_ABI_VERSION,.offset=MODEL_BASE,.bytes=MODEL_BYTES};
 if(!request(d,PANGO_MAC_IOC_REGISTER_MODEL,&m))return 0;d->model_registers++;return 1;
}
static int nnue_cpu(nnue_fixture *f)
{
 for(unsigned c=0;c<NN_CASES;c++){
  uint8_t x[1024];features(f->view[c][0],f->view[c][1],c&1,x);
  if(!pf_mlp_propagate(&f->model,x,NULL,NULL,&f->cpu[c]))return 0;
 }
 return 1;
}
static int nnue_accelerated(device *d,nnue_fixture *f)
{
 for(unsigned c=0;c<NN_CASES;c++){
  uint32_t tags[2];
  for(unsigned v=0;v<2;v++){
   memcpy(d->shadow+VIEW_SOURCE,f->view[c][v],2048);
   struct pango_mac_nnue_upload u={.abi_version=PANGO_MAC_NNUE_ABI_VERSION,.view=v,.source_offset=VIEW_SOURCE};
   if(!request(d,PANGO_MAC_IOC_NNUE_UPLOAD,&u) || !u.tag)return 0;tags[v]=u.tag;d->uploads++;
  }
  struct pango_mac_nnue_job j={.abi_version=PANGO_MAC_NNUE_ABI_VERSION,.tag0=tags[0],.tag1=tags[1],.first_view=c&1,.timeout_us=1000000};
  if(!request(d,PANGO_MAC_IOC_RUN_NNUE,&j) || (j.status&7u)!=2u || !j.cycles || j.jobs!=6)return 0;
  f->accelerated[c]=(int32_t)j.score;d->cycles+=j.cycles;
 }
 return 1;
}
static int benchmark(device *d,int vision)
{
 vision_fixture v={0};nnue_fixture *n=NULL;size_t output_bytes;uint64_t setup=ns(),sum_cpu=0,sum_acc=0;
 if(vision){
  v.input=malloc(VW*VH*VI);v.weights=malloc(VO*VK*VK*VI);v.cpu=malloc(VW*VH*VO*4);v.accelerated=malloc(VW*VH*VO*4);
  if(!v.input || !v.weights || !v.cpu || !v.accelerated)goto failure;
  for(unsigned i=0;i<VW*VH*VI;i++)v.input[i]=(int8_t)((int)((i*17+29)%31)-15);
  for(unsigned i=0;i<VO*VK*VK*VI;i++)v.weights[i]=(int8_t)((int)((i*13+7)%15)-7);
  output_bytes=VW*VH*VO*4;
 }else{n=calloc(1,sizeof(*n));if(!n)goto failure;nnue_init(n);if(!nnue_register(d,n))goto failure;output_bytes=NN_CASES*4;}
 printf("R18_SETUP backend=%s operator=%s setup_ns=%llu parameters=synthetic_fixed_bounded model_file=none\n",backend,
  vision?"vision32_raw_i32_16x16_ci32_co32_k3":"nnue_transform_plus_1024x32_64x32_128x1_four_inputs",
  (unsigned long long)(ns()-setup));
 /* Leave room inside the external60s case limit for one CPU operation and
  * a bounded2s accepted-traffic drain. No retry after any submit failure. */
 uint64_t deadline=ns()+45000000000ull;
 for(unsigned pair=0;pair<WARM_PAIRS+MEASURE_PAIRS;pair++){
  uint64_t cpu=0,accelerated=0,cycles_before=d->cycles,mac_before=d->mac_cycles;
  for(unsigned phase=0;phase<2;phase++){
   if(stopped || ns()>deadline)goto failure;
   int hardware=(phase^(pair&1))!=0;uint64_t start=ns();
   if(hardware){if(!(vision?vision_accelerated(d,&v):nnue_accelerated(d,n)))goto failure;accelerated=ns()-start;}
   else{if(vision)vision_cpu(&v);else if(!nnue_cpu(n))goto failure;cpu=ns()-start;}
  }
  if(memcmp(vision?(void *)v.cpu:(void *)n->cpu,vision?(void *)v.accelerated:(void *)n->accelerated,output_bytes)){
   fprintf(stderr,"R18_NUMERIC_MISMATCH operator=%s pair=%u\n",vision?"vision":"nnue",pair);goto failure;
  }
  if(pair>=WARM_PAIRS){sum_cpu+=cpu;sum_acc+=accelerated;
   printf("R18_PAIR backend=%s operator=%s index=%u order=%s cpu_ns=%llu accelerator_ns=%llu cycles=%llu mac_cycles=%llu outputs_i32=%u exact=1\n",
    backend,vision?"vision":"nnue",pair-WARM_PAIRS,(pair&1)?"accelerator_cpu":"cpu_accelerator",(unsigned long long)cpu,
    (unsigned long long)accelerated,(unsigned long long)(d->cycles-cycles_before),(unsigned long long)(d->mac_cycles-mac_before),(unsigned)(output_bytes/4));
  }
 }
 if(!sum_acc || stopped || ns()>deadline)goto failure;
 printf("R18_OPERATOR_RESULT backend=%s operator=%s warm_pairs=%u measured_pairs=%u cpu_total_ns=%llu accelerator_total_ns=%llu ratio_milli=%llu macs_per_sample=%u scope=operator_only_includes_layout_driver_transfer_and_copyout not_model_or_engine=1\n",
  backend,vision?"vision32_raw_i32_ci32_co32_k3":"nnue_MLP_four_inputs",WARM_PAIRS,MEASURE_PAIRS,(unsigned long long)sum_cpu,
  (unsigned long long)sum_acc,(unsigned long long)(sum_cpu*1000/sum_acc),vision?VW*VH*VO*VK*VK*VI:NN_CASES*(32768+2048+128));
 free(v.input);free(v.weights);free(v.cpu);free(v.accelerated);free(n);return 1;
failure:
 free(v.input);free(v.weights);free(v.cpu);free(v.accelerated);free(n);return 0;
}
int main(int argc,char **argv)
{
 if(argc==2 && !strcmp(argv[1],"--describe")){
  puts("R18_PROBE_DESCRIPTION no_device_open=1 modes=vision,nnue required=published_E42_CPU60_SYS49.5 private_driver_shadow=1 warm_pairs=3 measured_pairs=3 per_mode_limit_s=60 final_five_BUSY0=required");return 0;
 }
 if(argc<3 || argc>4 || strcmp(argv[1],"--run") || (strcmp(argv[2],"vision") && strcmp(argv[2],"nnue")))return 2;
#ifdef R18_MOCK
 if(argc==4)mock_case=argv[3];
#else
 if(argc!=3)return 2;
#endif
 int vision=!strcmp(argv[2],"vision");
 struct sigaction action;memset(&action,0,sizeof(action));action.sa_handler=stop_signal;sigemptyset(&action.sa_mask);
 if(sigaction(SIGINT,&action,NULL) || sigaction(SIGTERM,&action,NULL) || sigaction(SIGALRM,&action,NULL))return 2;
 unsigned required=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_PIKAFISH_DEDICATED|
  (vision?PANGO_MAC_FEATURE_VISION32:PANGO_MAC_FEATURE_NNUE_PIPELINE|PANGO_MAC_FEATURE_RESIDENT_MODEL);
 device d;alarm(55);int okay=open_device(&d,required);
#ifdef R18_MOCK
 if(mock_case && !strcmp(mock_case,"cancel"))stopped=1;
#endif
 if(okay)okay=benchmark(&d,vision);int saved=errno;
 if(!close_device(&d))okay=0;alarm(0);
 if(!okay){fprintf(stderr,"R18_PROBE_FAIL backend=%s mode=%s errno=%d stopped=%d no_fallback=1\n",backend,argv[2],saved,(int)stopped);return 1;}
 puts("R18_PROBE_PASS outputs_complete_i32_equal=1 final_idle_proven=1");return 0;
}
