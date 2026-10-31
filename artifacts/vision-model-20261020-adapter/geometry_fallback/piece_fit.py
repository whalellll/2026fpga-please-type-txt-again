# -*- coding: utf-8 -*-
"""备几何路线（geometry_fallback）：棋子圆心 -> 网格拟合。

与 board_common.py 的 icp_fit 同一核心算法（ICP：映射->吸附最近格点->剔点->
重拟合），抽成无 LabelMe / 无路径依赖的可复用模块。这也是 FEN 真值生成器
（圆心->逐帧网格->FEN）的同一核心：真值生成时 seed 用人工复核网格，
走 piece_fit_refine 单轮精修。

算法
----
1. 初值：seed quad（时序缓存/人工），或无 seed 时枚举包络扩展候选
   （棋子包络 ± 0/1 格，9 变体），icp_fit_multi 按内点数择优；
   空边歧义（内点数与残差打平）靠时序 seed 距离裁决。
2. 每轮迭代：格角配对 -> H(grid->image) -> 圆心逆映射到格坐标 ->
   吸附最近整数格点（首轮容差 0.45 格，之后 0.26 格）-> 内点子集
   重拟合（边界线法与全对应单应法二选一，一致时取边界线法）。
3. 终检：内点数 >= min_kept；输出 Geometry(source=piece_fit)。

置信度语义（source=piece_fit）：
  confidence = (内点数 / 圆心总数，截到 [0,1]) × 0.7 + 0.3 × exp(-4·p95残差)
  内点比例衡量支持度，p95 残差（格）衡量拟合优度；两者都在 meta 里带出。

少子/离群处理
------------
- 圆心 < min_kept（默认 6）直接失败（返回 None，不猜）。
- 棋盘外/悬空棋子：残差 > OFF_BOARD_RES(0.6 格)的点在截尾统计里剔除，
  不参与否决（重置段存在桌面上待摆回的棋子）。
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np

from .board_perspective import (
    GeometryDegenerateError,
    check_quad,
    fit_homography_exact,
    order_corners,
)
from .geometry_contract import (
    GRID_COLS,
    GRID_ROWS,
    GRID_CORNERS_STANDARD,
    GRID_CORNERS_TRANSPOSED,
    Geometry,
    apply_homography,
    invert_homography,
)

HIGH_PIECE_MIN = 18       # >=18 直接拟合，<18 建议借用（沿预标任务书口径）
ICP_ITERS = 4
SNAP_TOL0 = 0.45          # 首轮吸附容差（格）
FINAL_TOL = 0.26          # 终检容差（格）
MIN_KEPT = 6              # 最少内点数
OFF_BOARD_RES = 0.6       # 疑似棋盘外棋子残差线（格）
METHOD_DIFF_TAKE_LINE = 15.0  # 边界线法与单应法一致阈值（px）


# ---------------- 单应（DLT，最小二乘，N>=4） ----------------

def _normalize_pts(pts):
    c = pts.mean(axis=0)
    d = np.linalg.norm(pts - c, axis=1).mean()
    s = np.sqrt(2.0) / max(d, 1e-12)
    T = np.array([[s, 0.0, -s * c[0]], [0.0, s, -s * c[1]], [0.0, 0.0, 1.0]])
    return T, (pts - c) * s


def fit_homography_ls(src: np.ndarray, dst: np.ndarray) -> Optional[np.ndarray]:
    """N>=4 点对的最小二乘单应（归一化 DLT，8×8 正规方程）。"""
    src = np.asarray(src, dtype=float).reshape(-1, 2)
    dst = np.asarray(dst, dtype=float).reshape(-1, 2)
    n = len(src)
    if n < 4:
        return None
    Ts, s = _normalize_pts(src)
    Td, d = _normalize_pts(dst)
    A = np.zeros((2 * n, 9))
    x, y = s[:, 0], s[:, 1]
    X, Y = d[:, 0], d[:, 1]
    o = np.zeros(n)
    A[0::2] = np.stack([x, y, np.ones(n), o, o, o, -X * x, -X * y, -X], axis=1)
    A[1::2] = np.stack([o, o, o, x, y, np.ones(n), -Y * x, -Y * y, -Y], axis=1)
    _, _, Vt = np.linalg.svd(A, full_matrices=False)
    Hn = Vt[-1].reshape(3, 3)
    H = np.linalg.inv(Td) @ Hn @ Ts
    if not np.isfinite(H).all() or abs(H[2, 2]) < 1e-12:
        return None
    return H / H[2, 2]


# ---------------- 边界线法（TLS + MAD 剔除） ----------------

def fit_line_tls(P, rounds=3, abs_floor=1.0):
    M = np.asarray(P, dtype=float)
    line = None
    for _ in range(rounds):
        if len(M) < 2:
            return None
        c = M.mean(axis=0)
        _, _, Vt = np.linalg.svd(M - c, full_matrices=False)
        d = Vt[0]
        r = np.abs((M - c) @ np.array([-d[1], d[0]]))
        med = float(np.median(r))
        mad = float(np.median(np.abs(r - med))) + 1e-9
        thr = med + 3.0 * 1.4826 * mad + abs_floor
        keep = r < thr
        if keep.sum() < 2:
            break
        line = (c, d)
        if keep.all():
            break
        M = M[keep]
    if line is None or len(M) < 2:
        return None
    c = M.mean(axis=0)
    _, _, Vt = np.linalg.svd(M - c, full_matrices=False)
    return (c, Vt[0]), int(len(M))


def intersect_lines(l1, l2):
    (p1, d1), (p2, d2) = l1, l2
    A = np.column_stack([d1, -d2])
    if abs(np.linalg.det(A)) < 1e-9:
        return None
    try:
        t, _ = np.linalg.solve(A, p2 - p1)
    except np.linalg.LinAlgError:
        return None
    return p1 + t * d1


def quad_from_lines(pts, gp):
    """按列/行族拟合 左/右/上/下 四条边界线并相交得四角（同 board_common）。"""
    cols = gp[:, 0].astype(int)
    rows = gp[:, 1].astype(int)
    fams, supports = {}, {}
    for key, mask in (
        ("L", cols == 0), ("R", cols == GRID_COLS),
        ("T", rows == 0), ("B", rows == GRID_ROWS),
    ):
        res = fit_line_tls(pts[mask])
        if res is None:
            return None, supports
        fams[key], supports[key] = res[0], res[1]
    corners = {
        "TL": intersect_lines(fams["T"], fams["L"]),
        "TR": intersect_lines(fams["T"], fams["R"]),
        "BR": intersect_lines(fams["B"], fams["R"]),
        "BL": intersect_lines(fams["B"], fams["L"]),
    }
    if any(v is None for v in corners.values()):
        return None, supports
    for a, b in (("T", "L"), ("T", "R"), ("B", "L"), ("B", "R")):
        if abs(np.cross(fams[a][1], fams[b][1])) < 0.25:
            return None, supports
    return order_corners([corners["TL"], corners["TR"], corners["BR"], corners["BL"]]), supports


# ---------------- 配对与格点吸附 ----------------

def grid_corner_pairing(quad) -> np.ndarray:
    q = np.asarray(quad, dtype=float)
    lh = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2.0
    lv = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2.0
    if lv >= lh:
        return GRID_CORNERS_STANDARD
    return GRID_CORNERS_TRANSPOSED


def _snap(uv: np.ndarray, xmax: float, ymax: float):
    gp = np.clip(np.rint(uv), [0.0, 0.0], [xmax, ymax])
    return gp, np.linalg.norm(uv - gp, axis=1)


# ---------------- ICP 主过程 ----------------

def icp_fit(quad0, C, iters=ICP_ITERS, min_kept=MIN_KEPT,
            final_tol=FINAL_TOL, snap_tol0=SNAP_TOL0, bounds=None):
    """以 quad0 为初值 ICP。返回 dict(quad,res,n_kept,support,method_diff) 或 None。"""
    C = np.asarray(C, dtype=float).reshape(-1, 2)
    if len(C) < min_kept:
        return None
    quad = np.asarray(quad0, dtype=float).copy()
    support, diff = None, None
    for it in range(iters):
        GC = grid_corner_pairing(quad)
        xmax, ymax = GC[:, 0].max(), GC[:, 1].max()
        Hg2i = fit_homography_exact(GC, quad)
        try:
            Hinv = invert_homography(Hg2i)
        except np.linalg.LinAlgError:
            return None
        uv = apply_homography(Hinv, C)
        gp, res = _snap(uv, xmax, ymax)
        tol = snap_tol0 if it == 0 else final_tol
        keep = res < tol
        if keep.sum() < min_kept:
            return None
        Hn = fit_homography_ls(gp[keep], C[keep])
        if Hn is None:
            return None
        quad_h = order_corners(apply_homography(Hn, GC))
        if bounds is not None:
            if not _in_bounds(quad_h, bounds):
                return None
        ql, sup = quad_from_lines(C[keep], gp[keep])
        if ql is not None:
            diff = float(np.abs(ql - quad_h).max())
            quad = ql if diff < METHOD_DIFF_TAKE_LINE else quad_h
        else:
            diff = None
            quad = quad_h
        support = sup
    GC = grid_corner_pairing(quad)
    xmax, ymax = GC[:, 0].max(), GC[:, 1].max()
    Hg2i = fit_homography_exact(GC, quad)
    try:
        Hinv = invert_homography(Hg2i)
    except np.linalg.LinAlgError:
        return None
    uv = apply_homography(Hinv, C)
    gp, res = _snap(uv, xmax, ymax)
    n_kept = int((res < final_tol).sum())
    return dict(quad=quad, res=res, n_kept=n_kept, support=support, method_diff=diff)


def _in_bounds(quad, bounds):
    m_x0, m_y0, m_x1, m_y1 = bounds
    q = np.asarray(quad, dtype=float)
    return bool(np.all(q[:, 0] > m_x0) and np.all(q[:, 0] < m_x1)
                and np.all(q[:, 1] > m_y0) and np.all(q[:, 1] < m_y1))


def envelope_candidates(C):
    """包络初值假设集：包络各边向外扩 0/1 格的 9 个变体（同 board_common）。"""
    C = np.asarray(C, dtype=float)
    x0, y0 = C.min(axis=0)
    x1, y1 = C.max(axis=0)
    w, h = x1 - x0, y1 - y0
    cx, cy = w / GRID_COLS, h / GRID_ROWS
    cands = []
    for dx0, dx1 in ((0, 0), (cx, 0), (0, cx)):
        for dy0, dy1 in ((0, 0), (cy, 0), (0, cy)):
            pad = 12.0 if (dx0 == 0 and dx1 == 0 and dy0 == 0 and dy1 == 0) else 2.0
            cands.append(order_corners(
                [[x0 - dx0 - pad, y0 - dy0 - pad],
                 [x1 + dx1 + pad, y0 - dy0 - pad],
                 [x1 + dx1 + pad, y1 + dy1 + pad],
                 [x0 - dx0 - pad, y1 + dy1 + pad]]))
    return cands


def _trim_res(res, frac=0.2, min_keep=4):
    res = np.sort(np.asarray(res, dtype=float))
    n = len(res)
    k = max(2, int(np.ceil(frac * n)))
    keep = min(n, max(min_keep, n - k))
    return res[:keep]


def icp_fit_multi(cands, C, seed=None, **kw):
    """多初值 ICP 择优：(内点数, -截尾P95, -与种子距离)。空边歧义靠 seed 裁决。"""
    seed = None if seed is None else np.asarray(seed, dtype=float)
    best, best_i, best_key = None, None, None
    for i, q0 in enumerate(cands):
        r = icp_fit(q0, C, **kw)
        if r is None:
            continue
        core = _trim_res(r["res"])
        p95 = float(core[-1]) if len(core) else 9e9
        dseed = 0.0 if seed is None else float(np.abs(r["quad"] - seed).max())
        key = (r["n_kept"], -round(p95, 2), -dseed)
        if best_key is None or key > best_key:
            best, best_i, best_key = r, i, key
    return best, best_i


def fit_geometry_piece(
    centers: Sequence[Sequence[float]],
    seed_quad: Optional[np.ndarray] = None,
    img_bounds: tuple = (-80.0, -80.0, 1280.0 + 80.0, 720.0 + 80.0),
    min_kept: int = MIN_KEPT,
) -> Optional[Geometry]:
    """piece_fit 生产者入口：棋子圆心（+可选时序种子）-> Geometry 或 None。

    少子（<min_kept）返回 None，由调用方走 cached/manual。
    """
    C = np.asarray(centers, dtype=float).reshape(-1, 2)
    if len(C) < min_kept:
        return None
    cands = []
    C_env = C
    if seed_quad is not None:
        seed_quad = np.asarray(seed_quad, dtype=float)
        cands.append(seed_quad)
        C_env = _seed_inliers(seed_quad, C)
    cands.extend(envelope_candidates(C_env))
    best, _ = icp_fit_multi(cands, C, seed=seed_quad, bounds=img_bounds, min_kept=min_kept)
    if best is None:
        return None
    quad = best["quad"]
    try:
        check_quad(quad)
    except GeometryDegenerateError:
        return None
    res = np.asarray(best["res"], dtype=float)
    onb = np.sort(res[res <= OFF_BOARD_RES])
    if len(onb) == 0:
        return None
    core = _trim_res(onb, frac=0.10, min_keep=5) if len(onb) >= 5 else onb
    p95 = float(np.percentile(core, 95))
    inlier_ratio = float(best["n_kept"]) / float(len(C))
    conf = min(1.0, inlier_ratio) * 0.7 + 0.3 * float(np.exp(-4.0 * p95))
    pairing = "standard" if grid_corner_pairing(quad) is GRID_CORNERS_STANDARD else "transposed"
    return Geometry(
        quad=quad, source="piece_fit", confidence=float(conf),
        grid_pairing=pairing, meta={
            "n_centers": int(len(C)),
            "n_kept": int(best["n_kept"]),
            "n_onboard": int(len(onb)),
            "n_off": int(len(res) - len(onb)),
            "residual_p95_cell": p95,
            "inlier_ratio": inlier_ratio,
            "method_diff_px": best["method_diff"],
            "support": {k: int(v) for k, v in (best["support"] or {}).items()},
            "used_seed": seed_quad is not None,
        },
    )


def assign_grid(geom: Geometry, centers: Sequence[Sequence[float]],
                tol: float = FINAL_TOL):
    """圆心 -> (格坐标取整, 残差)。FEN 真值生成器同款核心。"""
    C = np.asarray(centers, dtype=float).reshape(-1, 2)
    uv = geom.grid_of(C)
    gp, res = _snap(uv, GRID_COLS, GRID_ROWS)
    return gp.astype(int), res, res < tol


def _seed_inliers(seed_quad, C, tol=0.45, min_pts=6):
    GC = grid_corner_pairing(seed_quad)
    Hg2i = fit_homography_exact(GC, seed_quad)
    try:
        Hinv = invert_homography(Hg2i)
    except np.linalg.LinAlgError:
        return C
    uv = apply_homography(Hinv, C)
    _, res = _snap(uv, GC[:, 0].max(), GC[:, 1].max())
    m = res < tol
    return C[m] if m.sum() >= min_pts else C
