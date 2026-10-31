"""Execute actual driver open/clear callbacks with a cooperative-service observer."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--gcc',type=Path,default=Path('G:/fpga/workspace/tools/msys64/mingw64/bin/gcc.exe'))
a=ap.parse_args();root=Path(__file__).resolve().parents[1];out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
driver=root/'linux/mac_accel/kernel/pango_mac.c';header=root/'linux/mac_accel/kernel/pango_mac_copy_chunks.h'
source=driver.read_text()
def function(name,optional=False):
    m=re.search(r'static (?:int|void) '+name+r'\([^;]*?\)\s*\{',source,re.S)
    if not m:
        assert optional,name
        return ''
    start=m.start();index=m.end();depth=1
    while depth:
        if source[index]=='{':depth+=1
        if source[index]=='}':depth-=1
        index+=1
    return source[start:index]+'\n'
harness=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
#define PANGO_MAC_POOL_CONTEXTS 8
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct inode { int unused; };
struct file { void *private_data; };
struct miscdevice { int unused; };
struct mutex { unsigned held; };
struct pango_mac_file { bool in_use; u8 *shadow; uint32_t nnue_stats[8]; };
struct pango_mac_dev { struct miscdevice miscdev; struct mutex pool_lock; unsigned scratch_bytes; struct pango_mac_file contexts[8]; };
static struct pango_mac_dev mac;
static struct file file;
static unsigned expected_slot,yields,gap,maximum_gap,metadata_clears;
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held=0; }
static void cond_resched(void) {
    assert(mac.pool_lock.held);
    assert(mac.contexts[expected_slot].in_use);
    assert(file.private_data==&mac.miscdev); /* unpublished until zero complete */
    ++yields; gap=0;
}
static void *tracked_memset(void *p,int value,size_t bytes) {
    if(p==&mac.contexts[expected_slot].nnue_stats) {
        assert(value==0 && bytes==32 && mac.pool_lock.held);
        ++metadata_clears;
        return memset(p,value,bytes);
    }
    assert(value==0); gap+=(unsigned)bytes;
    if(gap>maximum_gap)maximum_gap=gap;
    return memset(p,value,bytes);
}
'''
harness+='\n#include "'+header.as_posix()+'"\n#define memset tracked_memset\n'
harness+=function('pango_mac_transfer_yield')+function('pango_mac_clear_chunk',optional=True)+function('pango_mac_open')
harness+=r'''
#undef memset
int main(void) {
    static const unsigned sizes[]={0,1,4095,4096,4097,1048576};
    unsigned trial,slot,index,cases=0;
    struct inode inode={0};
    for(trial=0;trial<sizeof(sizes)/sizeof(sizes[0]);++trial) {
        for(slot=0;slot<8;slot+=7) {
            unsigned bytes=sizes[trial];
            memset(&mac,0,sizeof(mac)); mac.scratch_bytes=bytes;
            for(index=0;index<8;++index) {
                mac.contexts[index].shadow=malloc(bytes+64)+32;
                assert(mac.contexts[index].shadow);
                memset(mac.contexts[index].shadow-32,0xa5,bytes+64);
                memset(mac.contexts[index].nnue_stats,0xa5,sizeof(mac.contexts[index].nnue_stats));
                mac.contexts[index].in_use=index!=slot;
            }
            file.private_data=&mac.miscdev; expected_slot=slot;
            yields=gap=maximum_gap=metadata_clears=0;
            assert(pango_mac_open(&inode,&file)==0);
            assert(file.private_data==&mac.contexts[slot] && !mac.pool_lock.held);
            assert(metadata_clears==1);
            for(index=0;index<8;++index) {
                unsigned j;
                for(j=0;j<bytes;++j)assert(mac.contexts[index].shadow[j]==(index==slot?0:0xa5));
                for(j=0;j<32;++j)assert(mac.contexts[index].shadow[-32+(int)j]==0xa5 && mac.contexts[index].shadow[bytes+j]==0xa5);
                assert(mac.contexts[index].in_use);
                for(j=0;j<8;++j)assert(mac.contexts[index].nnue_stats[j]==(index==slot?0:0xa5a5a5a5u));
            }
            if(maximum_gap>4096 || yields!=(bytes?((bytes-1)/4096):0)) {
                fprintf(stderr,"MAC_OPEN_SERVICE_BOUND_FAIL bytes=%u maximum_unserved_bytes=%u yields=%u\n",bytes,maximum_gap,yields);
                return 1;
            }
            file.private_data=&mac.miscdev;
            yields=gap=maximum_gap=metadata_clears=0;
            assert(pango_mac_open(&inode,&file)==-EBUSY);
            assert(file.private_data==&mac.miscdev && !mac.pool_lock.held && !yields && !maximum_gap && !metadata_clears);
            for(index=0;index<8;++index)free(mac.contexts[index].shadow-32);
            ++cases;
        }
    }
    printf("MAC_OPEN_PRIVATE_CLEAR_SERVICE_PASS cases=%u shadow_max_chunk=4096 metadata=32 publication_after_zero=pass other_contexts=unchanged guards=pass busy=pass\n",cases);
    return 0;
}
'''
(out/'test.c').write_text(harness,encoding='utf-8')
env=dict(os.environ);env['PATH']=str(a.gcc.parent)+os.pathsep+env['PATH']
commands=[]
try:
    for name,command in [('compile',[str(a.gcc),'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function',str(out/'test.c'),'-o',str(out/'test.exe')]),('execute',[str(out/'test.exe')])]:
        p=subprocess.run(command,capture_output=True,env=env,timeout=90)
        (out/(name+'.log')).write_bytes(p.stdout+p.stderr);commands.append(dict(name=name,command=command,exit=p.returncode))
        assert p.returncode==0,(name,(p.stdout+p.stderr).decode(errors='replace')[-2500:])
    status='ACTUAL_MAC_OPEN_PRIVATE_CLEAR_COOPERATIVE_SERVICE_PASS_NOT_KERNEL_OR_BOARD'
except Exception:
    status='FAILED_PRESERVED_NO_HARDWARE_PASS'
    raise
finally:
    receipt=dict(status=status,driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest(),header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),commands=commands,scope='Actual open and clear/yield callbacks extracted, executed against mutex/privacy/guard/service stubs. Byte bound is not a measured real-time guarantee; kernel and concurrent board acceptance remain required.')
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(status)
