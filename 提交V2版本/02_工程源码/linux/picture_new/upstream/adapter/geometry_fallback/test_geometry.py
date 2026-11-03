# -*- coding: utf-8 -*-
"""几何模块单元测试（pytest 或直接 python test_geometry.py）。

覆盖：
  1. 测试向量全量回放（corners/piecefit/expect_fail）
  2. 性质测试：H 往返、90 交点数与序、真实预标四角全量扫描
  3. piece_fit 恢复精度（合成已知真值）
  4. ROI 推导（含边缘棋子保护性外扩）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from geometry.board_perspective import (  # noqa: E402
    GeometryDegenerateError, choose_pairing, geometry_from_corners, homography_from_quad,
)
from geometry.geometry_contract import (  # noqa: E402
    GRID_COLS, GRID_ROWS, Geometry, invert_homography,
)
from geometry.piece_fit import assign_grid, fit_geometry_piece  # noqa: E402
from geometry.roi import quad_to_roi  # noqa: E402

# 基线 = tar 版预标（通过 board_labels_sha256.txt 校验，见交接报告 §3）
BOARD_DIR = (HERE.parent.parent / "训练交付包_新方案_20261018" /
             "训练交付包_新方案_20261018" / "board")


def load_vectors():
    with open(HERE / "test_vectors" / "vectors.json", encoding="utf-8") as f:
        return json.load(f)["vectors"]


def test_vectors_corners():
    vectors = load_vectors()
    n = 0
    for v in vectors:
        if v["kind"] != "corners":
            continue
        g = geometry_from_corners(np.array(v["input"]["quad"], float), confidence=0.9,
                                  reorder=v["input"].get("reorder", False))
        e = v["expect"]
        assert g.grid_pairing == e["pairing"], v["name"]
        assert np.abs(g.quad - np.array(e["quad"], float)).max() < 1e-9, v["name"]
        assert np.abs(g.H - np.array(e["H"], float)).max() < 1e-6 * max(1, np.abs(g.H).max()), v["name"]
        assert np.abs(g.points() - np.array(e["points90"], float)).max() < 1e-6, v["name"]
        n += 1
    assert n >= 11, "expected >=11 corners cases, got %d" % n


def test_vectors_piecefit():
    vectors = load_vectors()
    n = 0
    for v in vectors:
        if v["kind"] not in ("piecefit", "piecefit_ambig"):
            continue
        seed = None if v["input"]["seed"] is None else np.array(v["input"]["seed"], float)
        g = fit_geometry_piece(np.array(v["input"]["centers"], float), seed_quad=seed)
        assert g is not None, v["name"]
        e = v["expect"]
        assert np.abs(g.quad - np.array(e["quad"], float)).max() < 1e-9, v["name"]
        assert g.meta["n_kept"] == e["n_kept"], v["name"]
        assert abs(g.meta["residual_p95_cell"] - e["p95"]) < 1e-12, v["name"]
        assert np.abs(g.points() - np.array(e["points90"], float)).max() < 1e-6, v["name"]
        n += 1
    assert n >= 10, "expected >=10 piecefit cases, got %d" % n


def test_vectors_expect_fail():
    vectors = load_vectors()
    n = 0
    for v in vectors:
        if v["kind"] != "expect_fail":
            continue
        if "centers" in v["input"]:
            seed = None if v["input"]["seed"] is None else np.array(v["input"]["seed"], float)
            assert fit_geometry_piece(np.array(v["input"]["centers"], float), seed_quad=seed) is None, v["name"]
        else:
            try:
                geometry_from_corners(np.array(v["input"]["quad"], float), confidence=0.9)
            except GeometryDegenerateError:
                pass
            else:
                raise AssertionError("expected degenerate failure: " + v["name"])
        n += 1
    assert n >= 3


def test_homography_roundtrip_all_real_quads():
    """1042 份真实预标四角：quad->H->90 交点->逆映射回格坐标往返一致。"""
    files = sorted(BOARD_DIR.glob("IMG*.json"))
    assert len(files) == 1042
    bad = []
    for p in files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        quad = np.array(doc["shapes"][0]["points"], float)
        try:
            g = geometry_from_corners(quad, confidence=1.0)
        except GeometryDegenerateError as e:
            bad.append((p.stem, "degenerate: %s" % e))
            continue
        pts = g.points()
        assert pts.shape == (90, 2)
        back = g.grid_of(pts)
        target = np.array([[c, r] for r in range(10) for c in range(9)], float)
        if np.abs(back - target).max() > 1e-6:
            bad.append((p.stem, "roundtrip %.2e" % np.abs(back - target).max()))
    assert not bad, "bad frames: %s" % bad[:5]


def test_piecefit_recovers_true_quad():
    rng = np.random.RandomState(7)
    grids = [(c, r) for c in range(9) for r in range(10)]
    for trial in range(5):
        # 横放真实形态棋盘（cell≈60，方格）+ 轻透视（每角 ±0.2 格）
        cell = 60.0
        quad = np.array([[660 + rng.uniform(-25, 25), 100 + rng.uniform(-18, 18)],
                         [660 + 9 * cell + rng.uniform(-25, 25), 100 + rng.uniform(-18, 18)],
                         [660 + 9 * cell + rng.uniform(-25, 25), 100 + 8 * cell + rng.uniform(-18, 18)],
                         [660 + rng.uniform(-25, 25), 100 + 8 * cell + rng.uniform(-18, 18)]])
        H = homography_from_quad(quad, choose_pairing(quad))
        assert choose_pairing(quad) == "transposed", "landscape board expected"
        sel = rng.choice(len(grids), size=24, replace=False)
        gpts = np.array([grids[i] for i in sel], float)
        ph = np.hstack([gpts, np.ones((len(gpts), 1))]) @ H.T
        centers = ph[:, :2] / ph[:, 2:3]
        centers = centers + rng.normal(0, 1.0, centers.shape)
        seed = quad + rng.uniform(-10, 10, size=2)  # 平移型种子
        geom = fit_geometry_piece(centers, seed_quad=seed)
        assert geom is not None, "trial %d no solution" % trial
        assert np.abs(geom.quad - quad).max() < 4.0, (trial, np.abs(geom.quad - quad).max())
        gp, res, ok = assign_grid(geom, centers)
        assert ok.sum() >= 20, (trial, ok.sum())


def test_geometry_sources_and_serialization():
    q = np.array([[660, 110], [1202, 111], [1199, 592], [661, 588]], float)
    g = geometry_from_corners(q, confidence=0.8)
    d = g.to_dict()
    g2 = Geometry.from_dict(d)
    assert np.abs(g2.quad - g.quad).max() < 1e-9
    assert g2.source == "board_model"
    c = g.__class__.from_dict(json.loads(json.dumps(d)))
    tmp = HERE / "test_vectors" / "_tmp_geom.json"
    c.save(tmp)
    g3 = Geometry.load(tmp)
    tmp.unlink()
    assert np.abs(g3.points() - g.points()).max() < 1e-6
    cached = g.__class__(quad=g.quad, source="cached", confidence=0.5, H=g.H)
    assert cached.source == "cached"


def test_roi():
    quad = np.array([[660, 110], [1202, 111], [1199, 592], [661, 588]], float)
    roi = quad_to_roi(quad)
    # pad=40：外接矩形 (660,110)-(1202,592) -> floor/ceil 后 (620,70)-(1242,632)
    assert roi == [620, 70, 1242, 632], roi
    # 边缘棋子（半径 25 圆心在四角）完整包含
    assert roi[0] <= 660 - 25 and roi[1] <= 110 - 25
    assert roi[2] >= 1202 + 25 and roi[3] >= 592 + 25
    # 越界裁剪
    roi2 = quad_to_roi(np.array([[0, 0], [50, 2], [48, 60], [2, 58]], float))
    assert roi2 == [0, 0, 90, 100]


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS %s" % t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL %s: %r" % (t.__name__, e))
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
