/* -*- coding: utf-8 -*-
 * geometry_ref.c — 几何模块 C 参考实现。
 *
 * 与 Python 参考（src/geometry/board_perspective.py, piece_fit.py）同算法：
 *  - 主路线：四角 ->（配对）-> 4 点精确单应（归一化 + 8x8 求解）-> 90 交点。
 *  - 备路线：圆心 ICP（映射->吸附最近格点->剔点->重拟合；
 *    边界线法与全对应单应法一致时取边界线法）。
 *
 * 线性求解不用 SVD：4 点精确解直接解 8x8 线性方程组；N 点最小二乘用
 * 正规方程 A^T A x = A^T b（8x8）。数值条件由 DLT 归一化保证
 * （先平移到质心、缩放到平均距离 sqrt(2)），与 Python 版一致。
 *
 * TLS 直线拟合用 2x2 协方差矩阵闭式特征分解代替 SVD，数学等价
 * （最小化正交距离的方向 = 最大特征值对应的特征向量）。
 *
 * 注意：配对（standard/transposed）只改变四角与网格角的对应关系；
 * 网格坐标本身始终第一轴 0..8、第二轴 0..9，不存在坐标轴交换。
 */
#include "geometry_ref.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

/* ---------------- 小工具 ---------------- */

static GeomPt pt_sub(GeomPt a, GeomPt b) { GeomPt r = {a.x - b.x, a.y - b.y}; return r; }
static double pt_norm(GeomPt a) { return sqrt(a.x * a.x + a.y * a.y); }
static double pt_cross(GeomPt a, GeomPt b) { return a.x * b.y - a.y * b.x; }

typedef struct { double m[3][3]; } Mat3;

static void mat3_mul(const Mat3 *A, const Mat3 *B, Mat3 *C)
{
    int i, j, k;
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++) {
            double s = 0;
            for (k = 0; k < 3; k++) s += A->m[i][k] * B->m[k][j];
            C->m[i][j] = s;
        }
}

static int mat3_inv(const Mat3 *A, Mat3 *Ainv)
{
    double a = A->m[0][0], b = A->m[0][1], c = A->m[0][2];
    double d = A->m[1][0], e = A->m[1][1], f = A->m[1][2];
    double g = A->m[2][0], h = A->m[2][1], i = A->m[2][2];
    double A00 = e * i - f * h, A01 = -(d * i - f * g), A02 = d * h - e * g;
    double det = a * A00 + b * A01 + c * A02;
    if (fabs(det) < 1e-15) return GEOM_ERR_DEGENERATE;
    Ainv->m[0][0] = A00 / det;
    Ainv->m[0][1] = -(b * i - c * h) / det;
    Ainv->m[0][2] = (b * f - c * e) / det;
    Ainv->m[1][0] = A01 / det;
    Ainv->m[1][1] = (a * i - c * g) / det;
    Ainv->m[1][2] = -(a * f - c * d) / det;
    Ainv->m[2][0] = A02 / det;
    Ainv->m[2][1] = -(a * h - b * g) / det;
    Ainv->m[2][2] = (a * e - b * d) / det;
    return GEOM_OK;
}

/* 高斯消元 + 部分主元，解 8x8 线性方程组 A x = b（A 原地破坏）。 */
int geom_solve8(double A[8][8], const double b[8], double x[8])
{
    double aug[8][9];
    int i, j, k;
    for (i = 0; i < 8; i++) {
        for (j = 0; j < 8; j++) aug[i][j] = A[i][j];
        aug[i][8] = b[i];
    }
    for (k = 0; k < 8; k++) {
        int piv = k;
        double best = fabs(aug[k][k]);
        for (i = k + 1; i < 8; i++) {
            if (fabs(aug[i][k]) > best) { best = fabs(aug[i][k]); piv = i; }
        }
        if (best < 1e-12) return GEOM_ERR_DEGENERATE;
        if (piv != k) {
            for (j = 0; j < 9; j++) {
                double t = aug[k][j]; aug[k][j] = aug[piv][j]; aug[piv][j] = t;
            }
        }
        for (i = k + 1; i < 8; i++) {
            double f = aug[i][k] / aug[k][k];
            if (f == 0.0) continue;
            for (j = k; j < 9; j++) aug[i][j] -= f * aug[k][j];
        }
    }
    for (i = 7; i >= 0; i--) {
        double s = aug[i][8];
        for (j = i + 1; j < 8; j++) s -= aug[i][j] * x[j];
        x[i] = s / aug[i][i];
        if (!isfinite(x[i])) return GEOM_ERR_DEGENERATE;
    }
    return GEOM_OK;
}

/* ---------------- 四边形检查与配对 ---------------- */

