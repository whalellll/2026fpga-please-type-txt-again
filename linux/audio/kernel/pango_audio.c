// SPDX-License-Identifier: GPL-2.0
/* Capture-only Linux owner for the PG2L100H AUD1 I2S block. */

#include <linux/atomic.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/uaccess.h>

#include <uapi/linux/pango_audio.h>

#define PANGO_AUDIO_REG_ID              0x00
#define PANGO_AUDIO_REG_VERSION         0x04
#define PANGO_AUDIO_REG_CONTROL         0x08
#define PANGO_AUDIO_REG_MIC_COUNT       0x18
#define PANGO_AUDIO_REG_PLAY_UNDERFLOWS 0x1c
#define PANGO_AUDIO_REG_CAPTURE_DATA    0x20
#define PANGO_AUDIO_REG_CAPTURE_STATUS  0x24
#define PANGO_AUDIO_REG_CAPTURE_OVERRUN 0x28

#define PANGO_AUDIO_CONTROL_CLEAR       BIT(0)
#define PANGO_AUDIO_CONTROL_POP         BIT(1)
#define PANGO_AUDIO_CAPTURE_LEVEL_SHIFT 16
#define PANGO_AUDIO_CAPTURE_LEVEL_MASK  GENMASK(25, 16)

#define PANGO_AUDIO_SAMPLE_RATE         16000u
#define PANGO_AUDIO_FIFO_SAMPLES        512u
#define PANGO_AUDIO_COPY_SAMPLES        128u

struct pango_audio_dev {
	struct device *dev;
	void __iomem *regs;
	atomic_t reader_open;
	struct miscdevice miscdev;
};

static u32 pango_audio_fifo_level(struct pango_audio_dev *audio)
{
	u32 status = readl(audio->regs + PANGO_AUDIO_REG_CAPTURE_STATUS);

	return (status & PANGO_AUDIO_CAPTURE_LEVEL_MASK) >>
	       PANGO_AUDIO_CAPTURE_LEVEL_SHIFT;
}

static ssize_t pango_audio_read(struct file *file, char __user *user,
				size_t bytes, loff_t *position)
{
	struct pango_audio_dev *audio = file->private_data;
	__le16 samples[PANGO_AUDIO_COPY_SAMPLES];
	size_t copied = 0;

	if (!bytes)
		return 0;
	if (bytes & (sizeof(samples[0]) - 1))
		return -EINVAL;

	while (copied < bytes) {
		size_t wanted = (bytes - copied) / sizeof(samples[0]);
		u32 available = pango_audio_fifo_level(audio);
		u32 batch;
		u32 index;

		if (!available) {
			if (copied)
				break;
			if (file->f_flags & O_NONBLOCK)
				return -EAGAIN;
			if (signal_pending(current))
				return -ERESTARTSYS;
			usleep_range(250, 500);
			continue;
		}

		batch = min_t(u32, available, PANGO_AUDIO_COPY_SAMPLES);
		batch = min_t(u32, batch, wanted);
		for (index = 0; index < batch; ++index) {
			u32 raw = readl(audio->regs + PANGO_AUDIO_REG_CAPTURE_DATA);
			s32 signed_sample = (s32)(raw << 8) >> 8;

			samples[index] = cpu_to_le16((s16)(signed_sample >> 8));
			writel(PANGO_AUDIO_CONTROL_POP,
			       audio->regs + PANGO_AUDIO_REG_CONTROL);
			/* Order the destructive pop before reading the next head. */
			readl(audio->regs + PANGO_AUDIO_REG_CAPTURE_STATUS);
		}
		if (copy_to_user(user + copied, samples,
				 batch * sizeof(samples[0])))
			return copied ? (ssize_t)copied : -EFAULT;
		copied += batch * sizeof(samples[0]);
	}

	return copied;
}

