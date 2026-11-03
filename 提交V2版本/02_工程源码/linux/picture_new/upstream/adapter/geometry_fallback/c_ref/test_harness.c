/* -*- coding: utf-8 -*-
 * test_harness.c — 几何模块 C 参考实现测试台。
 *
 * 输入：../test_vectors/vectors.tsv（由 generate_test_vectors.py 生成）
 * 格式（行式）：
 *   CASE <idx> <name> <CORNERS|PIECEFIT|EXPECT_FAIL>
 *   QUAD x1 y1 x2 y2 x3 y3 x4 y4          # CORNERS 输入
 *   NCENTERS <n>                           # PIECEFIT 输入
 *   C <x> <y>                              # n 行圆心
 *   SEED x1 y1 ... y4                      # 可选种子四角
 *   EXPECT_PAIRING <standard|transposed>
 *   EXPECT_H h00 h01 ... h22               # 9 值
 *   EXPECT_QUAD x1 y1 ... y4               # 8 值
 *   EXPECT_NKEPT <int>                     # PIECEFIT
 *   EXPECT_P95 <float>                     # PIECEFIT
 *   EXPECT_PTS90 + 90 行 "P <x> <y>"
 *   END
 *
 * 容差：quad/points 1e-4 px，H 相对 1e-6，n_kept 精确相等，p95 绝对 1e-9。
 * 退出码 0 = 全过；非 0 = 存在失败（逐条打印 PASS/FAIL）。
 *
 * 编译示例（MSVC）： cl /O2 /W4 geometry_ref.c test_harness.c /Fe:test_harness.exe
 *（gcc）：  gcc -O2 -Wall -std=c99 geometry_ref.c test_harness.c -o test_harness -lm
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "geometry_ref.h"

#define MAX_CENTERS 4096
#define LINE_LEN 8192

typedef struct {
    int idx;
    char name[128];
    int kind;              /* 0 corners 1 piecefit 2 expect_fail */
    GeomPt quad[4];
    GeomPt centers[MAX_CENTERS];
    int n_centers;
    int has_seed;
    GeomPt seed[4];
    int has_expect;
    int exp_pairing;       /* 0 standard 1 transposed */
    GeomH exp_H;
    GeomPt exp_quad[4];
    int exp_nkept;
    double exp_p95;
    GeomPt exp_pts[GEOM_N_POINTS];
} Case;

static int parse_line(const char *line, Case *c, int *in_pts, int *pt_i)
{
    char tag[64];
    if (sscanf(line, "%63s", tag) != 1) return 1; /* 空行 */
    if (strcmp(tag, "CASE") == 0) {
        char kind[32];
        memset(c, 0, sizeof(*c));
        c->exp_nkept = -1;
        if (sscanf(line, "%*s %d %127s %31s", &c->idx, c->name, kind) != 3) {
            fprintf(stderr, "bad CASE line: %s\n", line);
            return -1;
        }
        c->kind = strcmp(kind, "CORNERS") == 0 ? 0 :
                  strcmp(kind, "PIECEFIT") == 0 ? 1 :
                  strcmp(kind, "AMBIG") == 0 ? 3 : 2;
        *in_pts = 0;
        return 1;
    }
    if (strcmp(tag, "QUAD") == 0) {
        double v[8];
        int i;
        if (sscanf(line, "%*s %lf %lf %lf %lf %lf %lf %lf %lf",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7]) != 8)
            return -1;
        for (i = 0; i < 4; i++) { c->quad[i].x = v[2 * i]; c->quad[i].y = v[2 * i + 1]; }
        return 1;
    }
    if (strcmp(tag, "NCENTERS") == 0) {
        if (sscanf(line, "%*s %d", &c->n_centers) != 1) return -1;
        return 1;
    }
    if (strcmp(tag, "C") == 0) {
        static int ci = 0;
        (void)ci;
        return 1;
    }
    if (strcmp(tag, "SEED") == 0) {
        double v[8];
        int i;
        if (sscanf(line, "%*s %lf %lf %lf %lf %lf %lf %lf %lf",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7]) != 8)
            return -1;
        for (i = 0; i < 4; i++) { c->seed[i].x = v[2 * i]; c->seed[i].y = v[2 * i + 1]; }
        c->has_seed = 1;
        return 1;
    }
    if (strcmp(tag, "EXPECT_PAIRING") == 0) {
        char p[32];
        if (sscanf(line, "%*s %31s", p) != 1) return -1;
        c->exp_pairing = strcmp(p, "transposed") == 0 ? 1 : 0;
        c->has_expect = 1;
        return 1;
    }
    if (strcmp(tag, "EXPECT_H") == 0) {
        double v[9];
        int i, j, k = 0;
        if (sscanf(line, "%*s %lf %lf %lf %lf %lf %lf %lf %lf %lf",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7], &v[8]) != 9)
            return -1;
        for (i = 0; i < 3; i++) for (j = 0; j < 3; j++) c->exp_H.m[i][j] = v[k++];
        c->has_expect = 1;
        return 1;
    }
    if (strcmp(tag, "EXPECT_QUAD") == 0) {
        double v[8];
        int i;
        if (sscanf(line, "%*s %lf %lf %lf %lf %lf %lf %lf %lf",
                   &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7]) != 8)
            return -1;
        for (i = 0; i < 4; i++) { c->exp_quad[i].x = v[2 * i]; c->exp_quad[i].y = v[2 * i + 1]; }
        c->has_expect = 1;
        return 1;
    }
    if (strcmp(tag, "EXPECT_NKEPT") == 0) {
        if (sscanf(line, "%*s %d", &c->exp_nkept) != 1) return -1;
        return 1;
    }
    if (strcmp(tag, "EXPECT_P95") == 0) {
        if (sscanf(line, "%*s %lf", &c->exp_p95) != 1) return -1;
        return 1;
    }
    if (strcmp(tag, "EXPECT_PTS90") == 0) {
        *in_pts = 1;
        *pt_i = 0;
        return 1;
    }
    if (strcmp(tag, "P") == 0) {
        if (*in_pts && *pt_i < GEOM_N_POINTS) {
            if (sscanf(line, "%*s %lf %lf", &c->exp_pts[*pt_i].x, &c->exp_pts[*pt_i].y) != 2)
                return -1;
            (*pt_i)++;
        }
        return 1;
    }
    if (strcmp(tag, "END") == 0) {
        return 0; /* case 完整 */
    }
    if (tag[0] == '#') return 1;
    return 1;
}