int geom_check_quad(const GeomPt quad[4],
                    double *area, double *rel_cross_min, double *lh, double *lv)
{
    GeomPt e[4];
    double lens[4], crossv[4], rel[4];
    double twice_area = 0.0, a, rmin = 1e9, h1, v1;
    int i, pos = 0, neg = 0;

    for (i = 0; i < 4; i++) {
        GeomPt p = quad[i], q = quad[(i + 1) % 4];
        twice_area += pt_cross(p, q);
        e[i] = pt_sub(q, p);
        lens[i] = pt_norm(e[i]);
        if (lens[i] < 1e-9) return GEOM_ERR_DEGENERATE;
    }
    for (i = 0; i < 4; i++) {
        crossv[i] = pt_cross(e[i], e[(i + 1) % 4]);
        rel[i] = fabs(crossv[i]) / (lens[i] * lens[(i + 1) % 4]);
        if (rel[i] < rmin) rmin = rel[i];
        if (crossv[i] > 0) pos++; else if (crossv[i] < 0) neg++;
    }
    a = 0.5 * fabs(twice_area);
    if (a < GEOM_MIN_AREA_PX) return GEOM_ERR_DEGENERATE;
    if (pos != 4 && neg != 4) return GEOM_ERR_DEGENERATE; /* 非凸 */
    if (rmin < GEOM_REL_CROSS_MIN) return GEOM_ERR_DEGENERATE; /* 近退化 */

    h1 = (lens[0] + lens[2]) / 2.0; /* 上/下边 */
    v1 = (lens[1] + lens[3]) / 2.0; /* 左/右边 */
    if (area) *area = a;
    if (rel_cross_min) *rel_cross_min = rmin;
    if (lh) *lh = h1;
    if (lv) *lv = v1;
    return GEOM_OK;
}

int geom_choose_pairing(const GeomPt quad[4], int *transposed)
{
    double lh, lv;
    int rc = geom_check_quad(quad, NULL, NULL, &lh, &lv);
    if (rc != GEOM_OK) return rc;
    *transposed = (lv >= lh) ? 0 : 1;
    return GEOM_OK;
}

/* ---------------- 归一化 DLT ---------------- */

static void normalize_pts(const GeomPt *p, int n, Mat3 *T, GeomPt *out)
{
    double cx = 0, cy = 0, dmean = 0, s;
    int i;
    for (i = 0; i < n; i++) { cx += p[i].x; cy += p[i].y; }
    cx /= n; cy /= n;
    for (i = 0; i < n; i++) {
        GeomPt d = pt_sub(p[i], (GeomPt){cx, cy});
        dmean += pt_norm(d);
    }
    dmean /= n;
    s = sqrt(2.0) / (dmean > 1e-12 ? dmean : 1e-12);
    for (i = 0; i < n; i++) {
        out[i].x = (p[i].x - cx) * s;
        out[i].y = (p[i].y - cy) * s;
    }
    T->m[0][0] = s;      T->m[0][1] = 0;  T->m[0][2] = -s * cx;
    T->m[1][0] = 0;      T->m[1][1] = s;  T->m[1][2] = -s * cy;
    T->m[2][0] = 0;      T->m[2][1] = 0;  T->m[2][2] = 1.0;
}

static void grid_corners(int transposed, GeomPt gc[4])
{
    if (!transposed) {
        gc[0].x = 0; gc[0].y = 0;
        gc[1].x = GEOM_GRID_COLS; gc[1].y = 0;
        gc[2].x = GEOM_GRID_COLS; gc[2].y = GEOM_GRID_ROWS;
        gc[3].x = 0; gc[3].y = GEOM_GRID_ROWS;
    } else {
        gc[0].x = 0; gc[0].y = 0;
        gc[1].x = 0; gc[1].y = GEOM_GRID_ROWS;
        gc[2].x = GEOM_GRID_COLS; gc[2].y = GEOM_GRID_ROWS;
        gc[3].x = GEOM_GRID_COLS; gc[3].y = 0;
    }
}

static int finalize_h(const Mat3 *Hraw, GeomH *H)
{
    double w = Hraw->m[2][2];
    int i, j;
    if (fabs(w) < 1e-15) return GEOM_ERR_DEGENERATE;
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++) {
            double v = Hraw->m[i][j] / w;
            if (!isfinite(v)) return GEOM_ERR_DEGENERATE;
            H->m[i][j] = v;
        }
    return GEOM_OK;
}

