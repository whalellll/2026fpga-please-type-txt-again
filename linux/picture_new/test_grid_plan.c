/* Internal differential fixtures: compile separately with plan flag 0 and 1.
 * The runner compares every retained lattice field, best score, proposal and
 * cancellation count, including repeated lattices and strict-score ties. */
#include "board_grid_recovery.c"
#include <assert.h>
#include <stdio.h>
static uint32_t random_state=UINT32_C(0x82a93147);
static uint32_t next(void)
{random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static void put(FILE *f,const void *p,size_t n){assert(fwrite(p,1,n,f)==n);}
static void put_lattice(FILE *f,const lattice *p)
{
    put(f,&p->score,8);put(f,&p->step,8);put(f,&p->left_shift,8);put(f,&p->right_shift,8);
    put(f,&p->support,4);put(f,&p->matched,4);put(f,&p->first,4);put(f,&p->last,4);
}
static unsigned calls,stop_at;
static int cancel_case(void *p){(void)p;return ++calls==stop_at;}
static void setup(state *s,unsigned mode)
{
    memset(s,0,sizeof(*s));
    const double q[4][2]={{20,20},{220,20},{220,155},{20,155}};memcpy(s->q,q,sizeof(q));
    for(unsigned a=0;a<2;a++){
        family *f=s->families+a;f->count=12+(int)(next()%29);f->nx=a?0:1;f->ny=a?1:0;
        double d=15;
        for(int i=0;i<f->count;i++){
            line *l=f->lines+i;d+=4+(next()%57)*.125;
            l->d=d;l->rho=d;l->nx=f->nx;l->ny=f->ny;l->fit_rho=d;
            l->log_votes=(next()%64)*.125;l->votes=100+next()%128;
        }
        if(mode){
            for(unsigned i=0;i<KEEP;i++){
                lattice l={0};l.first=(int)(next()%5);l.last=l.first+6+(int)(next()%2);
                l.step=(f->lines[l.last].d-f->lines[l.first].d)/8.;
                l.score=(next()%4)*100.;l.support=i%3?15u:7u;l.matched=8;
                l.left_shift=i%2?-l.step:0.;l.right_shift=i%3?0.:l.step;
                keep_lattice(f,&l);
            }
        }
    }
}
int main(int argc,char **argv)
{
    assert(argc==2 && sizeof(double)==8 && sizeof(unsigned)==4 && sizeof(int)==4);
    FILE *f=fopen(argv[1],"wbx");state *s=calloc(1,sizeof(*s));assert(f && s);
    for(unsigned c=0;c<96;c++){
        setup(s,c%2);
        if(!(c%2))for(unsigned a=0;a<2;a++){
            assert(find_lattices(s,s->families+a,c%4?9:10));
        }
        for(unsigned a=0;a<2;a++)for(unsigned ex=0;ex<4;ex++){
            unsigned count=s->families[a].counts[ex];put(f,&count,4);
            for(unsigned i=0;i<count;i++)put_lattice(f,&s->families[a].best[ex][i]);
        }
        double score=-INFINITY,proposal[4][2]={{0}};
        calls=0;stop_at=c%9?0:3;s->cancelled=cancel_case;
        int okay=combine(s,&score,proposal);put(f,&okay,4);put(f,&calls,4);
        put(f,&score,8);put(f,proposal,sizeof(proposal));
    }
#if XQ_GRID_PLAN_FAST
    lattice a={0},b={0};assert(same_lattice(&a,&b));b.step=-0.;assert(!same_lattice(&a,&b));
    b=a;b.matched=1;assert(!same_lattice(&a,&b));b=a;b.support=1;assert(!same_lattice(&a,&b));
    b=a;b.last=1;assert(!same_lattice(&a,&b));
#endif
    assert(!fclose(f));free(s);puts("GRID_PLAN_96_INTERNAL_FIELD_AND_ORDER_CASES_PASS");return 0;
}
