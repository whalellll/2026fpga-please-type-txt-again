#include "xq_grid.h"
#include <string.h>

static double magnitude(double x) { return x < 0 ? -x : x; }
static int solve(double a[8][9], double h[8])
{
    unsigned col, row, j, best;
    for (col = 0; col < 8; ++col) {
        best = col;
        for (row = col + 1; row < 8; ++row)
            if (magnitude(a[row][col]) > magnitude(a[best][col])) best = row;
        if (magnitude(a[best][col]) < 1e-9) return 0;
        for (j = col; j < 9; ++j) {
            double t = a[col][j]; a[col][j] = a[best][j]; a[best][j] = t;
        }
        { double scale = a[col][col]; for (j = col; j < 9; ++j) a[col][j] /= scale; }
        for (row = 0; row < 8; ++row) if (row != col) {
            double scale = a[row][col];
            for (j = col; j < 9; ++j) a[row][j] -= scale * a[col][j];
        }
    }
    for (col = 0; col < 8; ++col) h[col] = a[col][8];
    return 1;
}
static void equations(double u, double v, double x, double y, double rows[2][9])
{
    const double r[2][9] = {{u,v,1,0,0,0,-u*x,-v*x,x},
                           {0,0,0,u,v,1,-u*y,-v*y,y}};
    memcpy(rows, r, sizeof(r));
}
int xqg_project(const xqg_grid *g, double u, double v, double *x, double *y)
{
    double d;
    if (!g || !g->valid) return 0;
    d = g->h[6]*u + g->h[7]*v + 1;
    if (!(magnitude(d) > 1e-8)) return 0;
    *x = (g->h[0]*u + g->h[1]*v + g->h[2])/d;
    *y = (g->h[3]*u + g->h[4]*v + g->h[5])/d;
    return *x >= 0 && *x < XQV_WIDTH && *y >= 0 && *y < XQV_HEIGHT;
}
int xqg_corners(xqg_grid *g, const double c[4][2])
{
    static const double uv[4][2] = {{0,0},{8,0},{8,9},{0,9}};
    double a[8][9], area = 0;
    xqg_grid candidate;
    unsigned i;
    for (i = 0; i < 4; ++i) {
        unsigned j = (i+1)%4, k = (i+2)%4;
        double cross = (c[j][0]-c[i][0])*(c[k][1]-c[j][1]) -
                       (c[j][1]-c[i][1])*(c[k][0]-c[j][0]);
        /* Non-mirrored camera; reject crossing, collapsed or tiny quadrilaterals. */
        if (!(cross < -100)) return 0;
        area += c[i][0]*c[j][1] - c[i][1]*c[j][0];
        equations(uv[i][0],uv[i][1],c[i][0],c[i][1], &a[2*i]);
    }
    if (!(area < -20000) || !solve(a,candidate.h)) return 0;
    candidate.valid = 1;
    for (i=0; i<90; ++i) { double x,y; if (!xqg_project(&candidate,i%9,i/9,&x,&y)) return 0; }
    *g = candidate;
    return 1;
}
static int square_at(const xqg_grid *g, double x, double y)
{
    double a=g->h[0]-x*g->h[6], b=g->h[1]-x*g->h[7], c=x-g->h[2];
    double d=g->h[3]-y*g->h[6], e=g->h[4]-y*g->h[7], f=y-g->h[5];
    double det=a*e-b*d, u,v;
    int file,rank;
    if (!(magnitude(det)>1e-8)) return -1;
    u=(c*e-b*f)/det; v=(a*f-c*d)/det;
    if (!(u>=-0.25 && u<=8.25 && v>=-0.25 && v<=9.25)) return -1;
    file=(int)(u+0.5); rank=(int)(v+0.5);
    /* Freeze a conservative development residual, in cell units. */
    if ((u-file)*(u-file)+(v-rank)*(v-rank)>0.0625) return -1;
    return rank*9+file;
}
int xqg_map(const xqg_grid *g, const xqg_detection *d, unsigned count,
            uint32_t frame, xqv_result *out)
{
    xq_search_board_t b;
    uint16_t scores[90]={0}, confidence=1000;
    unsigned i;
    if (!g || !g->valid || count>32) return 0;
    memset(&b,0,sizeof(b));
    for (i=0; i<count; ++i) {
        int s=square_at(g,d[i].x,d[i].y);
        if (s<0 || d[i].class_id>=14 || d[i].confidence>1000 || b.squares[s]) return 0;
        b.squares[s]=(uint8_t)(d[i].class_id%7+1+(d[i].class_id>=7?SIDE_BLACK:0));
        scores[s]=d[i].confidence;
        if (confidence>d[i].confidence) confidence=d[i].confidence;
    }
    xqv_board_result(&b,frame,confidence,out);
    for (i=0; i<out->piece_count; ++i)
        out->pieces[i].confidence=scores[out->pieces[i].rank*9+out->pieces[i].file];
    return xqv_result_board(out,frame,&b);
}
static int refine(xqg_grid *g, const xqg_detection *d, unsigned n,
                   const xq_search_board_t *reference, uint32_t frame)
{
    double normal[8][9]={{0}};
    xqv_result mapped;
    xq_search_board_t b;
    xqg_grid fitted;
    unsigned i,j,k,r;
    if (!xqg_map(g,d,n,frame,&mapped) || !xqv_result_board(&mapped,frame,&b) ||
        memcmp(reference->squares,b.squares,90)) return 0;
    for (i=0; i<n; ++i) {
        double rows[2][9];
        int s=square_at(g,d[i].x,d[i].y);
        equations(s%9,s/9,d[i].x,d[i].y,rows);
        for (r=0; r<2; ++r) for (j=0; j<8; ++j) for (k=0; k<9; ++k)
            normal[j][k]+=rows[r][j]*rows[r][k];
    }
    if (!solve(normal,fitted.h)) return 0;
    fitted.valid=1;
    if (!xqg_map(&fitted,d,n,frame,&mapped) || !xqv_result_board(&mapped,frame,&b) ||
        memcmp(reference->squares,b.squares,90)) return 0;
    *g=fitted;
    return 1;
}
int xqg_fit(xqg_grid *g, const xqg_detection *d, unsigned n,
            const xq_search_board_t *reference, uint32_t frame)
{
    unsigned i,r[2],b[2],nr=0,nb=0,a,c;
    xqg_grid candidate=*g;
    if (candidate.valid && refine(&candidate,d,n,reference,frame)) { *g=candidate; return 1; }
    if (n!=32 || reference->squares[0]!=PIECE_R || reference->squares[8]!=PIECE_R ||
        reference->squares[81]!=(PIECE_R|SIDE_BLACK) || reference->squares[89]!=(PIECE_R|SIDE_BLACK)) return 0;
    for (i=0; i<n; ++i) {
        if (d[i].class_id==4) { if (nr==2) return 0; r[nr++]=i; }
        if (d[i].class_id==11) { if (nb==2) return 0; b[nb++]=i; }
    }
    if (nr!=2 || nb!=2) return 0;
    for (a=0; a<2; ++a) for (c=0; c<2; ++c) {
        unsigned order[4]={r[a],r[1-a],b[c],b[1-c]};
        double corners[4][2];
        for (i=0; i<4; ++i) { corners[i][0]=d[order[i]].x; corners[i][1]=d[order[i]].y; }
        if (xqg_corners(&candidate,corners) && refine(&candidate,d,n,reference,frame)) {
            *g=candidate; return 1;
        }
    }
    return 0;
}
void xqg_stub_geometry(const xqv_result *r, xqg_detection *d)
{
    unsigned i;
    for (i=0; i<r->piece_count && i<32; ++i) {
        d[i].x=320+64*r->pieces[i].file; d[i].y=640-64*r->pieces[i].rank;
        d[i].x0=(uint16_t)(d[i].x-22); d[i].y0=(uint16_t)(d[i].y-22);
        d[i].x1=(uint16_t)(d[i].x+22); d[i].y1=(uint16_t)(d[i].y+22);
        d[i].class_id=r->pieces[i].class_id; d[i].confidence=r->pieces[i].confidence;
    }
}