int geom_h_from_corners(const GeomPt quad[4], int pairing, GeomH *H)
{
    GeomPt gc[4], s[4], d[4];
    int tr = pairing, rc, i;
    double A[8][8], b[8], x[8];
    Mat3 Ts, Td, Hn, Tdinv, Tmp;

    if (pairing != 0 && pairing != 1) {
        rc = geom_choose_pairing(quad, &tr);
        if (rc != GEOM_OK) return rc;
    }
    grid_corners(tr, gc);
    normalize_pts(gc, 4, &Ts, s);
    normalize_pts(quad, 4, &Td, d);
    for (i = 0; i < 4; i++) {
        double xx = s[i].x, yy = s[i].y, XX = d[i].x, YY = d[i].y;
        A[2 * i][0] = xx; A[2 * i][1] = yy; A[2 * i][2] = 1;
        A[2 * i][3] = 0; A[2 * i][4] = 0; A[2 * i][5] = 0;
        A[2 * i][6] = -XX * xx; A[2 * i][7] = -XX * yy;
        b[2 * i] = XX;
        A[2 * i + 1][0] = 0; A[2 * i + 1][1] = 0; A[2 * i + 1][2] = 0;
        A[2 * i + 1][3] = xx; A[2 * i + 1][4] = yy; A[2 * i + 1][5] = 1;
        A[2 * i + 1][6] = -YY * xx; A[2 * i + 1][7] = -YY * yy;
        b[2 * i + 1] = YY;
    }
    rc = geom_solve8(A, b, x);
    if (rc != GEOM_OK) return rc;
    Hn.m[0][0] = x[0]; Hn.m[0][1] = x[1]; Hn.m[0][2] = x[2];
    Hn.m[1][0] = x[3]; Hn.m[1][1] = x[4]; Hn.m[1][2] = x[5];
    Hn.m[2][0] = x[6]; Hn.m[2][1] = x[7]; Hn.m[2][2] = 1.0;
    rc = mat3_inv(&Td, &Tdinv);
    if (rc != GEOM_OK) return rc;
    mat3_mul(&Tdinv, &Hn, &Tmp);
    mat3_mul(&Tmp, &Ts, &Tdinv); /* Tdinv 此时 = H_raw */
    return finalize_h(&Tdinv, H);
}

int geom_fit_homography_ls(const GeomPt *src, const GeomPt *dst, int n, GeomH *H)
{
    GeomPt *s, *d;
    Mat3 Ts, Td, Hs, Tdinv, Tmp;
    double N[8][8] = {{0}}, rb[8] = {0}, x[8];
    int i, j, k, m, rc;

    if (n < 4) return GEOM_ERR_TOO_FEW;
    if (!src || !dst || !H) return GEOM_ERR_INVALID;
    s = (GeomPt *)malloc((size_t)n * sizeof(GeomPt));
    d = (GeomPt *)malloc((size_t)n * sizeof(GeomPt));
    if (!s || !d) { free(s); free(d); return GEOM_ERR_INVALID; }
    normalize_pts(src, n, &Ts, s);
    normalize_pts(dst, n, &Td, d);
    /* 正规方程：每点两行 a1/a2（h9=1 参数化），累加 A^T A 与 A^T b */
    for (i = 0; i < n; i++) {
        double xx = s[i].x, yy = s[i].y, XX = d[i].x, YY = d[i].y;
        double rows[2][8] = {
            {xx, yy, 1, 0, 0, 0, -XX * xx, -XX * yy},
            {0, 0, 0, xx, yy, 1, -YY * xx, -YY * yy},
        };
        double bb[2] = {XX, YY};
        for (m = 0; m < 2; m++) {
            for (j = 0; j < 8; j++) {
                for (k = 0; k < 8; k++) N[j][k] += rows[m][j] * rows[m][k];
                rb[j] += rows[m][j] * bb[m];
            }
        }
    }
    rc = geom_solve8(N, rb, x);
    if (rc != GEOM_OK) { free(s); free(d); return rc; }
    Hs.m[0][0] = x[0]; Hs.m[0][1] = x[1]; Hs.m[0][2] = x[2];
    Hs.m[1][0] = x[3]; Hs.m[1][1] = x[4]; Hs.m[1][2] = x[5];
    Hs.m[2][0] = x[6]; Hs.m[2][1] = x[7]; Hs.m[2][2] = 1.0;
    rc = mat3_inv(&Td, &Tdinv);
    if (rc != GEOM_OK) { free(s); free(d); return rc; }
    mat3_mul(&Tdinv, &Hs, &Tmp);
    mat3_mul(&Tmp, &Ts, &Hs);
    free(s); free(d);
    return finalize_h(&Hs, H);
}

int geom_apply_h(const GeomH *H, GeomPt p, GeomPt *out)
{
    double w = H->m[2][0] * p.x + H->m[2][1] * p.y + H->m[2][2];
    if (fabs(w) < 1e-15) return GEOM_ERR_DEGENERATE;
    out->x = (H->m[0][0] * p.x + H->m[0][1] * p.y + H->m[0][2]) / w;
    out->y = (H->m[1][0] * p.x + H->m[1][1] * p.y + H->m[1][2]) / w;
    return GEOM_OK;
}

