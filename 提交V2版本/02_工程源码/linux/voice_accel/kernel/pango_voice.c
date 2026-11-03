// SPDX-License-Identifier: GPL-2.0
/* Exclusive owner of the independent XQT1 feature/classifier accelerator. */
#include <linux/atomic.h>
#include <linux/crc32.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <asm/unaligned.h>
#include <uapi/linux/pango_voice.h>

struct pango_voice_dev {
    void __iomem *regs;
    struct mutex lock;
    atomic_t owner;
    bool model_loaded;
    bool cnn_supported,cnn_loaded;
    u32 cnn_k,cnn_cout,cnn_generation;
    struct miscdevice misc;
};
static int voice_wait(struct pango_voice_dev *v,u32 mask,u32 timeout)
{
    ktime_t end=ktime_add_us(ktime_get(),timeout?timeout:100000u);
    u32 polls=0,status;
    for(;;){
        status=readl(v->regs+0x0c);
        if(status&mask)return 0;
        if(ktime_compare(ktime_get(),end)>=0){writel(2,v->regs+8);mb();return -ETIMEDOUT;}
        cpu_relax();if(!(++polls&255))cond_resched();
    }
}
static int voice_disable(struct pango_voice_dev *v)
{
    ktime_t end=ktime_add_us(ktime_get(),100000);
    u32 polls=0;
    do {
        writel(0,v->regs+0x5c);mb();
        if(!readl(v->regs+0x5c))return 0;
        if(ktime_compare(ktime_get(),end)>=0)return -ETIMEDOUT;
        cpu_relax();if(!(++polls&255))cond_resched();
    } while(1);
}
static int voice_model(struct pango_voice_dev *v,const struct pango_voice_model *m)
{
    const u8 *b=m->image;
    u32 i,shifts;
    int ret;
    if(memcmp(b,"XQT1",4) || get_unaligned_le32(b+4)!=1 || get_unaligned_le32(b+8)!=128 ||
       get_unaligned_le32(b+12)!=6020 || get_unaligned_le32(b+20)!=16000 ||
       get_unaligned_le32(b+24)!=20 || get_unaligned_le32(b+28)!=2 ||
       get_unaligned_le32(b+32)!=64 || get_unaligned_le32(b+36)!=32 ||
       get_unaligned_le32(b+40)!=25 || get_unaligned_le32(b+64)!=1 ||
       get_unaligned_le32(b+52)>30 || get_unaligned_le32(b+56)>30 || get_unaligned_le32(b+60)>30 ||
       (crc32_le(~0u,b+128,6020-128)^~0u)!=get_unaligned_le32(b+16))return -EINVAL;
    ret=voice_disable(v);if(ret)return ret;
    v->model_loaded=false;writel(2,v->regs+8);writel(0,v->regs+0x10);
    for(i=0;i<6020;i+=4)writel(get_unaligned_le32(b+i),v->regs+0x14);
    shifts=get_unaligned_le32(b+52)|(get_unaligned_le32(b+56)<<8)|(get_unaligned_le32(b+60)<<16);
    writel(shifts,v->regs+0x18);writel(get_unaligned_le32(b+44),v->regs+0x1c);
    writel(get_unaligned_le32(b+48),v->regs+0x20);mb();
    if(readl(v->regs+0x10)!=1505)return -EIO;
    v->model_loaded=true;return 0;
}
static long voice_ioctl_locked(struct pango_voice_dev *v,unsigned int cmd,unsigned long arg)
{
    void __user *u=(void __user *)arg;
    unsigned int i,j;
    int ret;
    if(cmd==PANGO_VOICE_IOC_INFO){
        struct pango_voice_info info={.abi_version=1,.device_id=PANGO_VOICE_ID,.device_version=PANGO_VOICE_VERSION,
            .sample_rate=16000,.features=v->cnn_supported?PANGO_VOICE_FEATURE_CNN_TILE:31,.window_samples=400,.hop_samples=160,.queue_frames=16,.model_bytes=6020};
        return copy_to_user(u,&info,sizeof(info))?-EFAULT:0;
    }
    if(cmd==PANGO_VOICE_IOC_CNN_MODEL){
        struct pango_voice_cnn_model *m;
        u32 words;
        if(!v->cnn_supported)return -EOPNOTSUPP;
        m=memdup_user(u,sizeof(*m));if(IS_ERR(m))return PTR_ERR(m);
        ret=-EINVAL;
        if(m->abi_version!=1 || m->k<4 || m->k>256 || (m->k&3) || !m->cout || m->cout>32 ||
           m->generation || m->flags || m->reserved[0] || m->reserved[1] || m->reserved[2])goto cnn_model_out;
        if(v->cnn_generation==~0u){ret=-EOVERFLOW;goto cnn_model_out;}
        if(readl(v->regs+0x8c)&1){ret=-EBUSY;goto cnn_model_out;}
        v->cnn_loaded=false;writel(6,v->regs+0x88);words=m->k*m->cout/4;
        writel(m->k|(m->cout<<16),v->regs+0xa0);
        for(i=0;i<words;i++)writel(get_unaligned_le32(m->weights+i*4),v->regs+0x94);
        mb();if(readl(v->regs+0xb4)!=words){ret=-EIO;goto cnn_model_out;}
        v->cnn_k=m->k;v->cnn_cout=m->cout;v->cnn_loaded=true;m->generation=++v->cnn_generation;
        ret=copy_to_user(u,m,sizeof(*m))?-EFAULT:0;
cnn_model_out:kfree(m);return ret;
    }
    if(cmd==PANGO_VOICE_IOC_CNN_TILE){
        struct pango_voice_cnn_tile *t;
        ktime_t deadline;u32 polls=0,status=0;
        if(!v->cnn_supported)return -EOPNOTSUPP;
        if(!v->cnn_loaded)return -ENODATA;
        t=memdup_user(u,sizeof(*t));if(IS_ERR(t))return PTR_ERR(t);
        ret=-EINVAL;
        if(t->abi_version!=1 || !t->pixels || t->pixels>16 || t->timeout_us>1000000 ||
           t->reserved[0] || t->reserved[1])goto cnn_tile_out;
        if(t->generation!=v->cnn_generation){ret=-ESTALE;goto cnn_tile_out;}
        if(readl(v->regs+0x8c)&1){ret=-EBUSY;goto cnn_tile_out;}
        writel(2,v->regs+0x88);writel(t->pixels,v->regs+0xa4);
        for(i=0;i<t->pixels*v->cnn_k/4;i++)writel(get_unaligned_le32(t->input+i*4),v->regs+0x9c);
        wmb();writel(1,v->regs+0x88);deadline=ktime_add_us(ktime_get(),t->timeout_us?t->timeout_us:100000);
        for(;;){
            status=readl(v->regs+0x8c);
            if(!(status&1) && (status&2)){ret=(status&4)?-EIO:0;break;}
            if(ktime_compare(ktime_get(),deadline)>=0){ret=-ETIMEDOUT;break;}
            cpu_relax();if(!(++polls&255))cond_resched();
        }
        if(ret){writel(6,v->regs+0x88);mb();v->cnn_loaded=false;goto cnn_tile_out;}
        t->status=status;t->cycles=readl(v->regs+0xa8);memset(t->output,0,sizeof(t->output));
        rmb();for(i=0;i<t->pixels*v->cnn_cout;i++){
            writel(i,v->regs+0xac);readl(v->regs+0xac);t->output[i]=readl(v->regs+0xb0);
        }
        ret=copy_to_user(u,t,sizeof(*t))?-EFAULT:0;
cnn_tile_out:kfree(t);return ret;
    }
    if(v->cnn_supported)return -EOPNOTSUPP;
    if(cmd==PANGO_VOICE_IOC_MODEL){
        struct pango_voice_model *m=memdup_user(u,sizeof(*m));
        if(IS_ERR(m))return PTR_ERR(m);
        ret=voice_model(v,m);kfree(m);return ret;
    }
    if(!v->model_loaded)return -ENODATA;
    if(cmd==PANGO_VOICE_IOC_MODE){
        u32 mode;
        if(copy_from_user(&mode,u,sizeof(mode)))return -EFAULT;
        if(mode>1)return -EINVAL;
        ret=voice_disable(v);if(ret)return ret;
        writel(2,v->regs+8);writel(mode,v->regs+0x5c);mb();
        return readl(v->regs+0x5c)==mode?0:-EIO;
    }
    if(cmd==PANGO_VOICE_IOC_FRAME){
        struct pango_voice_frame *f=memdup_user(u,sizeof(*f));
        if(IS_ERR(f))return PTR_ERR(f);
        if(f->timeout_us>1000000 || f->reserved[0] || f->reserved[1]){ret=-EINVAL;goto frame_out;}
        if(readl(v->regs+0x5c) || (readl(v->regs+0x0c)&(BIT(0)|BIT(3)))){ret=-EBUSY;goto frame_out;}
        writel(2,v->regs+8);writel(1,v->regs+8);
        for(i=0;i<400;i++)writel((u16)f->samples[i],v->regs+0x24);
        ret=voice_wait(v,BIT(1),f->timeout_us);
        if(!ret){
            rmb();
            for(i=0;i<5;i++){u32 word;writel(i,v->regs+0x60);word=readl(v->regs+0x64);memcpy(f->features+i*4,&word,4);}
            f->cycles=readl(v->regs+0x40);writel(8,v->regs+8);
            if(copy_to_user(u,f,sizeof(*f)))ret=-EFAULT;
        }
frame_out:kfree(f);return ret;
    }
    if(cmd==PANGO_VOICE_IOC_INFER){
        struct pango_voice_infer f;
        u32 result;
        if(copy_from_user(&f,u,sizeof(f)))return -EFAULT;
        if(f.timeout_us>1000000 || (f.flags&~1u) || f.reserved[0] || f.reserved[1])return -EINVAL;
        if(readl(v->regs+0x0c)&BIT(3))return -EBUSY;
        writel(0,v->regs+0x30);
        for(i=0;i<10;i++)writel(get_unaligned_le32(f.input+i*4),v->regs+0x34);
        wmb();writel(4,v->regs+8);ret=voice_wait(v,BIT(4),f.timeout_us);
        if(ret)return ret;
        rmb();result=readl(v->regs+0x48);f.token=result&255;f.confidence=(result>>8)&1023;
        f.status=readl(v->regs+0x0c);f.cycles=readl(v->regs+0x44);memset(f.outputs,0,sizeof(f.outputs));
        if(f.flags&1)for(i=0;i<121;i++){writel(i,v->regs+0x38);f.outputs[i]=readl(v->regs+0x3c);}
        return copy_to_user(u,&f,sizeof(f))?-EFAULT:0;
    }
    if(cmd==PANGO_VOICE_IOC_STREAM){
        struct pango_voice_stream *s=memdup_user(u,sizeof(*s));
        ktime_t end;
        if(IS_ERR(s))return PTR_ERR(s);
        if(s->abi_version!=1 || s->timeout_us>1000000 || s->reserved[0] || s->reserved[1]){ret=-EINVAL;goto stream_out;}
        s->feature_count=s->level_count=0;
        end=ktime_add_us(ktime_get(),s->timeout_us);
        while(!(readl(v->regs+0x0c)&(BIT(5)|BIT(7)))){
            if(!s->timeout_us || ktime_compare(ktime_get(),end)>=0)break;
            if(signal_pending(current)){ret=-ERESTARTSYS;goto stream_out;}
            usleep_range(250,500);
        }
        for(i=0;i<16 && (readl(v->regs+0x0c)&BIT(5));i++){
            struct pango_voice_feature *f=&s->frames[i];
            f->end_sample=readl(v->regs+0x68);f->sequence=readl(v->regs+0x6c);
            for(j=0;j<5;j++){u32 word;writel(j,v->regs+0x60);word=readl(v->regs+0x64);memcpy(f->values+j*4,&word,4);}
            writel(8,v->regs+8);s->feature_count++;
        }
        for(i=0;i<16 && (readl(v->regs+0x0c)&BIT(7));i++){
            s->levels[i].end_sample=readl(v->regs+0x74);s->levels[i].mean_absolute=readl(v->regs+0x70);
            writel(16,v->regs+8);s->level_count++;
        }
        s->overflows=readl(v->regs+0x50);s->capture_count=readl(v->regs+0x58);
        ret=copy_to_user(u,s,sizeof(*s))?-EFAULT:0;
stream_out:kfree(s);return ret;
    }
    return -ENOTTY;
}
static long voice_ioctl(struct file *file,unsigned int cmd,unsigned long arg)
{
    struct pango_voice_dev *v=file->private_data;
    long ret;
    if(_IOC_TYPE(cmd)!='V')return -ENOTTY;
    ret=mutex_lock_interruptible(&v->lock);if(ret)return ret;
    ret=voice_ioctl_locked(v,cmd,arg);mutex_unlock(&v->lock);return ret;
}
static int voice_open(struct inode *inode,struct file *file)
{
    struct miscdevice *misc=file->private_data;
    struct pango_voice_dev *v=container_of(misc,struct pango_voice_dev,misc);
    if(atomic_cmpxchg(&v->owner,0,1))return -EBUSY;
    file->private_data=v;v->model_loaded=false;v->cnn_loaded=false;return 0;
}
static int voice_release(struct inode *inode,struct file *file)
{
    struct pango_voice_dev *v=file->private_data;
    mutex_lock(&v->lock);voice_disable(v);writel(2,v->regs+8);v->model_loaded=false;v->cnn_loaded=false;
    mutex_unlock(&v->lock);atomic_set(&v->owner,0);return 0;
}
static const struct file_operations voice_fops={.owner=THIS_MODULE,.open=voice_open,.release=voice_release,
    .unlocked_ioctl=voice_ioctl,.llseek=no_llseek};
