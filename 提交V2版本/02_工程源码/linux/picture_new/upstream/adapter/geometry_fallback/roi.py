# -*- coding: utf-8 -*-
"""board 四角 -> 两阶段检测器 ROI（全链自动化：ROI 不再需要外部输入）。

契约（退回提示词 T1/T3）：ROI = 四角外接矩形。为满足 v1 README 的硬约束
"不得裁去棋盘上棋子的轮廓"（棋子圆心恰在最外圈交点上、半径约 25px，
外接矩形会把最外圈棋子的轮廓裁掉近半），外接矩形外扩 pad 像素（默认 40，
= 半径 25 + 余量），并夹到图像边界。pad 记录进评估报告。
"""
from __future__ import annotations

import numpy as np

DEFAULT_PAD = 40.0


def quad_to_roi(quad, img_w=1280, img_h=720, pad=DEFAULT_PAD):
    """四角（任意顺序）-> [x1, y1, x2, y2] 整数半开区间 ROI。"""
    q = np.asarray(quad, dtype=float).reshape(-1, 2)
    x1 = max(0, int(np.floor(q[:, 0].min() - pad)))
    y1 = max(0, int(np.floor(q[:, 1].min() - pad)))
    x2 = min(img_w, int(np.ceil(q[:, 0].max() + pad)))
    y2 = min(img_h, int(np.ceil(q[:, 1].max() + pad)))
    if not (0 <= x1 < x2 <= img_w and 0 <= y1 < y2 <= img_h):
        raise ValueError("degenerate ROI: [%d,%d,%d,%d]" % (x1, y1, x2, y2))
    return [x1, y1, x2, y2]
