#define _POSIX_C_SOURCE 200809L
#include "integer_hwc.h"
#include "crc32_fast.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv){
 if(argc<3 || argc>5){fputs("usage: integer-detector model.xqi input.hwc8 [repeats1..3] [output.f32]\n",stderr);return 2;}
 unsigned repeats=argc>=4?(unsigned)strtoul(argv[3],NULL,10):1;if(!repeats || repeats>3)return 2;
 int code=2;xqm_linux device={.fd=-1};xi8_tensor input={0};xi8_model *m=NULL;
 xi8_clock_init();uint64_t began=xi8_now();m=xi8_load(argv[1]);uint64_t loaded=xi8_now();if(!m)goto done;
 if(!xi8_input_load(m,argv[2],&input))goto done;uint64_t read=xi8_now();
 if(!xqm_linux_open(&device))goto done;uint64_t opened=xi8_now();
 for(unsigned repeat=0;repeat<repeats;repeat++){
  xi8_stats st={0};uint64_t a=xi8_now();if(!xi8_run(m,&device.io,&input,&st))goto done;uint64_t b=xi8_now();
  uint32_t crc=0xffffffffu;uint64_t exported=0;FILE *f=NULL;
  if(argc==5){f=fopen(argv[4],"wb");if(!f)goto done;}
  for(unsigned i=0;i<3;i++){
   size_t n=xi8_output_elements(m,i);void *out=malloc(n*4);unsigned dims[4];uint64_t mark=xi8_now();
   if(!out || !xi8_export_f32(m,i,out,n*4,dims)){free(out);if(f)fclose(f);goto done;}
   exported+=xi8_now()-mark;crc=crc32_fast(crc,out,n*4);
   if(f && (fwrite(dims,4,4,f)!=4 || fwrite(out,4,n,f)!=n)){free(out);fclose(f);goto done;}free(out);
  }
  if(f && fclose(f))goto done;
  printf("INTEGER_TIMING repeat=%u graph_us=%llu output_export_us=%llu model_load_us=%llu input_read_us=%llu device_open_us=%llu jobs=%llu cycles=%llu hardware_us=%llu output_crc=%08x float_ops=0 layout=HWC no_fallback=1\n",repeat,
   (unsigned long long)xi8_us(b-a),(unsigned long long)xi8_us(exported),(unsigned long long)xi8_us(loaded-began),(unsigned long long)xi8_us(read-loaded),(unsigned long long)xi8_us(opened-read),
   (unsigned long long)st.jobs,(unsigned long long)st.cycles,(unsigned long long)(st.cycles/495*10+st.cycles%495*10/495),crc^0xffffffffu);
  printf("INTEGER_STAGES pack_us=%llu output_pack_us=%llu parameter_copy_us=%llu ioctl_us=%llu nonconv_us=%llu allocate_us=%llu converted_input_values=%llu copied_input_bytes=%llu output_bytes=%llu parameter_upload_bytes=%llu parameter_saved_bytes=%llu\n",
   (unsigned long long)xi8_us(st.pack_ticks),(unsigned long long)xi8_us(st.output_ticks),(unsigned long long)xi8_us(st.weight_ticks),(unsigned long long)xi8_us(st.ioctl_ticks),(unsigned long long)xi8_us(st.ops_ticks),(unsigned long long)xi8_us(st.allocate_ticks),
   (unsigned long long)st.converted_input_values,(unsigned long long)st.copied_input_bytes,(unsigned long long)st.output_bytes,(unsigned long long)device.parameter_upload_bytes,(unsigned long long)device.parameter_saved_bytes);
  printf("INTEGER_MEMORY input_zero_bytes=%llu output_word_values=%llu reused_tensor_bytes=%llu allocated_tensor_bytes=%llu peak_tensor_bytes=%llu extra_pool_buffer_bytes=0\n",
   (unsigned long long)st.input_zero_bytes,(unsigned long long)st.output_word_values,(unsigned long long)st.reused_tensor_bytes,
   (unsigned long long)st.allocated_tensor_bytes,(unsigned long long)st.peak_tensor_bytes);
  fflush(stdout);
 }
 code=0;
done:xi8_tensor_free(&input);xi8_free(m);xqm_linux_close(&device);return code;
}