int geom_invert_h(const GeomH *H, GeomH *Hinv)
{
    Mat3 a, b;
    int i, j, rc;
    for (i = 0; i < 3; i++) for (j = 0; j < 3; j++) a.m[i][j] = H->m[i][j];
    rc = mat3_inv(&a, &b);
    if (rc != GEOM_OK) return rc;
    return finalize_h(&b, Hinv);
}

int geom_grid_points(const GeomH *H, GeomPt points[GEOM_N_POINTS])
{
    int r, c, k = 0, rc;
    for (r = 0; r <= GEOM_GRID_ROWS; r++) {
        for (c = 0; c <= GEOM_GRID_COLS; c++) {
            GeomPt g = {(double)c, (double)r}, o;
            rc = geom_apply_h(H, g, &o);
            if (rc != GEOM_OK) return rc;
            points[k++] = o;
        }
    }
    return GEOM_OK;
}

void geom_snap(double u, double v, int *col, int *row, double *res)
{
    int cc = (int)floor(u + 0.5), rr = (int)floor(v + 0.5);
    double cu, cv;
    if (cc < 0) cc = 0;
    if (cc > GEOM_GRID_COLS) cc = GEOM_GRID_COLS;
    if (rr < 0) rr = 0;
    if (rr > GEOM_GRID_ROWS) rr = GEOM_GRID_ROWS;
    cu = u - cc; cv = v - rr;
    *col = cc; *row = rr;
    if (res) *res = sqrt(cu * cu + cv * cv);
}

int geom_grid_of(const GeomH *H, GeomPt p, double *u, double *v)
{
    GeomH Hinv;
    GeomPt o;
    int rc = geom_invert_h(H, &Hinv);
    if (rc != GEOM_OK) return rc;
    rc = geom_apply_h(&Hinv, p, &o);
    if (rc != GEOM_OK) return rc;
    *u = o.x; *v = o.y;
    return GEOM_OK;
}

/* ---------------- TLS 直线拟合（2x2 协方差闭式特征分解） ---------------- */

static void insertion_sort_d(double *a, int n)
{
    int i, j;
    for (i = 1; i < n; i++) {
        double key = a[i];
        j = i - 1;
        while (j >= 0 && a[j] > key) { a[j + 1] = a[j]; j--; }
        a[j + 1] = key;
    }
}

static double median_sorted_inplace(double *a, int n)
{
    insertion_sort_d(a, n);
    return (n % 2) ? a[n / 2] : 0.5 * (a[n / 2 - 1] + a[n / 2]);
}

static int fit_line_tls(const GeomPt *P, int *idx, int n,
                        GeomPt *center, GeomPt *direction, int rounds)
{
    double mx, my, sxx, syy, sxy;
    int i, iter;
    if (n < 2) return 0;
    for (iter = 0; iter < rounds; iter++) {
        double *r = NULL;
        int *keep = NULL;
        mx = my = sxx = syy = sxy = 0;
        for (i = 0; i < n; i++) { mx += P[idx[i]].x; my += P[idx[i]].y; }
        mx /= n; my /= n;
        for (i = 0; i < n; i++) {
            double dx = P[idx[i]].x - mx, dy = P[idx[i]].y - my;
            sxx += dx * dx; syy += dy * dy; sxy += dx * dy;
        }
        {
            double tr = sxx + syy, det = sxx * syy - sxy * sxy;
            double disc = tr * tr / 4.0 - det;
            double lam, nx, ny, nl;
            if (disc < 0) disc = 0;
            lam = tr / 2.0 + sqrt(disc);
            if (fabs(sxy) > 1e-12) { nx = lam - syy; ny = sxy; }
            else { nx = (sxx >= syy) ? 1.0 : 0.0; ny = (sxx >= syy) ? 0.0 : 1.0; }
            nl = sqrt(nx * nx + ny * ny);
            if (nl < 1e-12) return 0;
            direction->x = nx / nl; direction->y = ny / nl;
            center->x = mx; center->y = my;
        }
        if (iter + 1 == rounds) break;
        /* MAD 剔除（同 Python: med + 3*1.4826*mad + 1.0 绝对底） */
        r = (double *)malloc((size_t)n * sizeof(double));
        keep = (int *)malloc((size_t)n * sizeof(int));
        if (!r || !keep) { free(r); free(keep); return 0; }
        for (i = 0; i < n; i++) {
            double dx = P[idx[i]].x - mx, dy = P[idx[i]].y - my;
            r[i] = fabs(-direction->x * dy + direction->y * dx);
        }
        {
            double med, mad, thr, dummy;
            double *tmp = (double *)malloc((size_t)n * sizeof(double));
            int nkeep = 0;
            if (!tmp) { free(r); free(keep); return 0; }
            memcpy(tmp, r, (size_t)n * sizeof(double));
            dummy = median_sorted_inplace(tmp, n);
            (void)dummy;
            med = (n % 2) ? tmp[n / 2] : 0.5 * (tmp[n / 2 - 1] + tmp[n / 2]);
            for (i = 0; i < n; i++) tmp[i] = fabs(r[i] - med);
            mad = median_sorted_inplace(tmp, n);
            free(tmp);
            thr = med + 3.0 * 1.4826 * mad + 1.0;
            for (i = 0; i < n; i++) if (r[i] < thr) keep[nkeep++] = idx[i];
            if (nkeep < 2) { free(r); free(keep); return 0; }
            /* 先拷回 idx 再释放（避免 use-after-free） */
            for (i = 0; i < nkeep; i++) idx[i] = keep[i];
            free(r); free(keep);
            n = nkeep;
        }
    }
    return 1;
}

