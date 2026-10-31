# Picture_new 整层软件快路径候选

这里的 `vision32_layer.c` 是独立的软件覆盖源。能在 1 MiB scratch 中整层运行的
卷积使用原有平面循环；大型卷积保留空间分块及 halo。模型、整数规则、驱动 ABI、
32 路 MAC 和 P3 位流不变。

原 `linux/picture_new/vision32_layer.c` 是 P3 冻结正确性证据的一部分，保留原字节。
本覆盖源明确由以下构建入口选用，不把旧源码的回归冒充本覆盖源的验证：

```powershell
G:/py/ana/python.exe -X utf8 scripts/build_picture_whole_fast.py `
  --assets <包含 manifest.json 和 timing-assets.tar.gz 的真实三模型目录> `
  --output build/picture-whole-fast-rebuild `
  --expected-binary-sha256 f2dac66d005ee4417e7c3c0c210a015d2ae3f1c008907d7f087d3967dc9a61e0
```

该入口在候选 `build/` 的新目录中组装源码，WSL 构建目录使用 `/mnt/g/fpga/...`，
Windows 与 WSL 临时目录也位于本次构建树中。原冻结构建脚本保留原字节，仅在本次
工作区副本中替换构建目录与临时目录并记录副本哈希。它运行原三图整数黄金对照、主机和 RV32 接口检查，记录
每份输入及结果哈希，并验证二进制与指定版本完全一致。它不修改冻结硬件输入，
不访问 SD 或板卡。当前验证记录为 `build/opt60-picture-fast-rebuild-01/result.json`；
写卡记录为 `build/opt60-p3-picture-fast-deployment-01/result.json`。
当前目录规则下的重建记录为 `build/opt60-picture-fast-workspace-rebuild-02/result.json`，
其二进制仍与 SD 中的版本一致；早期外部构建证据保留原始身份。

当前为待板测候选。离线输出一致及写卡成功不代表性能不回退、30 fps 或正式交付通过。