static long pango_audio_ioctl(struct file *file, unsigned int command,
			      unsigned long argument)
{
	struct pango_audio_dev *audio = file->private_data;
	void __user *user = (void __user *)argument;

	if (_IOC_TYPE(command) != PANGO_AUDIO_IOC_MAGIC)
		return -ENOTTY;

	switch (command) {
	case PANGO_AUDIO_IOC_GET_INFO: {
		struct pango_audio_info info = {
			.abi_version = PANGO_AUDIO_ABI_VERSION,
			.device_id = readl(audio->regs + PANGO_AUDIO_REG_ID),
			.device_version = readl(audio->regs + PANGO_AUDIO_REG_VERSION),
			.sample_rate_hz = PANGO_AUDIO_SAMPLE_RATE,
			.sample_format = PANGO_AUDIO_FORMAT_S16_LE,
			.channels = 1,
			.fifo_samples = PANGO_AUDIO_FIFO_SAMPLES,
			.features = PANGO_AUDIO_FEATURE_POLLING |
				    PANGO_AUDIO_FEATURE_EXCLUSIVE_READER |
				    PANGO_AUDIO_FEATURE_CAPTURE_FIFO,
		};

		return copy_to_user(user, &info, sizeof(info)) ? -EFAULT : 0;
	}
	case PANGO_AUDIO_IOC_GET_STATS: {
		struct pango_audio_stats stats = {
			.abi_version = PANGO_AUDIO_ABI_VERSION,
			.fifo_level = pango_audio_fifo_level(audio),
			.microphone_samples = readl(audio->regs +
						 PANGO_AUDIO_REG_MIC_COUNT),
			.fifo_overflows = readl(audio->regs +
						 PANGO_AUDIO_REG_CAPTURE_OVERRUN),
			.playback_underflows = readl(audio->regs +
						  PANGO_AUDIO_REG_PLAY_UNDERFLOWS),
		};

		return copy_to_user(user, &stats, sizeof(stats)) ? -EFAULT : 0;
	}
	case PANGO_AUDIO_IOC_CLEAR:
		writel(PANGO_AUDIO_CONTROL_CLEAR,
		       audio->regs + PANGO_AUDIO_REG_CONTROL);
		readl(audio->regs + PANGO_AUDIO_REG_CAPTURE_STATUS);
		return 0;
	default:
		return -ENOTTY;
	}
}

static int pango_audio_open(struct inode *inode, struct file *file)
{
	struct miscdevice *misc = file->private_data;
	struct pango_audio_dev *audio =
		container_of(misc, struct pango_audio_dev, miscdev);

	int ret;

	if (atomic_cmpxchg(&audio->reader_open, 0, 1))
		return -EBUSY;
	file->private_data = audio;
	writel(PANGO_AUDIO_CONTROL_CLEAR,
	       audio->regs + PANGO_AUDIO_REG_CONTROL);
	readl(audio->regs + PANGO_AUDIO_REG_CAPTURE_STATUS);
	ret = nonseekable_open(inode, file);
	if (ret)
		atomic_set(&audio->reader_open, 0);
	return ret;
}

static int pango_audio_release(struct inode *inode, struct file *file)
{
	struct pango_audio_dev *audio = file->private_data;

	atomic_set(&audio->reader_open, 0);
	return 0;
}

static const struct file_operations pango_audio_fops = {
	.owner = THIS_MODULE,
	.open = pango_audio_open,
	.release = pango_audio_release,
	.read = pango_audio_read,
	.unlocked_ioctl = pango_audio_ioctl,
	.llseek = no_llseek,
};

static int pango_audio_probe(struct platform_device *pdev)
{
	struct pango_audio_dev *audio;
	u32 id;
	u32 version;
	int ret;

	audio = devm_kzalloc(&pdev->dev, sizeof(*audio), GFP_KERNEL);
	if (!audio)
		return -ENOMEM;
	audio->dev = &pdev->dev;
	audio->regs = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(audio->regs))
		return PTR_ERR(audio->regs);

	id = readl(audio->regs + PANGO_AUDIO_REG_ID);
	version = readl(audio->regs + PANGO_AUDIO_REG_VERSION);
	if (id != PANGO_AUDIO_ID || version != PANGO_AUDIO_VERSION)
		return dev_err_probe(&pdev->dev, -ENODEV,
				     "ABI mismatch id=%08x version=%08x\n",
				     id, version);

	atomic_set(&audio->reader_open, 0);
	audio->miscdev.minor = MISC_DYNAMIC_MINOR;
	audio->miscdev.name = "pango-audio0";
	audio->miscdev.fops = &pango_audio_fops;
	audio->miscdev.parent = &pdev->dev;
	audio->miscdev.mode = 0600;
	ret = misc_register(&audio->miscdev);
	if (ret)
		return dev_err_probe(&pdev->dev, ret,
				     "cannot register misc device\n");

	platform_set_drvdata(pdev, audio);
	dev_info(&pdev->dev,
		 "I2S capture ready: /dev/%s, %u Hz mono s16le, polling\n",
		 audio->miscdev.name, PANGO_AUDIO_SAMPLE_RATE);
	return 0;
}

static int pango_audio_remove(struct platform_device *pdev)
{
	struct pango_audio_dev *audio = platform_get_drvdata(pdev);

	misc_deregister(&audio->miscdev);
	return 0;
}

static const struct of_device_id pango_audio_of_match[] = {
	{ .compatible = "pango,audio-capture-v2" },
	{ }
};
MODULE_DEVICE_TABLE(of, pango_audio_of_match);

static struct platform_driver pango_audio_driver = {
	.probe = pango_audio_probe,
	.remove = pango_audio_remove,
	.driver = {
		.name = "pango-audio",
		.of_match_table = pango_audio_of_match,
	},
};
module_platform_driver(pango_audio_driver);

MODULE_DESCRIPTION("Pango AUD1 capture FIFO driver");
MODULE_AUTHOR("SoC V4 project");
MODULE_LICENSE("GPL");