static int intersect_lines(GeomPt p1, GeomPt d1, GeomPt p2, GeomPt d2, GeomPt *out)
{
    /* 解 [d1, -d2] [t; s] = p2 - p1，取 t */
    double det = -(d1.x * d2.y - d1.y * d2.x); /* det[d1, -d2] */
    double rx = p2.x - p1.x, ry = p2.y - p1.y;
    double t;
    if (fabs(det) < 1e-9) return 0;
    t = (rx * (-d2.y) - (-d2.x) * ry) / det;
    out->x = p1.x + t * d1.x;
    out->y = p1.y + t * d1.y;
    return 1;
}

static void order_corners_idx(const GeomPt q[4], GeomPt out[4])
{
    double s[4], d[4];
    int ismin = 0, idmax = 0, ismax = 0, idmin = 0, i;
    for (i = 0; i < 4; i++) {
        s[i] = q[i].x + q[i].y;
        d[i] = q[i].x - q[i].y;
    }
    for (i = 1; i < 4; i++) {
        if (s[i] < s[ismin]) ismin = i;
        if (s[i] > s[ismax]) ismax = i;
        if (d[i] > d[idmax]) idmax = i;
        if (d[i] < d[idmin]) idmin = i;
    }
    out[0] = q[ismin]; out[1] = q[idmax]; out[2] = q[ismax]; out[3] = q[idmin];
}

static int in_bounds(const GeomPt q[4], const double *b)
{
    int i;
    for (i = 0; i < 4; i++) {
        if (q[i].x <= b[0] || q[i].x >= b[2] || q[i].y <= b[1] || q[i].y >= b[3])
            return 0;
    }
    return 1;
}

/* 边界线法：4 条边族（col=0 / col=8 / row=0 / row=9）TLS 直线相交得四角。
 * 注意：col/row 指格坐标第一轴(0..8)/第二轴(0..9)，与配对方式无关。
 * 失败返回 0（族点数 <2 或近平行）。quad_out 为规范序四角。 */
static int quad_from_lines(const GeomPt *C, const int *keep, int nkeep,
                           const int *gcol, const int *grow, GeomPt quad_out[4])
{
    GeomPt fam_c[4], fam_d[4];
    int i, k;
    int pairs[4][2] = {{2, 0}, {2, 1}, {3, 0}, {3, 1}}; /* T-L T-R B-L B-R */
    for (k = 0; k < 4; k++) {
        int *idx = (int *)malloc((size_t)(nkeep > 0 ? nkeep : 1) * sizeof(int));
        int cnt = 0;
        if (!idx) return 0;
        for (i = 0; i < nkeep; i++) {
            int take;
            if (k == 0) take = (gcol[keep[i]] == 0);
            else if (k == 1) take = (gcol[keep[i]] == GEOM_GRID_COLS);
            else if (k == 2) take = (grow[keep[i]] == 0);
            else take = (grow[keep[i]] == GEOM_GRID_ROWS);
            if (take) idx[cnt++] = keep[i];
        }
        if (cnt < 2 || !fit_line_tls(C, idx, cnt, &fam_c[k], &fam_d[k], 3)) {
            free(idx);
            return 0;
        }
        free(idx);
    }
    for (k = 0; k < 4; k++) {
        if (fabs(pt_cross(fam_d[pairs[k][0]], fam_d[pairs[k][1]])) < 0.25) return 0;
    }
    {
        GeomPt tl, tr, br, bl, tmp[4];
        if (!intersect_lines(fam_c[2], fam_d[2], fam_c[0], fam_d[0], &tl)) return 0;
        if (!intersect_lines(fam_c[2], fam_d[2], fam_c[1], fam_d[1], &tr)) return 0;
        if (!intersect_lines(fam_c[3], fam_d[3], fam_c[1], fam_d[1], &br)) return 0;
        if (!intersect_lines(fam_c[3], fam_d[3], fam_c[0], fam_d[0], &bl)) return 0;
        tmp[0] = tl; tmp[1] = tr; tmp[2] = br; tmp[3] = bl;
        order_corners_idx(tmp, quad_out);
    }
    return 1;
}

