/* -*- coding: utf-8 -*-
 * geometry_ref.h — 几何模块 C 参考实现（板端移植基准）
 *
 * 语义约定（与 Python 参考 src/geometry/ 一致）：
 *  - 全部使用 IEEE 754 double；板端如用定点，以本实现输出为对拍基准。
 *  - 网格：9 列 × 10 行，格坐标 (col,row)，col∈0..8，row∈0..9。
 *  - 四角 quad 顺序：顺时针左上起 [TL,TR,BR,BL]。
 *  - 配对规则：行轴(10格,GRID_ROWS=9)对应较长边对，否则转置配对。
 *  - 单应 H：格坐标->图像坐标，H[2][2] 归一化为 1。
 *  - 所有函数返回 GEOM_OK(0) 或 GEOM_ERR_*(<0)；出错时输出参数不定义。
 */
#ifndef GEOMETRY_REF_H
#define GEOMETRY_REF_H

#ifdef __cplusplus
extern "C" {
#endif

#define GEOM_GRID_COLS 8     /* 列最大下标（9 列） */
#define GEOM_GRID_ROWS 9     /* 行最大下标（10 行） */
#define GEOM_N_POINTS 90     /* (8+1)*(9+1) 交点数 */

#define GEOM_OK                0
#define GEOM_ERR_DEGENERATE   -1   /* 非凸/近共线/面积过小/单应奇异 */
#define GEOM_ERR_TOO_FEW      -2   /* 点数不足 */
#define GEOM_ERR_NO_CONVERGE  -3   /* ICP 无内点解 */
#define GEOM_ERR_INVALID      -4   /* 参数非法 */

/* 退化判据（与 Python 参考一致，board_perspective.REL_CROSS_MIN 等） */
#define GEOM_REL_CROSS_MIN   5e-3
#define GEOM_MIN_AREA_PX     1000.0
#define GEOM_CORNER_MARGIN   80.0  /* 四角允许越出图像的边距 */

typedef struct {
    double x, y;
} GeomPt;

typedef struct {
    double m[3][3];
} GeomH;

/* ---- 线性代数（内部使用 8x8 高斯消元 + 部分主元） ---- */
int geom_solve8(double A[8][8], const double b[8], double x[8]);

/* ---- 四边形检查与配对 ---- */
/* 返回 GEOM_OK；四个输出指针（area、rel_cross_min、lh、lv）均可为 NULL。 */
int geom_check_quad(const GeomPt quad[4],
                    double *area, double *rel_cross_min, double *lh, double *lv);
/* "standard"(0) 或 1(transposed)；quad 非法返回 GEOM_ERR_DEGENERATE。 */
int geom_choose_pairing(const GeomPt quad[4], int *transposed);

/* ---- 单应 ---- */
/* 4 对（格角->图像角）精确单应；pairing: 0=standard 1=transposed，-1=自动。 */
int geom_h_from_corners(const GeomPt quad[4], int pairing, GeomH *H);
/* N>=4 点对最小二乘单应（归一化 DLT + 正规方程）。 */
int geom_fit_homography_ls(const GeomPt *src, const GeomPt *dst, int n, GeomH *H);
int geom_apply_h(const GeomH *H, GeomPt p, GeomPt *out);
int geom_invert_h(const GeomH *H, GeomH *Hinv);

/* ---- 90 交点 ---- */
/* points 按 row 主序：[(col,row) for row 0..9 for col 0..8]，共 90 项。 */
int geom_grid_points(const GeomH *H, GeomPt points[GEOM_N_POINTS]);

/* ---- 圆心吸附/归格 ---- */
/* 返回吸附格点（取整并夹到 [0,8]x[0,9]），*res 输出残差（格）。 */
void geom_snap(double u, double v, int *col, int *row, double *res);

/* ---- 备路线：棋子圆心 ICP 拟合 ---- */
/* 以 seed 为初值迭代（映射->吸附->剔点->重拟合）。
 * 参数：centers 圆心数组，n 数量（>=GEOM_MIN_KEPT=6，否则 GEOM_ERR_TOO_FEW）；
 * seed 可为 NULL（无种子时用包络枚举，9 变体择优）。
 * 输出：quad（顺时针左上起）、H、n_kept、p95（截尾 10% 后 95 分位残差，格）。
 * bounds: [min_x,min_y,max_x,max_y]，四角越界即拒（可传 NULL 跳过）。
 */
#define GEOM_MIN_KEPT 6
#define GEOM_ICP_ITERS 4
#define GEOM_SNAP_TOL0 0.45
#define GEOM_FINAL_TOL 0.26
#define GEOM_OFF_BOARD_RES 0.6

int geom_piece_fit(const GeomPt *centers, int n, const GeomPt *seed,
                   const double *bounds, /* [4] 或 NULL */
                   GeomPt quad[4], GeomH *H,
                   int *n_kept, double *p95);

/* 圆心 -> 格坐标（连续 u,v），用 H 的逆。 */
int geom_grid_of(const GeomH *H, GeomPt p, double *u, double *v);

#ifdef __cplusplus
}
#endif
#endif /* GEOMETRY_REF_H */
