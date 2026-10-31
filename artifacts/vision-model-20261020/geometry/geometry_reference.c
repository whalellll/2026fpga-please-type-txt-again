/* Host C reference and integer Q16.16 point projection. No hardware ABI assumed.
 * Matrix solving here uses double; this is NOT a claim of an all-integer device solver.
 * Input rows: case_id, TLx TLy TRx TRy BRx BRy BLx BLy, black_edge(0top1right2bottom3left).
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <math.h>
#include <limits.h>

static int solve_h(const double q[8],int edge,double h[9]) {
 double a[8][9]={{0}},cx=0,cy=0,scale=0;int k,i,j;
 const double g[4][2]={{0,0},{8,0},{8,9},{0,9}};
 if(edge<0||edge>3)return -1;
 double area2=0;
 for(k=0;k<4;k++){
  int p=(k+1)%4,z=(k+2)%4;
  double ex=q[2*p]-q[2*k],ey=q[2*p+1]-q[2*k+1];
  double fx=q[2*z]-q[2*p],fy=q[2*z+1]-q[2*p+1];
  if(!isfinite(q[2*k])||!isfinite(q[2*k+1])||q[2*k]<0||q[2*k]>1279||q[2*k+1]<0||q[2*k+1]>719)return -4;
  if(ex*fy-ey*fx<=1e-5||hypot(ex,ey)<10)return -5;
  area2+=q[2*k]*q[2*p+1]-q[2*k+1]*q[2*p];
 }
 if(area2/2<.01*1280*720)return -6;
 for(k=0;k<4;k++){cx+=q[2*k]/4;cy+=q[2*k+1]/4;}
 for(k=0;k<4;k++)for(i=0;i<4;i++){
  double dx=fabs(q[2*k]-q[2*i]),dy=fabs(q[2*k+1]-q[2*i+1]);
  if(dx>scale)scale=dx;
  if(dy>scale)scale=dy;
 }
 if(!(scale>1)||!isfinite(scale))return -2;
 for(k=0;k<4;k++){
  int p=(k+edge)%4;double x=g[k][0],y=g[k][1],u=(q[2*p]-cx)/scale,v=(q[2*p+1]-cy)/scale;
  a[2*k][0]=x;a[2*k][1]=y;a[2*k][2]=1;a[2*k][6]=-u*x;a[2*k][7]=-u*y;a[2*k][8]=u;
  a[2*k+1][3]=x;a[2*k+1][4]=y;a[2*k+1][5]=1;a[2*k+1][6]=-v*x;a[2*k+1][7]=-v*y;a[2*k+1][8]=v;
 }
 for(k=0;k<8;k++){
  int pivot=k;for(i=k+1;i<8;i++)if(fabs(a[i][k])>fabs(a[pivot][k]))pivot=i;
  if(fabs(a[pivot][k])<1e-12)return -3;
  for(j=k;j<=8;j++){double temp=a[k][j];a[k][j]=a[pivot][j];a[pivot][j]=temp;}
  double d=a[k][k];for(j=k;j<=8;j++)a[k][j]/=d;
  for(i=0;i<8;i++)if(i!=k){double f=a[i][k];for(j=k;j<=8;j++)a[i][j]-=f*a[k][j];}
 }
 double z[9];for(k=0;k<8;k++)z[k]=a[k][8];z[8]=1;
 h[0]=scale*z[0]+cx*z[6];h[1]=scale*z[1]+cx*z[7];h[2]=scale*z[2]+cx;
 h[3]=scale*z[3]+cy*z[6];h[4]=scale*z[4]+cy*z[7];h[5]=scale*z[5]+cy;
 h[6]=z[6];h[7]=z[7];h[8]=1;
 return 0;
}
static int64_t rounded_div(int64_t n,int64_t d){
 if(d<0){d=-d;n=-n;}
 return n>=0?(n+d/2)/d:-((-n+d/2)/d);
}
static int project_q16(const int32_t h[9],int f,int r,int64_t *x,int64_t *y){
 if(f<0||f>8||r<0||r>9)return -1;
 int64_t a=(int64_t)h[0]*f+(int64_t)h[1]*r+h[2];
 int64_t b=(int64_t)h[3]*f+(int64_t)h[4]*r+h[5];
 int64_t d=(int64_t)h[6]*f+(int64_t)h[7]*r+h[8];
 if(d==0)return -2;
 /* int32 coefficients and bounded grid indices keep multiplication in int64. */
 *x=rounded_div(a*INT64_C(65536),d);*y=rounded_div(b*INT64_C(65536),d);return 0;
}
int main(void){
 int id,edge,ncases=0;double q[8];
 while(scanf("%d %lf %lf %lf %lf %lf %lf %lf %lf %d",&id,&q[0],&q[1],&q[2],&q[3],&q[4],&q[5],&q[6],&q[7],&edge)==10){
  double h[9];int32_t fixed[9];int rc=solve_h(q,edge,h);
  if(rc){printf("ERROR %d %d\n",id,rc);continue;}
  for(int k=0;k<9;k++){double v=h[k]*65536;if(!isfinite(v)||v<INT32_MIN||v>INT32_MAX)return 2;fixed[k]=(int32_t)llround(v);}
  for(int r=0;r<10;r++)for(int f=0;f<9;f++){
   double d=h[6]*f+h[7]*r+h[8];if(fabs(d)<1e-9)return 3;
   double x=(h[0]*f+h[1]*r+h[2])/d,y=(h[3]*f+h[4]*r+h[5])/d;int64_t ix,iy;
   if(project_q16(fixed,f,r,&ix,&iy))return 4;
   printf("%d %d %d %.12f %.12f %.12f %.12f\n",id,f,r,x,y,ix/65536.0,iy/65536.0);
  }ncases++;
 }
 return ncases?0:5;
}