/* ---------------- ICP：备路线主过程 ---------------- */

typedef struct {
    GeomPt quad[4];
    int n_kept;        /* 终检内点数（res < FINAL_TOL） */
    double sel_p95;    /* 择优用：trim20 截尾集最大值（同 Python icp_fit_multi） */
    double out_p95;    /* 输出用：棋盘内 trim10 后 95 分位（同 Python core_stats） */
    double dseed;
} IcpResult;

/* 复刻 Python trim_res(res, frac, min_keep)：升序取前 keep 个。
 * 返回 keep 数量；keep_out 为保留长度。 */
static int trim_keep_count(int n, double frac, int min_keep)
{
    int k = (int)ceil(frac * (double)n);
    if (k < 2) k = 2;
    {
        int keep = n - k;
        if (keep < min_keep) keep = min_keep;
        if (keep > n) keep = n;
        return keep;
    }
}

static double percentile95_linear(const double *sorted, int n)
{
    double pos = 0.95 * (n - 1);
    int lo = (int)floor(pos);
    int hi = (lo + 1 < n) ? lo + 1 : lo;
    double frac = pos - lo;
    return sorted[lo] * (1.0 - frac) + sorted[hi] * frac;
}

/* 单候选 ICP。失败返回 0；成功填充 *out 并返回 1。 */
static int icp_one(const GeomPt *C, int n, const GeomPt *seed, const GeomPt q0[4],
                   const double *bounds, IcpResult *out)
{
    GeomPt quad[4], gc[4];
    GeomH Hg2i, Hinv, Hn;
    int it, i, tr, rc;
    double *res = NULL;

    memcpy(quad, q0, 4 * sizeof(GeomPt));
    res = (double *)malloc((size_t)n * sizeof(double));
    if (!res) return 0;

    for (it = 0; it < GEOM_ICP_ITERS; it++) {
        int keep_n = 0;
        int *gcol = (int *)malloc((size_t)n * sizeof(int));
        int *grow = (int *)malloc((size_t)n * sizeof(int));
        int *keep = (int *)malloc((size_t)n * sizeof(int));
        GeomPt *gs, *gd, quad_h[4], ordered_h[4], ordered_l[4];
        int have_line, tr_now;

        if (!gcol || !grow || !keep) {
            free(gcol); free(grow); free(keep); free(res);
            return 0;
        }
        rc = geom_choose_pairing(quad, &tr_now);
        if (rc != GEOM_OK) { free(gcol); free(grow); free(keep); free(res); return 0; }
        grid_corners(tr_now, gc);
        rc = geom_h_from_corners(quad, tr_now, &Hg2i);
        if (rc != GEOM_OK) { free(gcol); free(grow); free(keep); free(res); return 0; }
        rc = geom_invert_h(&Hg2i, &Hinv);
        if (rc != GEOM_OK) { free(gcol); free(grow); free(keep); free(res); return 0; }
        {
            double tol = (it == 0) ? GEOM_SNAP_TOL0 : GEOM_FINAL_TOL;
            for (i = 0; i < n; i++) {
                GeomPt uv = {0.0, 0.0};
                int cc, rr;
                geom_apply_h(&Hinv, C[i], &uv);
                geom_snap(uv.x, uv.y, &cc, &rr, &res[i]);
                gcol[i] = cc; grow[i] = rr;
                if (res[i] < tol) keep[keep_n++] = i;
            }
        }
        if (keep_n < GEOM_MIN_KEPT) {
            free(gcol); free(grow); free(keep); free(res);
            return 0;
        }
        gs = (GeomPt *)malloc((size_t)keep_n * sizeof(GeomPt));
        gd = (GeomPt *)malloc((size_t)keep_n * sizeof(GeomPt));
        if (!gs || !gd) {
            free(gcol); free(grow); free(keep); free(res); free(gs); free(gd);
            return 0;
        }
        for (i = 0; i < keep_n; i++) {
            int j = keep[i];
            gs[i].x = (double)gcol[j];
            gs[i].y = (double)grow[j];
            gd[i] = C[j];
        }
        rc = geom_fit_homography_ls(gs, gd, keep_n, &Hn);
        free(gs); free(gd);
        if (rc != GEOM_OK) {
            free(gcol); free(grow); free(keep); free(res);
            return 0;
        }
        for (i = 0; i < 4; i++) geom_apply_h(&Hn, gc[i], &quad_h[i]);
        order_corners_idx(quad_h, ordered_h);
        /* 同 Python：仅对单应法四角做越界否决（边界线法结果不再查） */
        if (bounds && !in_bounds(ordered_h, bounds)) {
            free(gcol); free(grow); free(keep); free(res);
            return 0;
        }
        have_line = quad_from_lines(C, keep, keep_n, gcol, grow, ordered_l);
        if (have_line) {
            double diff = 0;
            for (i = 0; i < 4; i++) {
                double dx = fabs(ordered_l[i].x - ordered_h[i].x);
                double dy = fabs(ordered_l[i].y - ordered_h[i].y);
                if (dx > diff) diff = dx;
                if (dy > diff) diff = dy;
            }
            memcpy(quad, (diff < 15.0) ? ordered_l : ordered_h, 4 * sizeof(GeomPt));
        } else {
            memcpy(quad, ordered_h, 4 * sizeof(GeomPt));
        }
        free(gcol); free(grow); free(keep);
    }

    /* 终检：终轮网格下内点数 + 两种 P95 */
    rc = geom_choose_pairing(quad, &tr);
    if (rc != GEOM_OK) { free(res); return 0; }
    grid_corners(tr, gc);
    rc = geom_h_from_corners(quad, tr, &Hg2i);
    if (rc != GEOM_OK) { free(res); return 0; }
    rc = geom_invert_h(&Hg2i, &Hinv);
    if (rc != GEOM_OK) { free(res); return 0; }
    {
        int kept = 0;
        for (i = 0; i < n; i++) {
            GeomPt uv = {0.0, 0.0};
            int cc, rr;
            geom_apply_h(&Hinv, C[i], &uv);
            geom_snap(uv.x, uv.y, &cc, &rr, &res[i]);
            if (res[i] < GEOM_FINAL_TOL) kept++;
        }
        /* 择优 P95：trim20(frac=0.2, min_keep=4) 截尾集的最大值 */
        {
            double *sorted = (double *)malloc((size_t)n * sizeof(double));
            int kc;
            if (!sorted) { free(res); return 0; }
            memcpy(sorted, res, (size_t)n * sizeof(double));
            insertion_sort_d(sorted, n);
            kc = trim_keep_count(n, 0.2, 4);
            out->sel_p95 = sorted[kc - 1];
            free(sorted);
        }
        /* 输出 P95：棋盘内（<=0.6 格）trim10(frac=0.1, min_keep=5) 后 95 分位 */
        {
            int nonb = 0;
            double *onb = (double *)malloc((size_t)n * sizeof(double));
            int ncore;
            if (!onb) { free(res); return 0; }
            for (i = 0; i < n; i++)
                if (res[i] <= GEOM_OFF_BOARD_RES) onb[nonb++] = res[i];
            if (nonb < 1) { free(onb); free(res); return 0; }
            insertion_sort_d(onb, nonb);
            ncore = (nonb >= 5) ? trim_keep_count(nonb, 0.10, 5) : nonb;
            out->out_p95 = percentile95_linear(onb, ncore);
            free(onb);
        }
        out->n_kept = kept;
        memcpy(out->quad, quad, 4 * sizeof(GeomPt));
        out->dseed = 0.0;
        if (seed) {
            for (i = 0; i < 4; i++) {
                double dx = fabs(quad[i].x - seed[i].x);
                double dy = fabs(quad[i].y - seed[i].y);
                if (dx > out->dseed) out->dseed = dx;
                if (dy > out->dseed) out->dseed = dy;
            }
        }
    }
    free(res);
    return 1;
}

