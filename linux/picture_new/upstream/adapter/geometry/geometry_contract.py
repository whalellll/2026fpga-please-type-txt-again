# -*- coding: utf-8 -*-
"""统一 Geometry 契约。

板上四个几何生产者（board_model / piece_fit / cached / manual）共用本结构。
棋盘网格：9 列 × 10 行 = 90 个交点，格坐标 (col, row)，col ∈ 0..8，row ∈ 0..9。
四角与格坐标的配对遵循 board_common.grid_corner_pairing 的转置规则
（棋盘横放时 (0..8) 轴竖直、(0..9) 轴水平，配对自动转置）。

Geometry 结构字段：
  quad        : 4×2 图像坐标，顺时针左上起 [TL, TR, BR, BL]
  grid_pairing: "standard" | "transposed"（quad 四角与网格角的配对方式）
  H           : 3×3 单应，格坐标 (col,row) -> 图像坐标 (x,y)
  points      : 90 个交点 [{grid:[col,row], xy:[x,y]}, ...]（row 主序）
  source      : "board_model" | "piece_fit" | "cached" | "manual"
  confidence  : [0,1]，语义随 source（见各生产者文档）
  meta        : 生产者附加信息（如 piece_fit 的内点数/残差；board_model 的原始输出）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

GRID_COLS = 8   # 列角点最大下标（9 列）
GRID_ROWS = 9   # 行角点最大下标（10 行）
N_POINTS = (GRID_COLS + 1) * (GRID_ROWS + 1)

GRID_CORNERS_STANDARD = np.array(
    [[0, 0], [GRID_COLS, 0], [GRID_COLS, GRID_ROWS], [0, GRID_ROWS]], dtype=float
)
GRID_CORNERS_TRANSPOSED = np.array(
    [[0, 0], [0, GRID_ROWS], [GRID_COLS, GRID_ROWS], [GRID_COLS, 0]], dtype=float
)

VALID_SOURCES = ("board_model", "piece_fit", "cached", "manual")


@dataclass
class Geometry:
    quad: np.ndarray                     # 4×2 float64
    source: str
    confidence: float
    H: Optional[np.ndarray] = None       # 3×3 float64, grid -> image
    grid_pairing: str = "standard"       # "standard" | "transposed"
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.quad = np.asarray(self.quad, dtype=float).reshape(4, 2)
        if self.source not in VALID_SOURCES:
            raise ValueError("source must be one of %s, got %r" % (VALID_SOURCES, self.source))
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0,1]")
        if self.grid_pairing not in ("standard", "transposed"):
            raise ValueError("grid_pairing must be standard|transposed")
        if self.H is None:
            from .board_perspective import homography_from_quad
            self.H = homography_from_quad(self.quad, self.grid_pairing)
        self.H = np.asarray(self.H, dtype=float).reshape(3, 3)

    @property
    def grid_corners(self) -> np.ndarray:
        return GRID_CORNERS_STANDARD if self.grid_pairing == "standard" else GRID_CORNERS_TRANSPOSED

    def points(self) -> np.ndarray:
        """90 交点图像坐标，row 主序：[(col,row) for row in 0..9 for col in 0..8]。"""
        g = np.array([[c, r] for r in range(GRID_ROWS + 1) for c in range(GRID_COLS + 1)], dtype=float)
        return apply_homography(self.H, g)

    def grid_of(self, xy: np.ndarray) -> np.ndarray:
        """图像坐标 -> 格坐标（连续值，就近归格由调用方取整）。"""
        Hinv = invert_homography(self.H)
        return apply_homography(Hinv, np.asarray(xy, dtype=float).reshape(-1, 2))

    def to_dict(self) -> dict:
        return {
            "quad": [[round(float(x), 4), round(float(y), 4)] for x, y in self.quad],
            "grid_pairing": self.grid_pairing,
            "H": [[float(v) for v in row] for row in self.H],
            "points90": [
                {"grid": [int(c), int(r)],
                 "xy": [round(float(x), 4), round(float(y), 4)]}
                for (c, r), (x, y) in zip(
                    ((c, r) for r in range(GRID_ROWS + 1) for c in range(GRID_COLS + 1)),
                    self.points(),
                )
            ],
            "source": self.source,
            "confidence": float(self.confidence),
            "meta": self.meta,
        }

    @staticmethod
    def from_dict(d: dict) -> "Geometry":
        return Geometry(
            quad=np.array(d["quad"], dtype=float),
            source=d["source"],
            confidence=float(d["confidence"]),
            H=np.array(d["H"], dtype=float) if d.get("H") is not None else None,
            grid_pairing=d.get("grid_pairing", "standard"),
            meta=dict(d.get("meta") or {}),
        )

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)

    @staticmethod
    def load(path) -> "Geometry":
        with open(path, encoding="utf-8") as f:
            return Geometry.from_dict(json.load(f))


def apply_homography(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=float).reshape(-1, 2)
    p = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(H, dtype=float).T
    return p[:, :2] / p[:, 2:3]


def invert_homography(H: np.ndarray) -> np.ndarray:
    H = np.asarray(H, dtype=float)
    Hinv = np.linalg.inv(H)
    return Hinv / Hinv[2, 2]
