# Picture 私有 FAT 写入兼容库

fat_camera.c/h、fat_boot_prefix.c/h及故障注入测试逐字来自本分支检查点7f0ba644。
main CPU80的sw/bootloader保持原样；其通用camera_sd继续链接main FAT库。
Picture安装器和命名空间工具显式链接这里的扩展，保留CID/CRC、create-only、
不确定写入后停止、root pair事务和前缀备份等原保护。

主机测试用内存卡；编译camera_sd测试翻译单元时强制包含此fat_camera.h，
避免与main头的结构布局混用。实际介质安装不在2026-10-23无板任务中，
必须等待设备回归并使用适用的身份核验和用户授权。
2026-10-20历史归档脚本应在其原检查点重放，不重写旧安装回执的源身份。