/* 种子内点过滤（同 Python _seed_inliers：res<0.45，<6 个则全保留），
 * 用于包络初值的点集。返回新点数，写出 out 数组（容量 >= n）。 */
static int seed_inliers(const GeomPt *C, int n, const GeomPt seed[4], GeomPt *out)
{
    GeomH Hg2i, Hinv;
    int tr, rc, i, cnt = 0;
    GeomPt gc[4];
    rc = geom_choose_pairing(seed, &tr);
    if (rc != GEOM_OK) { memcpy(out, C, (size_t)n * sizeof(GeomPt)); return n; }
    grid_corners(tr, gc);
    rc = geom_h_from_corners(seed, tr, &Hg2i);
    if (rc != GEOM_OK) { memcpy(out, C, (size_t)n * sizeof(GeomPt)); return n; }
    rc = geom_invert_h(&Hg2i, &Hinv);
    if (rc != GEOM_OK) { memcpy(out, C, (size_t)n * sizeof(GeomPt)); return n; }
    for (i = 0; i < n; i++) {
        GeomPt uv = {0.0, 0.0};
        geom_apply_h(&Hinv, C[i], &uv);
        {
            int cc, rr;
            double r;
            geom_snap(uv.x, uv.y, &cc, &rr, &r);
            if (r < 0.45) out[cnt++] = C[i];
        }
    }
    if (cnt < 6) { memcpy(out, C, (size_t)n * sizeof(GeomPt)); return n; }
    return cnt;
}

