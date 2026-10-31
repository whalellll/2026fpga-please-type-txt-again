/* Generic file IPC for explicit experimental model workers. Ordinary RAM
 * only; immutable capture token/frame/CRC and backend identity prevent stale
 * results from becoming moves. Used by PC assistance and the native worker. */
#include "crc32_fast.h"
#include <time.h>
#include <math.h>
static const char *picture_model_dir;
static uint64_t picture_model_token;
static uint32_t picture_model_crc;
static uint64_t picture_model_timeout_ms=900000;
static unsigned picture_model_manual_pending,picture_model_manual_submit;
static int picture_model_replace(const char *from,const char *to)
{
#ifdef _WIN32
    return MoveFileExA(from,to,MOVEFILE_REPLACE_EXISTING)!=0;
#else
    return rename(from,to)==0;
#endif
}
static const char *picture_backend_label(void)
{return picture_model_mode?picture_model_backend:"桩识别 无真实模型";}

static int picture_model_wait(const xqv_frame *frame,xqv_result *result)
{
    char path[512],temporary[512],request[512],request_part[512],response[512],manual[512],manual_part[512],magic[32],backend[64];
    FILE *file;
    uint64_t deadline=monotonic_milliseconds()+picture_model_timeout_ms,token;
    unsigned fid,crc,status,count,i,cid,f,r,score;
    int trailing,used_manual=picture_model_manual_submit;
    xqv_result candidate;
    double corners[4][2];
    xqg_detection boxes[32];
    ++picture_model_token;
    picture_model_manual_pending=0;
    picture_model_crc=crc32_fast(0xffffffffu,frame->rgb565,XQV_FRAME_BYTES)^0xffffffffu;
    if(snprintf(path,sizeof(path),"%s/frame.rgb565",picture_model_dir)>=(int)sizeof(path) ||
       snprintf(temporary,sizeof(temporary),"%s/frame.part",picture_model_dir)>=(int)sizeof(temporary) ||
       snprintf(request,sizeof(request),"%s/request.txt",picture_model_dir)>=(int)sizeof(request) ||
       snprintf(request_part,sizeof(request_part),"%s/request.part",picture_model_dir)>=(int)sizeof(request_part) ||
       snprintf(response,sizeof(response),"%s/result.txt",picture_model_dir)>=(int)sizeof(response) ||
       snprintf(manual,sizeof(manual),"%s/manual-corners.txt",picture_model_dir)>=(int)sizeof(manual) ||
       snprintf(manual_part,sizeof(manual_part),"%s/manual-corners.part",picture_model_dir)>=(int)sizeof(manual_part))return 0;
    remove(request);remove(response);
    remove(manual);
    if(picture_model_manual_submit) {
        /* Clicks are a0,i0,i9,a9. Normalize their cyclic order to image TL,TR,
         * BR,BL; orientation still comes from observed generals downstream. */
        unsigned first=0;double area=0;
        for(i=0;i<4;i++) {
            unsigned j=(i+1)%4;
            if(picture_corners[i][0]+picture_corners[i][1]<picture_corners[first][0]+picture_corners[first][1])first=i;
            area+=picture_corners[i][0]*picture_corners[j][1]-picture_corners[j][0]*picture_corners[i][1];
        }
        file=fopen(manual_part,"w");if(!file)return 0;
        int okay=fprintf(file,"XQ_MANUAL_CORNERS_V1 %llu %u %08x\n",(unsigned long long)picture_model_token,frame->frame_id,picture_model_crc)>0;
        for(i=0;i<4;i++) {
            unsigned j=(first+(area>0?i:4-i))%4;
            if(fprintf(file,"%.17g %.17g\n",picture_corners[j][0],picture_corners[j][1])<0)okay=0;
        }
        if(fclose(file))okay=0;
        picture_model_manual_submit=0;
        if(!okay || !picture_model_replace(manual_part,manual)){remove(manual_part);return 0;}
    }
    file=fopen(temporary,"wb");if(!file)return 0;
    { int okay=fwrite(frame->rgb565,1,XQV_FRAME_BYTES,file)==XQV_FRAME_BYTES;
      if(fclose(file))okay=0;
      if(!okay || !picture_model_replace(temporary,path)){remove(temporary);return 0;} }
    file=fopen(request_part,"w");if(!file)return 0;
    { int okay=fprintf(file,"XQ_MODEL_REQUEST_V1 %llu %u %08x %s\n",
        (unsigned long long)picture_model_token,frame->frame_id,picture_model_crc,picture_model_backend)>0;
      if(fclose(file))okay=0;
      if(!okay || !picture_model_replace(request_part,request)){remove(request_part);return 0;} }
    printf("XQ_MODEL_REQUEST token=%llu frame=%u crc=%08x backend=%s EXPERIMENTAL\n",
        (unsigned long long)picture_model_token,frame->frame_id,picture_model_crc,picture_model_backend);
    fflush(stdout);
    while(!(file=fopen(response,"r"))) {
        if(picture_cancel(NULL) || monotonic_milliseconds()>=deadline){remove(request);remove(manual);return 0;}
#ifdef _WIN32
        Sleep(20);
#else
        { const struct timespec wait={0,20000000};nanosleep(&wait,NULL); }
#endif
    }
    memset(&candidate,0,sizeof(candidate));memset(boxes,0,sizeof(boxes));
    { unsigned long long parsed_token;
      if(fscanf(file,"%31s %llu %u %x %63s %u %u",magic,&parsed_token,&fid,&crc,backend,&status,&count)!=7)
          goto bad;
      token=(uint64_t)parsed_token; }
    if(strcmp(magic,"XQ_MODEL_RESULT_V1") || strcmp(backend,picture_model_backend) ||
       token!=picture_model_token || fid!=frame->frame_id || crc!=picture_model_crc || count>32)goto bad;
    if(status) {
        /* Only an authenticated empty rejection can request manual geometry.
         * It carries no candidate board and cannot advance the game. */
        picture_model_manual_pending=status==8 && count==0;
        goto bad;
    }
    if(fscanf(file," %127[^\n]",candidate.fen)!=1)goto bad;
    candidate.abi_version=1;candidate.frame_id=fid;candidate.piece_count=count;candidate.confidence=1000;
    for(i=0;i<count;i++) {
        float x0,y0,x1,y1;
        if(fscanf(file,"%u %u %u %u %f %f %f %f",&cid,&f,&r,&score,&x0,&y0,&x1,&y1)!=8 ||
           cid>=14 || f>=9 || r>=10 || score>1000 || score<50 ||
           !isfinite(x0) || !isfinite(y0) || !isfinite(x1) || !isfinite(y1) ||
           x0<0 || y0<0 || x1>1280 || y1>720 || x1<=x0 || y1<=y0)goto bad;
        candidate.pieces[i]=(xqv_piece){(uint8_t)cid,(uint8_t)f,(uint8_t)r,(uint16_t)score};
        if(score<candidate.confidence)candidate.confidence=(uint16_t)score;
        boxes[i]=(xqg_detection){.x=(x0+x1)/2,.y=(y0+y1)/2,.x0=(uint16_t)x0,
            .y0=(uint16_t)y0,.x1=(uint16_t)x1,.y1=(uint16_t)y1,.confidence=(uint16_t)score,.class_id=(uint8_t)cid};
    }
    for(i=0;i<4;i++)if(fscanf(file,"%lf %lf",&corners[i][0],&corners[i][1])!=2)goto bad;
    do{trailing=fgetc(file);}while(trailing==' ' || trailing=='\r' || trailing=='\n' || trailing=='\t');
    if(trailing!=EOF || ferror(file))goto bad;
    { xq_search_board_t board;
      if(!xqv_result_board(&candidate,fid,&board) ||
         !xqr_manual_init(&picture_manual,(xqr_roi){0,0,1280,720},corners,++picture_preview_view))goto bad; }
    fclose(file);remove(request);remove(response);remove(manual);
    memcpy(picture_boxes,boxes,sizeof(boxes));*result=candidate;
    picture_model_geometry_manual=used_manual;
    printf("XQ_MODEL_RESULT token=%llu frame=%u pieces=%u backend=%s strict_usable=1\n",
        (unsigned long long)token,fid,count,backend);
    return 1;
bad:
    fclose(file);remove(request);remove(response);remove(manual);
    puts("XQ_MODEL_REJECT strict_result_or_identity_invalid no_fallback=1");return 0;
}
