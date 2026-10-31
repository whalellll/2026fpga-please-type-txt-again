#ifndef XQ_DETECTOR_LAZY_DECODE_H
#define XQ_DETECTOR_LAZY_DECODE_H

/* Included after the frozen proposal/sigmoid/nms definitions. Scores, bbox
 * expressions, strict thresholds and proposal order are unchanged. Only bbox
 * work for anchors that cannot contribute a class is omitted. Floating status
 * flags and errno are not observed by the worker. NaN bbox/NMS behavior for
 * retained proposals is inherited without algebraic rearrangement. */
#ifndef XQDECODE_NMS
#define XQDECODE_NMS nms
#endif
#ifndef XQDECODE_NOTE_BOX
#define XQDECODE_NOTE_BOX() ((void)0)
#endif
#ifndef XQDECODE_NOTE_OBJ
#define XQDECODE_NOTE_OBJ() ((void)0)
#endif
static int xqdecode_detector_boxes(xqn_model *m,xqr_box out[300],unsigned *count)
{
    proposal *p=malloc(352800*sizeof(*p));unsigned n=0,order=0;
    if(!p)return 0;
    for(unsigned head=0;head<3;head++) {
        unsigned d[4];const float *x=xqn_output(m,head,d);
        if(!x || d[0]!=1 || d[1]!=57 || d[2]!=d[3] || d[2]!=(XQ_NATIVE_DETECTOR_SIDE/8u)/(1u<<head)){free(p);return 0;}
        unsigned side=d[2],area=side*side;
        for(unsigned anchor=0;anchor<3;anchor++)for(unsigned y=0;y<side;y++)for(unsigned xx=0;xx<side;xx++,order+=14) {
            const float *q=x+(anchor*19*area+y*side+xx);
            float obj=sigmoid(q[4*area]);if(obj<=.001f)continue;
            XQDECODE_NOTE_OBJ();
            float scores[14];int any=0;
            for(unsigned cls=0;cls<14;cls++) {
                scores[cls]=obj*sigmoid(q[(cls+5)*area]);
                if(scores[cls]>.001f)any=1;
            }
            if(!any)continue;
            XQDECODE_NOTE_BOX();
            float cx=(sigmoid(q[0])*2.f+(xx-.5f))*native_strides[head];
            float cy=(sigmoid(q[area])*2.f+(y-.5f))*native_strides[head];
            float w=sigmoid(q[2*area])*2.f,h=sigmoid(q[3*area])*2.f;
            w=w*w*native_anchors[head][anchor][0];h=h*h*native_anchors[head][anchor][1];
            for(unsigned cls=0;cls<14;cls++) {
                float score=scores[cls];
                if(score>.001f) {if(n>=352800){free(p);return 0;}
                    p[n++]=(proposal){{cx-w/2.f,cy-h/2.f,cx+w/2.f,cy+h/2.f,score,cls},order+cls};}
            }
        }
    }
    *count=XQDECODE_NMS(p,n,out);free(p);return 1;
}
#endif