int geom_piece_fit(const GeomPt *centers, int n, const GeomPt *seed,
                   const double *bounds,
                   GeomPt quad_out[4], GeomH *H_out,
                   int *n_kept, double *p95)
{
    GeomPt cands[10][4];
    int ncand = 0, i, c, tr, rc;
    IcpResult best, cur;
    int have_best = 0;
    GeomPt *env_pts = NULL;
    int n_env = 0;

    if (!centers || !quad_out || !H_out) return GEOM_ERR_INVALID;
    if (n < GEOM_MIN_KEPT) return GEOM_ERR_TOO_FEW;

    if (seed) {
        memcpy(cands[ncand], seed, 4 * sizeof(GeomPt));
        ncand++;
        env_pts = (GeomPt *)malloc((size_t)n * sizeof(GeomPt));
        if (!env_pts) return GEOM_ERR_INVALID;
        n_env = seed_inliers(centers, n, seed, env_pts);
    } else {
        env_pts = (GeomPt *)malloc((size_t)n * sizeof(GeomPt));
        if (!env_pts) return GEOM_ERR_INVALID;
        memcpy(env_pts, centers, (size_t)n * sizeof(GeomPt));
        n_env = n;
    }

    /* 包络 ± 0/1 格，9 变体（同 Python envelope_candidates；基于种子内点集） */
    {
        double x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18, cx, cy;
        int dx0i, dx1i, dy0i, dy1i;
        for (i = 0; i < n_env; i++) {
            if (env_pts[i].x < x0) x0 = env_pts[i].x;
            if (env_pts[i].x > x1) x1 = env_pts[i].x;
            if (env_pts[i].y < y0) y0 = env_pts[i].y;
            if (env_pts[i].y > y1) y1 = env_pts[i].y;
        }
        cx = (x1 - x0) / GEOM_GRID_COLS;
        cy = (y1 - y0) / GEOM_GRID_ROWS;
        for (dx0i = 0; dx0i < 2; dx0i++)
        for (dx1i = 0; dx1i < 2; dx1i++)
        for (dy0i = 0; dy0i < 2; dy0i++)
        for (dy1i = 0; dy1i < 2; dy1i++) {
            double ddx0, ddx1, ddy0, ddy1, pad;
            GeomPt tmp[4];
            if ((dx0i && dx1i) || (dy0i && dy1i)) continue;
            ddx0 = dx0i ? cx : 0; ddx1 = dx1i ? cx : 0;
            ddy0 = dy0i ? cy : 0; ddy1 = dy1i ? cy : 0;
            pad = (!dx0i && !dx1i && !dy0i && !dy1i) ? 12.0 : 2.0;
            tmp[0].x = x0 - ddx0 - pad; tmp[0].y = y0 - ddy0 - pad;
            tmp[1].x = x1 + ddx1 + pad; tmp[1].y = y0 - ddy0 - pad;
            tmp[2].x = x1 + ddx1 + pad; tmp[2].y = y1 + ddy1 + pad;
            tmp[3].x = x0 - ddx0 - pad; tmp[3].y = y1 + ddy1 + pad;
            memcpy(cands[ncand], tmp, 4 * sizeof(GeomPt));
            ncand++;
        }
    }
    free(env_pts);

    /* 择优：(n_kept, -round(sel_p95,2), -dseed)（同 Python icp_fit_multi；
     * round 到 2 位小数做平手裁决，C 用半舍入，极端平手情形与 Python 的
     * 银行家舍入可能有 0.01 格级差异——见 README 数值语义节） */
    for (c = 0; c < ncand; c++) {
        double r2_best, r2_cur;
        if (!icp_one(centers, n, seed, cands[c], bounds, &cur)) continue;
        if (!have_best) { best = cur; have_best = 1; continue; }
        r2_best = floor(best.sel_p95 * 100.0 + 0.5) / 100.0;
        r2_cur = floor(cur.sel_p95 * 100.0 + 0.5) / 100.0;
        if (cur.n_kept > best.n_kept) { best = cur; }
        else if (cur.n_kept == best.n_kept) {
            if (r2_cur < r2_best) { best = cur; }
            else if (r2_cur == r2_best && cur.dseed < best.dseed) { best = cur; }
        }
    }
    if (!have_best) return GEOM_ERR_NO_CONVERGE;

    memcpy(quad_out, best.quad, 4 * sizeof(GeomPt));
    rc = geom_choose_pairing(quad_out, &tr);
    if (rc != GEOM_OK) return rc;
    rc = geom_h_from_corners(quad_out, tr, H_out);
    if (rc != GEOM_OK) return rc;
    if (n_kept) *n_kept = best.n_kept;
    if (p95) *p95 = best.out_p95;
    return GEOM_OK;
}
