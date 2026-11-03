# 芯弈一号语音软件候选

会话/自动走棋来自 `origin/voice_2@a901132a7493a6402c145d9208be92d751faf118`
的 `voice/voice_2/source/`，CNN/流式前端及匹配后端来自 integrated60
`127ff9a5b517f0f298ab91492d07ef2a1cf44f5b`。逐文件原始身份在各目录
`SOURCE.json`，本次移植、构建和稳定性记录在 `ADAPTATION.json`。

`balanced24.bin` 保持 SHA256
`3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973`。
20ms 帧移、CTC beam8、FFT、量化和 CNN 数学不变；mac 路径任何设备错误不回退 CPU。

软件构建（新输出目录，不访问板卡）：

```sh
sh linux/voice_ctc/build.sh /absolute/new/output
```

产品 GUI 链接 `xqvoice_session.c`、`xqvoice_gui_flow.c`、原
`linux/voice/xqvoice_{protocol,notation}.c` 和新 `linux/voice_speech/` 实现。
后者与旧 Picture 的 `xqs_*` 同名，只能链接一份实现。已有 37 个 Picture PCM
和 7 个 voice SDK 资产不在本次导入的写入范围；缓存可以读取原有不可变 PCM 目录，
不得将本候选的缓存优化称为 1.25 倍音频素材或实板性能验收。

GUI 环境：`XQVOICE_RUNTIME=<本次xqvoice-small-cnn>`、
`XQVOICE_MODEL=<本次balanced24.bin>`、`XQVOICE_BACKEND=mac`、
`XQVOICE_AUDIO_DEVICE=/dev/pango-audio0`、`XQVOICE_STREAM_FEATURES=1`；
播报目录由 `XQVOICE_PCM` 指定，默认音量100。保留 stdin/stdout 为私有 XQW1
协议，stderr 独立传给 GUI 父进程。闲置 resident worker 不打开麦克风。

只有语音模式调用 `xqvoice_session_auto_step`/`xqvoice_gui_input`。
离开模式须先 `xqvoice_session_pause()` 等待取消和麦克风释放，随后增加棋盘/模式
revision；取消或旧 revision 的结果不能落子。会话在 RESULT 与 IDLE 都收到后，
再次核对完整棋盘快照并只提交一次唯一合法着法。

`s.timing.valid` 仅对本 revision 的完整真实麦克风请求成立：

- `endpoint_to_result_us`：VAD 结束到结果生成，包含剩余特征/CNN/CTC。
- `last_voice_to_result_us`：最后有声块到结果，包含既有450ms静音判停。
- `feature_tail_us`：VAD 结束后剩余特征处理。
- `request_us`：含等待说话和整段采集，不能用作尾延迟。

合成特征、WAV回放、取消和设备失败均不会生成有效麦克风尾延迟。
当前验证只覆盖 host/QEMU 与明确的设备算术/音频替身；真实语音准确率、声音听感、
物理按键和板端时延未由这些测试验收。
