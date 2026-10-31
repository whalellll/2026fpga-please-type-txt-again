/* Test-only: small real-model windows, original weights/parameters/table. */
static void capture_exact(const struct pango_vision32_job *original,const char *prefix)
{
 struct pango_vision32_job j=*original;
 unsigned ci4=(j.cin+3)&~3u,k=j.cin*j.kernel*j.kernel;
 unsigned cw=j.width<j.kernel+2?j.width:j.kernel+2;
 unsigned ch=j.height<j.kernel+2?j.height:j.kernel+2;
 j.width=cw;j.height=ch;if(j.cout>9)j.cout=9;
 j.input=0x1000;j.weights=0x20000;j.params=0x80000;j.lut=0x60000;j.output=0x90000;
 unsigned groups=(j.cout+7)/8,ow=(cw+2*j.padding-j.kernel)/j.stride+1,oh=(ch+2*j.padding-j.kernel)/j.stride+1;
 unsigned char *memory=calloc(1,0x100000);assert(memory);
 for(unsigned y=0;y<ch;y++)memcpy(memory+j.input+y*cw*ci4,shadow+original->input+y*original->width*ci4,cw*ci4);
 memcpy(memory+j.weights,shadow+original->weights,groups*k*8);
 memcpy(memory+j.params,shadow+original->params,groups*96);
 if(j.flags&1)memcpy(memory+j.lut,shadow+original->lut,65536);
 char name[1024];FILE *f;
 snprintf(name,sizeof(name),"%s.mem",prefix);f=fopen(name,"w");assert(f);
 unsigned addresses[4]={j.input,j.weights,j.params,j.lut};
 unsigned lengths[4]={cw*ch*ci4,groups*k*8,groups*96,(j.flags&1)?65536u:0u};
 for(unsigned s=0;s<4;s++)if(lengths[s]){
  fprintf(f,"@%x\n",addresses[s]/4);
  for(unsigned i=0;i<lengths[s];i+=4){uint32_t v;memcpy(&v,memory+addresses[s]+i,4);fprintf(f,"%08x\n",v);}
 }
 fclose(f);
 snprintf(name,sizeof(name),"%s.cfg",prefix);f=fopen(name,"w");assert(f);
 unsigned cfg[16]={j.input+0x1b000000,j.weights+0x1b000000,j.output+0x1b000000,j.params+0x1b000000,j.lut+0x1b000000,cw,ch,j.cin,j.cout,j.kernel,j.stride,j.padding,j.flags,20000000,1,2};
 for(unsigned i=0;i<16;i++){fprintf(f,"%08x\n",cfg[i]);}
 fclose(f);
 snprintf(name,sizeof(name),"%s.gold",prefix);f=fopen(name,"w");assert(f);
 const int8_t *x=(const int8_t *)memory+j.input,*w=(const int8_t *)memory+j.weights;
 for(unsigned y=0;y<oh;y++)for(unsigned xx=0;xx<ow;xx++)for(unsigned co=0;co<j.cout;co++){
  int64_t sum=0;
  for(unsigned ky=0;ky<j.kernel;ky++)for(unsigned kx=0;kx<j.kernel;kx++){
   int iy=(int)(y*j.stride+ky)-(int)j.padding,ix=(int)(xx*j.stride+kx)-(int)j.padding;
   if(iy<0 || ix<0 || iy>=(int)ch || ix>=(int)cw)continue;
   for(unsigned ci=0;ci<j.cin;ci++)sum+=(int32_t)x[(iy*cw+ix)*ci4+ci]*w[((co/8)*k+(ky*j.kernel+kx)*j.cin+ci)*8+co%8];
  }
  int32_t b;uint32_t shift;memcpy(&b,memory+j.params+co*12,4);memcpy(&shift,memory+j.params+co*12+8,4);
  sum+=b;assert(sum>=INT32_MIN && sum<=INT32_MAX);
  uint64_t mag=sum<0?(uint64_t)-sum:(uint64_t)sum,q=mag>>shift;
  if(shift){uint64_t r=mag-(q<<shift),h=UINT64_C(1)<<(shift-1);if(r>h || (r==h && (q&1)))q++;}
  sum=sum<0?-(int64_t)q:(int64_t)q;
  int16_t value=sum>32767?32767:sum< -32768?-32768:(int16_t)sum;
  if(j.flags&1)value=((int8_t *)memory+j.lut)[(int)value+32768];
  fprintf(f,"%02x\n%02x\n",(unsigned)(uint16_t)value&255,(unsigned)(uint16_t)value>>8);
 }
 fclose(f);free(memory);
 snprintf(name,sizeof(name),"%s.ctl",prefix);f=fopen(name,"w");assert(f);
 unsigned ctl[6]={ow*oh*j.cout*2,0,0,((ow*oh+3)/4)*groups*k,ow*oh*j.cout,groups*k*8};
 for(unsigned i=0;i<6;i++){fprintf(f,"%08x\n",ctl[i]);}
 fclose(f);
}