static int voice_probe(struct platform_device *pdev)
{
    struct pango_voice_dev *v=devm_kzalloc(&pdev->dev,sizeof(*v),GFP_KERNEL);
    if(!v)return -ENOMEM;
    v->regs=devm_platform_ioremap_resource(pdev,0);if(IS_ERR(v->regs))return PTR_ERR(v->regs);
    if(readl(v->regs)!=PANGO_VOICE_ID || readl(v->regs+4)!=PANGO_VOICE_VERSION)return -ENODEV;
    v->cnn_supported=(readl(v->regs+0x7c)&1)!=0;
    if(v->cnn_supported && (readl(v->regs+0x80)!=PANGO_VOICE_CNN_ID || readl(v->regs+0x84)!=0x10000))return -ENODEV;
    mutex_init(&v->lock);atomic_set(&v->owner,0);
    v->misc.minor=MISC_DYNAMIC_MINOR;v->misc.name="pango-voice0";v->misc.fops=&voice_fops;
    v->misc.parent=&pdev->dev;v->misc.mode=0600;platform_set_drvdata(pdev,v);
    return misc_register(&v->misc);
}
static int voice_remove(struct platform_device *pdev)
{struct pango_voice_dev *v=platform_get_drvdata(pdev);misc_deregister(&v->misc);return 0;}
static const struct of_device_id voice_of_match[]={{.compatible="pango,voice-accel-v1"},{}};
MODULE_DEVICE_TABLE(of,voice_of_match);
static struct platform_driver voice_driver={.probe=voice_probe,.remove=voice_remove,
    .driver={.name="pango-voice",.of_match_table=voice_of_match}};
module_platform_driver(voice_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Pango XQT1 local streaming features and classifier");
