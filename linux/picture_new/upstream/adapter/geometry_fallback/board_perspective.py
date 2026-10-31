# -*- coding: utf-8 -*-
"""主几何路线：棋盘四角 -> 透视映射 -> 90 交点。

数学过程
--------
1. 输入四角 quad = [TL, TR, BR, BL]（图像坐标，顺时针左上起）。
2. 按 quad 长短边决定配对（同 board_common.grid_corner_pairing）：
   9 格轴（列 0..8）应对应较短边对、10 格轴（行 0..9）对应较长边对，
   棋盘横放（行轴水平）时用转置配对。网格的旋转/翻转对称保持格点不变，
   只需区分是否转置。
3. 用 4 对点解 8 参数单应 H（格坐标 -> 图像坐标），DLT 归一化后精确求解。
4. H 作用于 90 个整数格点得交点；H 逆作用于图像点得连续格坐标。

退化处理
--------
- 三点近共线 / 凸性破坏 / 面积过小：refuse（抛 GeometryDegenerateError）。
  判据：相邻边叉积相对量 |cross| / (|e1|·|e2|) < REL_CROSS_MIN 视为近退化；
  面积 < MIN_AREA_PX 视为退化。
- 配对歧义（长短边长度接近，比例在 [1/PAIR_RATIO_GUARD, PAIR_RATIO_GUARD] 内）：
  仍给出结果但在 meta.pairing_ambiguous=True 中标记，调用方可拒用。

置信度语义（source=board_model）：由调用方传入模型置信度（如角点回归的
1 - 归一化误差或热图峰值的软 argmax 置信度），本模块不生成。
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .geometry_contract import (
    GRID_COLS,
    GRID_ROWS,
    GRID_CORNERS_STANDARD,
    GRID_CORNERS_TRANSPOSED,
    Geometry,
)

REL_CROSS_MIN = 5e-3      # 相对叉积下限（约 0.29° 最小内角偏移）
MIN_AREA_PX = 1000.0      # 四边形最小面积（像素²）
PAIR_RATIO_GUARD = 1.15   # 长短边比例低于该值视为配对歧义


class GeometryDegenerateError(ValueError):
    pass


def order_corners(q: np.ndarray) -> np.ndarray:
    """任意四点 -> 顺时针 [左上, 右上, 右下, 左下]（同 board_common.order_corners）。"""
    q = np.asarray(q, dtype=float).reshape(4, 2)
    s = q[:, 0] + q[:, 1]
    d = q[:, 0] - q[:, 1]
    return np.array([q[np.argmin(s)], q[np.argmax(d)], q[np.argmax(s)], q[np.argmin(d)]])


def check_quad(quad: np.ndarray) -> dict:
    """四边形合法性检查。返回几何信息 dict；非法抛 GeometryDegenerateError。"""
    q = np.asarray(quad, dtype=float).reshape(4, 2)
    x, y = q[:, 0], q[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    if area < MIN_AREA_PX:
        raise GeometryDegenerateError("quad area %.1f px^2 below minimum %g" % (area, MIN_AREA_PX))
    e = np.roll(q, -1, axis=0) - q
    lens = np.linalg.norm(e, axis=1)
    if np.any(lens < 1e-9):
        raise GeometryDegenerateError("duplicate adjacent corners")
    cross = np.cross(e, np.roll(e, -1, axis=0))
    rel = np.abs(cross) / (lens * np.roll(lens, -1))
    if not (np.all(cross > 0) or np.all(cross < 0)):
        raise GeometryDegenerateError("non-convex quad")
    if np.any(rel < REL_CROSS_MIN):
        i = int(np.argmin(rel))
        raise GeometryDegenerateError(
            "near-degenerate quad: relative cross %.2e at corner %d (min %.2e)" % (rel[i], i, REL_CROSS_MIN)
        )
    lh = (lens[0] + lens[2]) / 2.0   # 上/下边（水平边对）
    lv = (lens[1] + lens[3]) / 2.0   # 左/右边（竖直边对）
    return {"area": float(area), "rel_cross_min": float(rel.min()), "lh": float(lh), "lv": float(lv)}


def choose_pairing(quad: np.ndarray) -> str:
    """长短边配对：行轴(10格)应对应较长边对。lv>=lh 用标准配对，否则转置。"""
    info = check_quad(quad)
    return "standard" if info["lv"] >= info["lh"] else "transposed"


def homography_from_quad(quad: np.ndarray, pairing: Optional[str] = None) -> np.ndarray:
    """4 对格角点->图像角点 的单应（归一化 DLT，精确 4 点解）。"""
    q = np.asarray(quad, dtype=float).reshape(4, 2)
    if pairing is None:
        pairing = choose_pairing(q)
    gc = GRID_CORNERS_STANDARD if pairing == "standard" else GRID_CORNERS_TRANSPOSED
    return fit_homography_exact(gc, q)


def fit_homography_exact(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """N=4 点对的精确单应（归一化 + 8×8 线性系统）。"""
    src = np.asarray(src, dtype=float).reshape(4, 2)
    dst = np.asarray(dst, dtype=float).reshape(4, 2)
    Ts, s = _normalize_pts(src)
    Td, d = _normalize_pts(dst)
    A = np.zeros((8, 8))
    b = np.zeros(8)
    for i in range(4):
        x, y = s[i]
        X, Y = d[i]
        A[2 * i] = [x, y, 1, 0, 0, 0, -X * x, -X * y]
        b[2 * i] = X
        A[2 * i + 1] = [0, 0, 0, x, y, 1, -Y * x, -Y * y]
        b[2 * i + 1] = Y
    h = np.linalg.solve(A, b)
    Hn = np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])
    H = np.linalg.inv(Td) @ Hn @ Ts
    H = H / H[2, 2]
    if not np.isfinite(H).all():
        raise GeometryDegenerateError("non-finite homography")
    return H


def _normalize_pts(pts: np.ndarray):
    c = pts.mean(axis=0)
    d = np.linalg.norm(pts - c, axis=1).mean()
    s = np.sqrt(2.0) / max(d, 1e-12)
    T = np.array([[s, 0.0, -s * c[0]], [0.0, s, -s * c[1]], [0.0, 0.0, 1.0]])
    return T, (pts - c) * s


def geometry_from_corners(
    quad: np.ndarray,
    confidence: float,
    pairing: Optional[str] = None,
    meta: Optional[dict] = None,
    reorder: bool = False,
) -> Geometry:
    """board_model / manual 生产者入口：四角 -> Geometry（含 90 交点）。"""
    q = order_corners(quad) if reorder else np.asarray(quad, dtype=float).reshape(4, 2)
    info = check_quad(q)
    if pairing is None:
        pairing = choose_pairing(q)
    ratio = max(info["lh"], info["lv"]) / max(min(info["lh"], info["lv"]), 1e-9)
    m = dict(info)
    m["pairing_edge_ratio"] = float(ratio)
    m["pairing_ambiguous"] = bool(ratio < PAIR_RATIO_GUARD)
    if meta:
        m.update(meta)
    H = homography_from_quad(q, pairing)
    return Geometry(quad=q, source="board_model", confidence=float(confidence),
                    H=H, grid_pairing=pairing, meta=m)


def geometry_from_cached(g: Geometry, age_frames: int) -> Geometry:
    """cached 生产者：沿用旧 Geometry，置信度随帧龄衰减。"""
    conf = max(0.0, float(g.confidence) * (0.98 ** max(0, int(age_frames))))
    out = Geometry(quad=g.quad.copy(), source="cached", confidence=conf,
                   H=g.H.copy(), grid_pairing=g.grid_pairing,
                   meta={**g.meta, "age_frames": int(age_frames), "origin_source": g.source})
    return out


def geometry_manual(quad: np.ndarray, pairing: Optional[str] = None) -> Geometry:
    """manual 生产者：人工指定四角，置信度恒 1.0。"""
    q = order_corners(quad) if not _is_canonical(quad) else np.asarray(quad, dtype=float).reshape(4, 2)
    if pairing is None:
        pairing = choose_pairing(q)
    return Geometry(quad=q, source="manual", confidence=1.0,
                    H=homography_from_quad(q, pairing), grid_pairing=pairing, meta={})


def _is_canonical(quad) -> bool:
    q = np.asarray(quad, dtype=float).reshape(4, 2)
    return bool(np.abs(q - order_corners(q)).max() < 1e-6)
