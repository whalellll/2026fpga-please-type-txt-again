"""Execute actual driver functions with MMIO/ownership/drain fault observers."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,io,tarfile
from picture_workspace import workspace_path,wsl_path
R=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);ap.add_argument('--reuse',action='store_true');ap.add_argument('--distribution',default='Ubuntu-22.04');a=ap.parse_args()
out=workspace_path(a.output);out.mkdir(parents=True,exist_ok=False)
driver=R/'linux/mac_accel/kernel/pango_mac.c';header=R/'linux/mac_accel/pango_mac_uapi.h'
s=driver.read_text();h=header.read_text()
def function(text,name):
 m=re.search(r'(?:static (?:inline )?(?:int|bool)) '+name+r'\([^;]*?\)\s*\{',text,re.S);assert m,name
 at=m.end();depth=1
 while depth:
  if text[at]=='{':depth+=1
  if text[at]=='}':depth-=1
  at+=1
 return text[m.start():at]+'\n'
api=re.search(r'struct pango_vision32_job\s*\{.*?\};',h,re.S).group(0)
body=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;typedef uint8_t u8;typedef int64_t ktime_t;
#define PANGO_MAC_U32 uint32_t
#define PANGO_VISION32_ABI 1u
#define PANGO_MAC_CONV_STATUS 0x48
#define PANGO_MAC_REG_STATUS 0x0c
#define PANGO_MAC_NNUE_BASE 0x180
#define PANGO_MAC_BATCH_BASE 0x80
#define PANGO_MAC_STAGEA_BASE 0x100
#define PANGO_MAC_STATUS_BUSY 1
#define BIT(n) (1u<<(n))
#define __iomem
struct mutex {int held;};
struct pango_mac_file;
struct pango_mac_dev {
    u8 *regs,*scratch;u32 scratch_bus,scratch_bytes;
    bool vision32_supported,vision32_exact_supported,nnue_supported,stagea_supported,batch_supported;
    struct mutex run_lock;struct pango_mac_file *resident_owner,*vision_owner;u32 vision_key[11];
};
struct pango_mac_file {struct pango_mac_dev *mac;u8 *shadow;};
static unsigned regs[128];static u8 scratch[1048576],shadow[1048576];
static struct pango_mac_dev mac;
static struct pango_mac_file context;
static unsigned polls,mode,outputs,copies,starts,aborts,config_writes,last_output_bytes;
static uint64_t copyin_bytes;
static u32 configuration[16],index_register,status;
static int64_t now;
static int mutex_lock_interruptible(struct mutex *m){assert(!m->held);m->held=1;return 0;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
static ktime_t ktime_get(void){return ++now;}
static ktime_t ktime_add_us(ktime_t t,u32 us){return t+us;}
static int ktime_compare(ktime_t a,ktime_t b){return (a>b)-(a<b);}
static void cpu_relax(void){}
static void cond_resched(void){assert(mac.run_lock.held);}
static void mb(void){}static void rmb(void){}static void wmb(void){}
static u32 readl(const void *p){
    unsigned offset=(unsigned)((const u8 *)p-(const u8 *)regs);
    assert(offset<sizeof(regs) && !(offset&3));
    if(offset==0x44){
        if(starts && status==1 && mode!=2 && ++polls>3){
            status=mode==1?6:2;
            if(mode==0){u32 value=0x87654321;memcpy(scratch+configuration[2]-mac.scratch_bus,&value,4);}
        }
        return status;
    }
    return regs[offset/4];
}
static void writel(u32 value,void *p){
    unsigned offset=(unsigned)((u8 *)p-(u8 *)regs);assert(mac.run_lock.held);
    assert(offset<sizeof(regs) && !(offset&3));regs[offset/4]=value;
    if(offset==0x4c)index_register=value;
    if(offset==0x50){assert(index_register<16);configuration[index_register]=value;config_writes++;}
    if(offset==0x48 && value==4){assert(!status);config_writes=0;}
    if(offset==0x48 && value==1){assert(config_writes==16);starts++;status=1;polls=0;}
    if(offset==0x48 && value==2){assert(mode==2);aborts++;status=17;}
}
static void pango_mac_copy_data(u8 *normal,u8 *io,const u8 *source,u32 bytes){
    assert(mac.run_lock.held && !normal && !status);memcpy(io,source,bytes);copies++;copyin_bytes+=bytes;
}
static void pango_mac_copy_output(u8 *normal,const u8 *io,u32 bytes){
    last_output_bytes=bytes;
    assert(mac.run_lock.held && status==2);memcpy(normal,io,bytes);outputs++;
}
'''
body+='#define PANGO_VISION32_REUSE_PARAMS 0x56525031u\n'
# Optional aggregate profiling and copy selection are observed, not real MMIO.
if 'pango_vision_copy(mode,' in s:
    body += '''
typedef uint64_t u64;
#define READ_ONCE(x) (x)
static unsigned vision_io_mode;
static bool vision_profile;
static u64 ktime_get_ns(void){return (u64)ktime_get();}
static void pango_vision_copy(unsigned io_mode,u8 *normal,u8 *io,
    const u8 *source,const u8 *io_source,u32 bytes){
    assert(io_mode<=2);
    if(normal)pango_mac_copy_output(normal,io_source,bytes);
    else pango_mac_copy_data(NULL,io,source,bytes);
}
'''
    counters = re.findall(r'static unsigned long long (vision_\w+);', s)
    body += 'static u64 '+','.join(counters)+';\n'
body+=api+'\n'+function(h,'pango_vision32_sizes')+'\n'+function(h,'pango_mac_ranges_overlap')
for name in ['pango_mac_nnue_busy','pango_mac_conv_busy','pango_mac_engines_busy','pango_mac_run_vision32']:body+=function(s,name)
body+=r'''
static struct pango_vision32_job job(void){
    struct pango_vision32_job j={0};j.abi_version=1;j.weights=4096;j.params=8192;j.output=12288;
    j.width=j.height=j.cin=j.cout=j.kernel=j.stride=1;j.flags=2;
    j.timeout_cycles=49500000;j.timeout_us=100;j.model_generation=91;j.frame_id=37;return j;
}
static void reset(void){
    memset(regs,0,sizeof(regs));memset(scratch,0,sizeof(scratch));memset(shadow,0xa5,sizeof(shadow));
    memset(&mac,0,sizeof(mac));mac.regs=(u8 *)regs;mac.scratch=scratch;
    mac.scratch_bus=0x1b000000;mac.scratch_bytes=sizeof(scratch);mac.vision32_supported=true;
    mac.nnue_supported=mac.stagea_supported=true;context.mac=&mac;context.shadow=shadow;mac.resident_owner=&context;
    polls=mode=outputs=copies=starts=aborts=config_writes=status=0;now=0;copyin_bytes=0;
}
int main(void){
    struct pango_vision32_job j;u32 word;reset();j=job();
    assert(!pango_mac_run_vision32(&context,&j));assert(outputs==1 && copies==3 && starts==1 && !aborts);
    memcpy(&word,shadow+j.output,4);assert(word==0x87654321 && !mac.resident_owner && !mac.run_lock.held);
    assert(configuration[0]==0x1b000000 && configuration[1]==0x1b001000 && configuration[2]==0x1b003000);
    assert(configuration[12]==2 && configuration[13]==49500000 && configuration[14]==91 && configuration[15]==37);
    assert(j.frame_id==37); /* Old clients retain their frame metadata. */
    for(unsigned busy=0;busy<5;busy++){
        reset();j=job();
        if(busy==0)status=17; /* prior V321 cancel is still draining */
        if(busy==1)regs[0x18c/4]=1;
        if(busy==2)regs[0x10c/4]=1;
        if(busy==3)regs[0x0c/4]=1;
        if(busy==4){mac.batch_supported=true;regs[0x8c/4]=1;}
        assert(pango_mac_run_vision32(&context,&j)==-EBUSY);
        assert(!starts && !copies && !outputs && mac.resident_owner==&context && !mac.run_lock.held);
    }
    reset();mode=1;j=job();assert(pango_mac_run_vision32(&context,&j)==-EIO);
    assert(!outputs && shadow[j.output]==0xa5 && !mac.resident_owner && !mac.run_lock.held);
    reset();mode=2;j=job();j.timeout_us=4;assert(pango_mac_run_vision32(&context,&j)==-ETIMEDOUT);
    assert(aborts==1 && !outputs && status==17 && !mac.run_lock.held);
    assert(pango_mac_engines_busy(&mac));j=job();assert(pango_mac_run_vision32(&context,&j)==-EBUSY);
    status=0;mode=0;starts=0;j=job();assert(!pango_mac_run_vision32(&context,&j));
    reset();j=job();j.flags=4;
    assert(pango_mac_run_vision32(&context,&j)==-EOPNOTSUPP);assert(!starts && !copies);
    mac.vision32_exact_supported=true;assert(!pango_mac_run_vision32(&context,&j));
    assert(outputs==1 && last_output_bytes==2);
    reset();j=job();j.output=0;assert(pango_mac_run_vision32(&context,&j)==-EINVAL);assert(!starts && !copies);
    reset();j=job();mac.vision32_supported=false;assert(pango_mac_run_vision32(&context,&j)==-EOPNOTSUPP);
    puts("ACTUAL_VISION32_DRIVER_OWNERSHIP_CONFIG_FAILURE_AND_DRAIN_PASS_NOT_KERNEL_OR_BOARD");return 0;
}
'''
if a.reuse:
 body=body.replace('    puts("ACTUAL_VISION32_DRIVER_',r'''
    reset();j=job();j.reserved[0]=PANGO_VISION32_REUSE_PARAMS;
    assert(!pango_mac_run_vision32(&context,&j));assert(copies==3 && j.frame_id==0);
    status=0;j=job();j.reserved[0]=PANGO_VISION32_REUSE_PARAMS;
    assert(!pango_mac_run_vision32(&context,&j));assert(copies==4 && j.frame_id==1);
    status=0;j.model_generation++;assert(!pango_mac_run_vision32(&context,&j));assert(copies==7 && j.frame_id==0);
    /* A peer with equal cookie/offsets must never reuse another fd's bytes. */
    {struct pango_mac_file peer=context;status=0;assert(!pango_mac_run_vision32(&peer,&j));assert(copies==10 && j.frame_id==0);}
    status=0;assert(!pango_mac_run_vision32(&context,&j));assert(copies==13 && j.frame_id==0);
    status=0;j.weights+=256;assert(!pango_mac_run_vision32(&context,&j));assert(copies==16 && j.frame_id==0);
    status=0;j.params+=256;assert(!pango_mac_run_vision32(&context,&j));assert(copies==19 && j.frame_id==0);
    status=0;j.input=j.weights;assert(!pango_mac_run_vision32(&context,&j));assert(copies==22 && !mac.vision_owner);
    status=0;assert(!pango_mac_run_vision32(&context,&j));assert(copies==25 && !j.frame_id);
    status=0;j=job();j.reserved[0]=PANGO_VISION32_REUSE_PARAMS;
    assert(!pango_mac_run_vision32(&context,&j));assert(mac.vision_owner==&context);
    status=0;mode=1;assert(pango_mac_run_vision32(&context,&j)==-EIO);assert(!mac.vision_owner);
    status=0;mode=0;assert(!pango_mac_run_vision32(&context,&j));assert(j.frame_id==0);
    /* Explicit opt-in is required; legacy nonzero generation remains ignored. */
    status=0;j=job();unsigned count=copies;assert(!pango_mac_run_vision32(&context,&j));
    status=0;assert(!pango_mac_run_vision32(&context,&j));assert(copies==count+6 && j.frame_id==37);
    status=0;j=job();j.reserved[0]=PANGO_VISION32_REUSE_PARAMS;j.model_generation=0;
    assert(pango_mac_run_vision32(&context,&j)==-EINVAL);
    reset();mac.vision32_exact_supported=true;j=job();j.flags=5;j.lut=0x20000;j.reserved[0]=PANGO_VISION32_REUSE_PARAMS;
    assert(!pango_mac_run_vision32(&context,&j));assert(copyin_bytes==65644 && copies==4);
    shadow[j.lut]=0x37;shadow[0]=0x29;status=0;
    assert(!pango_mac_run_vision32(&context,&j));assert(copyin_bytes==65648 && j.frame_id==1);
    assert(scratch[0]==0x29 && scratch[j.lut]==0xa5);
    status=0;j.model_generation++;assert(!pango_mac_run_vision32(&context,&j));
    assert(copyin_bytes==131292 && scratch[j.lut]==0x37 && j.frame_id==0);
    status=0;mode=2;j.timeout_us=4;
    assert(pango_mac_run_vision32(&context,&j)==-ETIMEDOUT && !mac.vision_owner && status==17);
    assert(pango_mac_run_vision32(&context,&j)==-EBUSY && !mac.vision_owner);
    status=0;mode=0;j.timeout_us=100;assert(!pango_mac_run_vision32(&context,&j) && j.frame_id==0);
    puts("VISION_REUSE_EXACT_LUT_COPYIN_65644_TO4_NEW_GENERATION_RESTORES_PASS");
    puts("VISION_REUSE_FIRST_UPLOAD_NEXT_INPUT_ONLY_PASS");
    puts("ACTUAL_VISION32_DRIVER_''',1)
(out/'test.c').write_bytes(body.encode());native=wsl_path(out/'source')
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w') as archive:archive.add(out/'test.c',arcname='test.c')
command=f"set -eu; mkdir '{native}'; tar -xf - -C '{native}'; mkdir '{native}/tmp'; export TMPDIR='{native}/tmp' TMP='{native}/tmp' TEMP='{native}/tmp'; gcc -std=c11 -O2 -Wall -Wextra -Werror '{native}/test.c' -o '{native}/test'; '{native}/test'"
r=subprocess.run(['wsl.exe','-d',a.distribution,'--','env','PATH=/usr/bin:/bin','timeout','--kill-after=5','60','sh','-c',command],input=payload.getvalue(),capture_output=True,timeout=90)
(out/'test.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr).decode(errors='replace')[-3000:]
result=dict(status='ACTUAL_VISION32_DRIVER_OWNERSHIP_CONFIG_FAILURE_AND_DRAIN_PASS_NOT_KERNEL_OR_BOARD',inputs_sha256={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [driver,header]},harness_sha256=hashlib.sha256(body.encode()).hexdigest(),log_sha256=hashlib.sha256(r.stdout+r.stderr).hexdigest(),scope='Actual driver functions executed with MMIO/copy/mutex/time observers: private ownership, physical cfg translation, concurrent-engine rejection, failed-output suppression, timeout/AXI drain quarantine/recovery. Real kernel and board remain separate.')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