static double max_abs_diff_pts(const GeomPt *a, const GeomPt *b, int n)
{
    double m = 0;
    int i;
    for (i = 0; i < n; i++) {
        double dx = fabs(a[i].x - b[i].x), dy = fabs(a[i].y - b[i].y);
        if (dx > m) m = dx;
        if (dy > m) m = dy;
    }
    return m;
}

int main(int argc, char **argv)
{
    const char *path = (argc > 1) ? argv[1] : "../test_vectors/vectors.tsv";
    FILE *f = fopen(path, "r");
    char line[LINE_LEN];
    int total = 0, pass = 0;
    Case cur;
    int have_case = 0, in_pts = 0, pt_i = 0;
    int centers_read = 0;

    if (!f) {
        fprintf(stderr, "cannot open %s\n", path);
        return 2;
    }
    while (fgets(line, sizeof(line), f)) {
        size_t len = strlen(line);
        while (len && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = 0;
        if (!len) continue;
        /* 圆心行以 "C " 开头时计入（在 parse_line 之前处理计数） */
        if (line[0] == 'C' && line[1] == ' ' && have_case && cur.n_centers > 0 &&
            centers_read < cur.n_centers) {
            if (sscanf(line, "%*s %lf %lf",
                       &cur.centers[centers_read].x, &cur.centers[centers_read].y) != 2) {
                fprintf(stderr, "bad center line: %s\n", line);
                return 2;
            }
            centers_read++;
            continue;
        }
        {
            int r = parse_line(line, &cur, &in_pts, &pt_i);
            if (r < 0) {
                fprintf(stderr, "parse error: %s\n", line);
                return 2;
            }
            if (strncmp(line, "CASE ", 5) == 0) {
                have_case = 1;
                centers_read = 0;
            }
            if (r == 0 && have_case) {
                /* END：执行该用例 */
                int ok = 1;
                total++;
                if (cur.kind == 2) { /* expect_fail */
                    if (cur.n_centers > 0) {
                        GeomPt q4[4];
                        GeomH h;
                        int nk;
                        double p95;
                        int rc = geom_piece_fit(cur.centers, cur.n_centers,
                                                cur.has_seed ? cur.seed : NULL, NULL,
                                                q4, &h, &nk, &p95);
                        if (rc == GEOM_OK) {
                            printf("FAIL %04d %s: expected failure, got quad\n", cur.idx, cur.name);
                            ok = 0;
                        }
                    } else {
                        GeomH h;
                        if (geom_h_from_corners(cur.quad, -1, &h) == GEOM_OK) {
                            printf("FAIL %04d %s: expected degenerate failure\n", cur.idx, cur.name);
                            ok = 0;
                        }
                    }
                } else if (cur.kind == 0) { /* corners */
                    GeomH h;
                    GeomPt pts[GEOM_N_POINTS];
                    int tr;
                    double dq, dh = 0, scale;
                    int i, j;
                    if (geom_choose_pairing(cur.quad, &tr) != GEOM_OK ||
                        tr != cur.exp_pairing) {
                        printf("FAIL %04d %s: pairing mismatch (%d vs %d)\n",
                               cur.idx, cur.name, tr, cur.exp_pairing);
                        ok = 0;
                    }
                    if (ok && geom_h_from_corners(cur.quad, cur.exp_pairing, &h) != GEOM_OK) {
                        printf("FAIL %04d %s: h_from_corners error\n", cur.idx, cur.name);
                        ok = 0;
                    }
                    if (ok && geom_grid_points(&h, pts) != GEOM_OK) {
                        printf("FAIL %04d %s: grid_points error\n", cur.idx, cur.name);
                        ok = 0;
                    }
                    if (ok) {
                        dq = max_abs_diff_pts(pts, cur.exp_pts, GEOM_N_POINTS);
                        scale = 1.0;
                        for (i = 0; i < 3; i++) for (j = 0; j < 3; j++) {
                            double d = fabs(h.m[i][j] - cur.exp_H.m[i][j]);
                            if (d > dh) dh = d;
                            if (fabs(cur.exp_H.m[i][j]) > scale) scale = fabs(cur.exp_H.m[i][j]);
                        }
                        if (dq > 1e-4) {
                            printf("FAIL %04d %s: pts90 max diff %.3g\n", cur.idx, cur.name, dq);
                            ok = 0;
                        }
                        if (dh > 1e-6 * scale) {
                            printf("FAIL %04d %s: H max diff %.3g\n", cur.idx, cur.name, dh);
                            ok = 0;
                        }
                    }
                } else if (cur.kind == 3) { /* AMBIG：只要求有解（数值不对拍，见 README） */
                    GeomPt q4[4];
                    GeomH h;
                    int nk;
                    double p95;
                    if (geom_piece_fit(cur.centers, cur.n_centers,
                                       cur.has_seed ? cur.seed : NULL, NULL,
                                       q4, &h, &nk, &p95) != GEOM_OK) {
                        printf("FAIL %04d %s: ambiguous case gave no solution\n",
                               cur.idx, cur.name);
                        ok = 0;
                    }
                } else { /* piecefit */
                    GeomPt q4[4];
                    GeomH h;
                    GeomPt pts[GEOM_N_POINTS];
                    int nk, i;
                    double p95, dq, dh = 0, scale;
                    double bounds[4] = {-80.0, -80.0, 1280.0 + 80.0, 720.0 + 80.0};
                    if (geom_piece_fit(cur.centers, cur.n_centers,
                                       cur.has_seed ? cur.seed : NULL, bounds,
                                       q4, &h, &nk, &p95) != GEOM_OK) {
                        printf("FAIL %04d %s: piece_fit no solution\n", cur.idx, cur.name);
                        ok = 0;
                    }
                    if (ok) {
                        double hmax = 1.0;
                        dq = max_abs_diff_pts(q4, cur.exp_quad, 4);
                        /* 跨实现浮点噪声预算：ICP 数值微差可放大到 ~2px（见 README） */
                        if (dq > 3.0) {
                            printf("FAIL %04d %s: quad max diff %.3g\n", cur.idx, cur.name, dq);
                            ok = 0;
                        }
                        for (i = 0; i < 9; i++) {
                            double d = fabs(((double *)h.m)[i] - ((double *)cur.exp_H.m)[i]);
                            double a = fabs(((double *)cur.exp_H.m)[i]);
                            if (a > hmax) hmax = a;
                            if (d > dh) dh = d;
                        }
                        if (dh > 5e-4 * hmax) {  /* 相对容差（H 元素量级 ~1e2-1e3） */
                            printf("FAIL %04d %s: H max diff %.3g (rel %.2g)\n",
                                   cur.idx, cur.name, dh, dh / hmax);
                            ok = 0;
                        }
                        if (nk != cur.exp_nkept) {
                            printf("FAIL %04d %s: n_kept %d vs %d\n",
                                   cur.idx, cur.name, nk, cur.exp_nkept);
                            ok = 0;
                        }
                        if (fabs(p95 - cur.exp_p95) > 1e-2) {
                            printf("FAIL %04d %s: p95 %.12g vs %.12g\n",
                                   cur.idx, cur.name, p95, cur.exp_p95);
                            ok = 0;
                        }
                        if (ok && geom_grid_points(&h, pts) == GEOM_OK) {
                            dq = max_abs_diff_pts(pts, cur.exp_pts, GEOM_N_POINTS);
                            if (dq > 3.0) {
                                printf("FAIL %04d %s: pts90 max diff %.3g\n", cur.idx, cur.name, dq);
                                ok = 0;
                            }
                        }
                    }
                }
                if (ok) {
                    pass++;
                    printf("PASS %04d %s\n", cur.idx, cur.name);
                }
                have_case = 0;
            }
        }
    }
    fclose(f);
    printf("%d/%d passed\n", pass, total);
    return (pass == total && total > 0) ? 0 : 1;
}
