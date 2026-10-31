#define _POSIX_C_SOURCE 200809L
#include "coach_protocol.h"
#include "crc32_fast.h"
#include <errno.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int identity_valid(const xqcoach_identity *id)
{
    return id && id->token && memchr(id->backend,0,sizeof(id->backend)) && !strcmp(id->backend,XQCOACH_BACKEND);
}
static int identity_equal(const xqcoach_identity *a,const xqcoach_identity *b)
{return identity_valid(a) && identity_valid(b) && a->token==b->token && a->frame==b->frame && a->crc==b->crc && !strcmp(a->backend,b->backend);}
int xqcoach_identity_init(xqcoach_identity *id,uint64_t token,uint32_t frame,uint32_t raw_crc)
{
    xqcoach_identity candidate={0};if(!id || !token)return 0;
    candidate.token=token;candidate.frame=frame;candidate.crc=raw_crc;
    memcpy(candidate.backend,XQCOACH_BACKEND,sizeof(XQCOACH_BACKEND));*id=candidate;return 1;
}
static char *word(char **cursor)
{
    char *p=*cursor,*begin;
    while(*p==' ' || *p=='\t' || *p=='\r' || *p=='\n')p++;
    if(!*p){*cursor=p;return NULL;}
    begin=p;while(*p && *p!=' ' && *p!='\t' && *p!='\r' && *p!='\n')p++;
    if(*p)*p++=0;
    *cursor=p;return begin;
}
static int number(char *text,uint64_t limit,uint64_t *out)
{
    char *end;unsigned long long n;
    if(!text || *text<'0' || *text>'9')return 0;
    errno=0;n=strtoull(text,&end,10);if(errno || *end || n>limit)return 0;
    *out=(uint64_t)n;return 1;
}
static int hex32(char *text,uint32_t *out)
{
    uint32_t n=0;if(!text || strlen(text)!=8)return 0;
    for(unsigned i=0;i<8;i++){
        unsigned c=(unsigned char)text[i],d;
        if(c>='0' && c<='9')d=c-'0';else if(c>='a' && c<='f')d=c-'a'+10;
        else if(c>='A' && c<='F')d=c-'A'+10;else return 0;
        n=(n<<4)|d;
    }
    *out=n;return 1;
}
static int decimal(char *text,double *out)
{
    char *end;double value;if(!text)return 0;
    errno=0;value=strtod(text,&end);if(errno || end==text || *end || !isfinite(value))return 0;
    *out=value;return 1;
}
static int header_identity(char **cursor,xqcoach_identity *id)
{
    uint64_t token,frame;uint32_t crc;char *backend;
    if(!number(word(cursor),UINT64_MAX,&token) || !number(word(cursor),UINT32_MAX,&frame) ||
       !hex32(word(cursor),&crc) || !(backend=word(cursor)) || strcmp(backend,XQCOACH_BACKEND))return 0;
    return xqcoach_identity_init(id,token,(uint32_t)frame,crc);
}
size_t xqcoach_encode_request(const xqcoach_identity *id,char *out,size_t cap)
{
    if(!identity_valid(id) || !out || !cap)return 0;
    int n=snprintf(out,cap,"XQ_COACH_REQUEST_V1 %llu %u %08x %s\n",(unsigned long long)id->token,id->frame,id->crc,id->backend);
    return n>0 && (size_t)n<cap?(size_t)n:0;
}
int xqcoach_parse_request(const char *text,size_t bytes,xqcoach_identity *out)
{
    char buffer[256],*cursor=buffer,*magic;xqcoach_identity candidate;
    if(!text || !out || !bytes || bytes>=sizeof(buffer) || text[bytes-1]!='\n' || memchr(text,0,bytes))return 0;
    memcpy(buffer,text,bytes);buffer[bytes]=0;magic=word(&cursor);
    if(!magic || strcmp(magic,"XQ_COACH_REQUEST_V1") || !header_identity(&cursor,&candidate) || word(&cursor))return 0;
    *out=candidate;return 1;
}
unsigned xqcoach_native_status(unsigned status)
{return status==2 || status==5 || status==6?5u:status;}
static int candidate_valid(const xqcoach_candidate *c,int partial)
{
    int mapped=c->file<9 && c->rank<10,unmapped=c->file==255 && c->rank==255;
    return c->class_id<14 && (partial==2?(mapped||unmapped):partial?unmapped:mapped) && c->confidence>=50 && c->confidence<=1000 &&
        isfinite(c->score) && c->score>=.05f && c->score<=1.f &&
        (unsigned)floor((double)c->score*1000.)==c->confidence &&
        isfinite(c->x0) && isfinite(c->y0) && isfinite(c->x1) && isfinite(c->y1) &&
        c->x0>=0 && c->y0>=0 && c->x1<=1280 && c->y1<=720 && c->x1>c->x0 && c->y1>c->y0;
}
static int result_valid(const xqcoach_result *r,int partial)
{
    if(!r || !identity_valid(&r->identity) || r->status>XQCOACH_CANCELLED || r->count>XQCOACH_MAX_CANDIDATES)return 0;
    if(r->estimated!=(unsigned)(partial==2))return 0;
    if(partial){if(r->status!=5 || !r->count)return 0;}
    else {if(r->status && r->count)return 0;if(r->status)return 1;}
    for(unsigned i=0;partial!=1 && i<4;i++)if(!isfinite(r->corners[i][0]) || !isfinite(r->corners[i][1]) ||
        r->corners[i][0]<0 || r->corners[i][0]>1279 || r->corners[i][1]<0 || r->corners[i][1]>719)return 0;
    for(unsigned i=0;i<r->count;i++)if(!candidate_valid(&r->candidates[i],partial))return 0;
    return 1;
}
static int append(char *out,size_t cap,size_t *used,const char *format,...)
{
    va_list args;int n;if(*used>=cap)return 0;
    va_start(args,format);n=vsnprintf(out+*used,cap-*used,format,args);va_end(args);
    if(n<0 || (size_t)n>=cap-*used)return 0;
    *used+=(size_t)n;return 1;
}
static size_t encode_packet(const xqcoach_result *r,char *out,size_t cap,int partial)
{
    size_t used=0;char header[256];int n;
    if(!result_valid(r,partial) || !out || cap<=sizeof(header) || cap>XQCOACH_PACKET_BYTES)return 0;
    char *body=out+sizeof(header);size_t body_cap=cap-sizeof(header);
    if(!r->status || partial){
        for(unsigned i=0;partial!=1 && i<4;i++)if(!append(body,body_cap,&used,"Q %.17g %.17g\n",r->corners[i][0],r->corners[i][1]))return 0;
        for(unsigned i=0;i<r->count;i++){
            const xqcoach_candidate *c=&r->candidates[i];
            if(!append(body,body_cap,&used,"D %u %u %u %u %.9g %.9g %.9g %.9g %.9g\n",
                c->class_id,c->file,c->rank,c->confidence,c->score,c->x0,c->y0,c->x1,c->y1))return 0;
        }
    }
    uint32_t crc=crc32_fast(0xffffffffu,body,(uint32_t)used)^0xffffffffu;
    n=snprintf(header,sizeof(header),"%s %llu %u %08x %s %u %u %08x\n",
        partial==2?"XQ_COACH_ESTIMATE_V1":partial?"XQ_COACH_PARTIAL_V1":"XQ_COACH_RESULT_V1",(unsigned long long)r->identity.token,r->identity.frame,r->identity.crc,r->identity.backend,r->status,r->count,crc);
    if(n<=0 || (size_t)n>=sizeof(header) || (size_t)n+used>=cap)return 0;
    memmove(out+n,body,used);memcpy(out,header,(size_t)n);out[n+used]=0;return (size_t)n+used;
}
static xqcoach_parse_status parse_packet(const char *text,size_t bytes,const xqcoach_identity *expected,
                                          xqcoach_result *out,unsigned *remote_status,int partial)
{
    char header[256],*cursor,*magic,*copy=NULL;uint64_t status,count;uint32_t crc;
    xqcoach_result candidate={0};xqcoach_parse_status answer=XQCOACH_INVALID;
    if(!text || !out || !identity_valid(expected) || !bytes || bytes>=XQCOACH_PACKET_BYTES || text[bytes-1]!='\n' || memchr(text,0,bytes))return answer;
    const char *newline=memchr(text,'\n',bytes);if(!newline || (size_t)(newline-text)>=sizeof(header))return answer;
    size_t head=(size_t)(newline-text),body_bytes=bytes-head-1;
    memcpy(header,text,head);header[head]=0;cursor=header;magic=word(&cursor);
    if(!magic || strcmp(magic,partial==2?"XQ_COACH_ESTIMATE_V1":partial?"XQ_COACH_PARTIAL_V1":"XQ_COACH_RESULT_V1") || !header_identity(&cursor,&candidate.identity) ||
       !identity_equal(&candidate.identity,expected) || !number(word(&cursor),XQCOACH_CANCELLED,&status) ||
       !number(word(&cursor),XQCOACH_MAX_CANDIDATES,&count) || !hex32(word(&cursor),&crc) || word(&cursor) ||
       crc!=(crc32_fast(0xffffffffu,newline+1,(uint32_t)body_bytes)^0xffffffffu))return answer;
    candidate.status=(unsigned)status;candidate.count=(unsigned)count;candidate.estimated=partial==2;
    if(partial){if(status!=5 || !count)return answer;}
    else if(status){if(count || body_bytes)return answer;if(remote_status)*remote_status=(unsigned)status;return XQCOACH_REJECTED;}
    copy=malloc(body_bytes+1);if(!copy)return answer;memcpy(copy,newline+1,body_bytes);copy[body_bytes]=0;cursor=copy;
    for(unsigned i=0;partial!=1 && i<4;i++){
        char *tag=word(&cursor);if(!tag || strcmp(tag,"Q") || !decimal(word(&cursor),&candidate.corners[i][0]) ||
           !decimal(word(&cursor),&candidate.corners[i][1]))goto done;
    }
    for(unsigned i=0;i<candidate.count;i++){
        xqcoach_candidate *c=&candidate.candidates[i];char *tag=word(&cursor);uint64_t cl,f,r,confidence;double v[5];
        if(!tag || strcmp(tag,"D") || !number(word(&cursor),13,&cl) || !number(word(&cursor),partial?255:8,&f) ||
           !number(word(&cursor),partial?255:9,&r) || !number(word(&cursor),1000,&confidence))goto done;
        for(unsigned j=0;j<5;j++)if(!decimal(word(&cursor),&v[j]))goto done;
        if(v[0]<.05 || v[0]>1 || v[1]<0 || v[2]<0 || v[3]>1280 || v[4]>720 || v[3]<=v[1] || v[4]<=v[2])goto done;
        c->class_id=(uint8_t)cl;c->file=(uint8_t)f;c->rank=(uint8_t)r;c->confidence=(uint16_t)confidence;
        c->score=(float)v[0];c->x0=(float)v[1];c->y0=(float)v[2];c->x1=(float)v[3];c->y1=(float)v[4];
    }
    if(word(&cursor) || !result_valid(&candidate,partial))goto done;
    *out=candidate;if(remote_status)*remote_status=(unsigned)status;answer=XQCOACH_ACCEPTED;
done:
    free(copy);return answer;
}
size_t xqcoach_encode_result(const xqcoach_result *r,char *o,size_t c){return encode_packet(r,o,c,0);}
size_t xqcoach_encode_partial(const xqcoach_result *r,char *o,size_t c){return encode_packet(r,o,c,r && r->estimated?2:1);}
xqcoach_parse_status xqcoach_parse_result(const char *t,size_t n,const xqcoach_identity *id,xqcoach_result *o,unsigned *s)
{return parse_packet(t,n,id,o,s,0);}
xqcoach_parse_status xqcoach_parse_partial(const char *t,size_t n,const xqcoach_identity *id,xqcoach_result *o)
{
    xqcoach_parse_status s=parse_packet(t,n,id,o,NULL,1);
    return s==XQCOACH_INVALID?parse_packet(t,n,id,o,NULL,2):s;
}
static int write_packet_atomic(const char *path,const xqcoach_result *r,int partial)
{
    char temporary[1024],*text=NULL;FILE *file=NULL;int okay=0;
    if(!path || snprintf(temporary,sizeof(temporary),"%s.part",path)>=(int)sizeof(temporary))return 0;
    text=malloc(XQCOACH_PACKET_BYTES);if(!text)return 0;
    size_t bytes=encode_packet(r,text,XQCOACH_PACKET_BYTES,partial);if(!bytes)goto done;
    file=fopen(temporary,"w");if(!file)goto done;
    if(fwrite(text,1,bytes,file)!=bytes || ferror(file))goto done;
    if(fclose(file)){file=NULL;goto done;}file=NULL;
    if(rename(temporary,path))goto done;
    okay=1;
done:
    if(file)fclose(file);
    if(!okay)unlink(temporary);
    free(text);return okay;
}
int xqcoach_write_result_atomic(const char *p,const xqcoach_result *r){return write_packet_atomic(p,r,0);}
int xqcoach_write_partial_atomic(const char *p,const xqcoach_result *r){return write_packet_atomic(p,r,r && r->estimated?2:1);}
xqcoach_parse_status xqcoach_read_result(const char *path,const xqcoach_identity *expected,xqcoach_result *out,unsigned *status)
{
    FILE *file=path?fopen(path,"r"):NULL;char *text=NULL;xqcoach_parse_status answer=XQCOACH_INVALID;
    if(!file)return answer;
    text=malloc(XQCOACH_PACKET_BYTES);if(!text)goto done;
    size_t bytes=fread(text,1,XQCOACH_PACKET_BYTES,file);
    if(bytes==XQCOACH_PACKET_BYTES || ferror(file) || fgetc(file)!=EOF)goto done;
    answer=xqcoach_parse_result(text,bytes,expected,out,status);
done:
    free(text);fclose(file);return answer;
}
