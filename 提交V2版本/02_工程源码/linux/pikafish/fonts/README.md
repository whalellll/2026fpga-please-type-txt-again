# 棋子抗锯齿字模

仅包含“帅将仕士相象马车炮兵卒”11字。来源 Noto Serif SC，字重550，固定字重后重新命名为
Xiangqi Piece Serif；源字体版权及SIL OFL 1.1许可证保存在 `source.json` 和 `OFL.txt`。
[原许可证](https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/LICENSE)。

`XiangqiPieceSerif.ttf` 是6.7KB的离线生成输入；板端不装载TTF，不依赖FreeType。
板端使用 `../xiangqi_piece_font_aa.h` 中的原生48×48字形，4bit覆盖率、16级抗锯齿，
两像素一个字节，11字共12672字节。字形完全位于棋子平坦底色内，避免在描边上错误混色。
颜色按RGB565通道混合；保留uncached DDR的32bit安全存储。

固定重建和检查入口：

```powershell
G:/py/ana/python.exe -X utf8 scripts/gen_xiangqi_piece_font.py
G:/py/ana/python.exe -X utf8 scripts/gen_xiangqi_piece_font.py --check
```

首次从完整矢量字体制作静态子集：

```powershell
G:/py/ana/python.exe -X utf8 scripts/gen_xiangqi_piece_font.py --source-font C:/Windows/Fonts/NotoSerifSC-VF.ttf --weight 550
```

字体、生成器与Pillow/FreeType版本及各字形哈希见 `source.json`、`piece-font.json`。
保留原板端布局、点击区域、棋盘与面板字模；本次没有修改RTL或1080p时序合同。
# UI 字体

标题、侧栏中英文、数字、语音提示及“楚河汉界”使用 Noto Sans SC 字重500。
`XiangqiUiSans.ttf` 是重命名后的静态字体子集，许可证为 `UI-OFL.txt`，来源记录为 `ui-source.json`。
汉字按32/48像素原生栅格，英文和数字按16/22/30/48像素生成，覆盖率为4位。
只保存所用字形，板端无需字体解析器；半透明笔画与实际RGB565背景混合。
运行 `python scripts/gen_xiangqi_ui_font.py --check` 可逐字节验证生成的头文件及 `ui-font.json`。
从系统原字体重建子集时使用 `--source-font C:/Windows/Fonts/NotoSansSC-VF.ttf`。
