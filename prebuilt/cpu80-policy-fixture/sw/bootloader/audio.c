#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "audio.h"
#include "audio_sample.h"

#define AUDIO_PROGRESS_TIMEOUT (TIMEBASE_HZ / 4u)
#define SONG_DDR_ADDR           0x10000000u
#define SONG_DDR_LIMIT          0x00800000u
#define SONG_NAME               "SONG.PCM"

#define AUDIO_WAIT_READY        0
#define AUDIO_WAIT_STOP         1
#define AUDIO_WAIT_STALLED      (-1)

static fat_ro_volume_t song_volume;
static uint32_t song_progress_mark;
static int song_sd_error;
static uint32_t debug_volume=10u;

uint32_t audio_get_volume(void){return debug_volume;}
int audio_set_volume(uint32_t volume){
 if(volume<1u||volume>100u)return -1;
 debug_volume=volume;
 return 0;
}

static int audio_require_running(void){
 uint32_t start,first;
 if(REG32(AUDIO_BASE+AUDIO_ID)!=AUDIO_ID_VALUE){
  console_puts("Audio hardware ID mismatch: expected ");
  console_hex(AUDIO_ID_VALUE);console_puts(", got ");
  console_hex(REG32(AUDIO_BASE+AUDIO_ID));console_putc('\n');
  return AUDIO_ERR_NO_HARDWARE;
 }
 REG32(AUDIO_BASE+AUDIO_CONTROL)=1u;
 delay_cycles(64u);
 first=REG32(AUDIO_BASE+AUDIO_MIC_COUNT);
 start=read_mtime_ticks32();
 while(REG32(AUDIO_BASE+AUDIO_MIC_COUNT)==first){
  if((uint32_t)(read_mtime_ticks32()-start)>=AUDIO_PROGRESS_TIMEOUT){
   console_puts("Audio hardware stalled: I2S frame counter is not advancing.\n");
   return AUDIO_ERR_STALLED;
  }
 }
 return 0;
}

static int song_read_sectors(void *user,uint32_t lba,uint32_t count,
                             uint8_t *destination){
 int r;
 (void)user;
 r=sd_read_sectors(lba,count,destination);
 if(r)song_sd_error=r;
 return r;
}

static int song_load_progress(void *user,uint32_t done,uint32_t total){
 int c;
 (void)user;
 c=console_getc_timeout(1u);
 if(c==0x1b)return 1;
 if(done>=song_progress_mark&&done<total){
  console_putc('.');
  song_progress_mark+=1024u*1024u;
 }
 return 0;
}

static void song_print_error(int error){
 if(song_sd_error){
  console_puts("MicroSD protocol error ");console_dec((uint32_t)-song_sd_error);
 }else{
  console_puts("MicroSD filesystem error: ");console_puts(fat_ro_error_string(error));
  console_puts(" (");console_dec((uint32_t)-error);console_putc(')');
 }
 console_putc('\n');
}

static int song_mount(void){
 const sd_card_info_t *card;
 int r;
 song_sd_error=0;
 r=sd_init();
 if(r){song_sd_error=r;return FAT_RO_ERR_IO;}
 card=sd_card_info();
 return fat_ro_mount(&song_volume,song_read_sectors,0,
                     card?card->sector_count:0u);
}

static uint16_t song_le16(const uint8_t *p){
 return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));
}

static uint32_t song_le32(const uint8_t *p){
 return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
        ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}

static int song_tag(const uint8_t *p,char a,char b,char c,char d){
 return p[0]==(uint8_t)a&&p[1]==(uint8_t)b&&
        p[2]==(uint8_t)c&&p[3]==(uint8_t)d;
}

/* Raw files are signed 16-bit little-endian mono.  A RIFF input is accepted
 * only when its bounded data chunk is 16 kHz, 16-bit, mono PCM. */
static int song_audio_range(const uint8_t *buf,uint32_t size,
                            uint32_t *data_off,uint32_t *data_len,int *is_wav){
 uint32_t off,end;
 int have_fmt=0,have_data=0;
 *data_off=0u;*data_len=size;*is_wav=0;
 if(size<4u||!song_tag(buf,'R','I','F','F'))
  return (size!=0u&&!(size&1u))?FAT_RO_OK:FAT_RO_ERR_CORRUPT;
 if(size<12u||!song_tag(buf+8u,'W','A','V','E'))return FAT_RO_ERR_CORRUPT;
 end=song_le32(buf+4u);
 if(end<4u||end>size-8u)return FAT_RO_ERR_CORRUPT;
 end+=8u;
 off=12u;
 while(off<end){
  uint32_t len,payload,next;
  if(end-off<8u)return FAT_RO_ERR_CORRUPT;
  len=song_le32(buf+off+4u);payload=off+8u;
  if(len>end-payload)return FAT_RO_ERR_CORRUPT;
  next=payload+len;
  if(len&1u){if(next>=end)return FAT_RO_ERR_CORRUPT;next++;}
  if(song_tag(buf+off,'f','m','t',' ')){
   if(have_fmt||len<16u)return FAT_RO_ERR_CORRUPT;
   if(song_le16(buf+payload)!=1u||song_le16(buf+payload+2u)!=1u||
      song_le32(buf+payload+4u)!=16000u||
      song_le32(buf+payload+8u)!=32000u||
      song_le16(buf+payload+12u)!=2u||
      song_le16(buf+payload+14u)!=16u)
    return FAT_RO_ERR_UNSUPPORTED;
   have_fmt=1;
  }else if(song_tag(buf+off,'d','a','t','a')){
   if(have_data)return FAT_RO_ERR_CORRUPT;
   *data_off=payload;*data_len=len;have_data=1;
  }
  off=next;
 }
 if(!have_fmt||!have_data||!*data_len||(*data_len&1u))
  return FAT_RO_ERR_CORRUPT;
 *is_wav=1;
 return FAT_RO_OK;
}

static int audio_fifo_full(void){
 return (REG32(AUDIO_BASE+AUDIO_STATUS)>>8)&1u;
}

static int audio_key_action(void){
 int c=console_getc_timeout(0u);
 if(c=='q'||c==0x1b)return AUDIO_WAIT_STOP;
 if(c=='+'&&debug_volume<=95u)debug_volume+=5u;
 else if(c=='+'&&debug_volume<100u)debug_volume=100u;
 else if(c=='-'&&debug_volume>=6u)debug_volume-=5u;
 else if(c=='-'&&debug_volume>1u)debug_volume=1u;
 return AUDIO_WAIT_READY;
}

static int wait_fifo_not_full(void){
 uint32_t start=read_mtime_ticks32();
 while(audio_fifo_full()){
  if(audio_key_action()==AUDIO_WAIT_STOP)return AUDIO_WAIT_STOP;
  if((uint32_t)(read_mtime_ticks32()-start)>=AUDIO_PROGRESS_TIMEOUT)
   return AUDIO_WAIT_STALLED;
 }
 return AUDIO_WAIT_READY;
}

__attribute__((noinline, externally_visible)) int cmd_debug_speaker(void){
 fat_ro_file_t song;
 const uint8_t *pcm;
 uint32_t data_off,data_len,frames,played,i,underflows;
 int r,stopped,failed,is_wav;
 r=audio_require_running();
 if(r)return r;
 if(!sd_card_present()){
  console_puts("No MicroSD card; insert one with "SONG_NAME" in its root directory.\n");
  return SD_ERR_NO_CARD;
 }
 console_puts("Speaker test: loading "SONG_NAME" from MicroSD...\n");
 r=song_mount();
 if(r){song_print_error(r);sd_release();return r;}
 r=fat_ro_find(&song_volume,SONG_NAME,&song);
 if(r){
  console_puts("Missing SD file: "SONG_NAME" (");
  console_puts(fat_ro_error_string(r));console_puts(")\n");
  sd_release();return r;
 }
 if(!song.size||song.size>SONG_DDR_LIMIT||
    !ddr_range_valid(SONG_DDR_ADDR,song.size)){
  console_puts("SD file size is unsafe: "SONG_NAME" bytes=");
  console_dec(song.size);console_putc('\n');sd_release();
  return FAT_RO_ERR_RANGE;
 }
 console_puts("Found "SONG_NAME", bytes=");console_dec(song.size);console_putc('\n');
 song_progress_mark=1024u*1024u;
 ddr_wait_ready();
 r=fat_ro_load(&song_volume,&song,(void *)(uintptr_t)SONG_DDR_ADDR,
               song.size,song_load_progress,0);
 sd_release();
 if(r){
  console_putc('\n');
  if(r==FAT_RO_ERR_ABORTED)console_puts("SD load cancelled by Esc.\n");
  else song_print_error(r);
  return r;
 }
 console_puts(" done\n");
 pcm=(const uint8_t *)(uintptr_t)SONG_DDR_ADDR;
 r=song_audio_range(pcm,song.size,&data_off,&data_len,&is_wav);
 if(r){
  console_puts(SONG_NAME" must be even-length raw s16le or a valid 16 kHz/16-bit/mono PCM WAV.\n");
  return r;
 }
 frames=data_len>>1;
 REG32(AUDIO_BASE+AUDIO_CONTROL)=1u;
 console_puts("Playing ");console_puts(is_wav?"PCM WAV":"raw s16le");
 console_puts(": 16 kHz mono, ");console_dec(frames);console_puts(" samples (~");
 console_dec(frames/16000u);console_puts(" s per pass), volume=");
 console_dec(debug_volume);console_puts("%. +/- adjusts 5%, q or Esc stops.\n");
 stopped=0;failed=0;played=0;
 for(;;){
  for(i=0;i<frames;i++){
   uint32_t s;
   r=wait_fifo_not_full();
   if(r==AUDIO_WAIT_STOP){stopped=1;break;}
   if(r==AUDIO_WAIT_STALLED){failed=1;break;}
   s=audio_scale_pcm16(pcm+data_off+i*2u,debug_volume);
   REG32(AUDIO_BASE+AUDIO_PLAYBACK)=s;
   played++;
   if((played&0x3fu)==0u&&audio_key_action()==AUDIO_WAIT_STOP){stopped=1;break;}
  }
  if(stopped||failed)break;
  if(audio_key_action()==AUDIO_WAIT_STOP){stopped=1;break;}
 }
 underflows=REG32(AUDIO_BASE+AUDIO_UNDERFLOWS);
 if(failed){
  console_puts("Playback failed after ");console_dec(played);
  console_puts(" samples: I2S FIFO did not drain for 250 ms.\n");
  return AUDIO_ERR_STALLED;
 }
 console_puts("Playback stopped after ");console_dec(played);console_puts(" samples (");
 console_dec(played/16000u);console_puts(" s), underflows=");
 console_dec(underflows);console_puts(", volume=");
 console_dec(debug_volume);console_puts("%.\n");
 return 0;
}

int cmd_debug_mic(void){
 uint32_t last_count,last_progress,underflow_base=0u;
 uint32_t captured=0u,missed=0u;
 int r;
 r=audio_require_running();
 if(r)return r;
 console_puts("Microphone monitor: live 16 kHz INMP441 to MAX98357A; +/- adjusts 5%, q or Esc stops. Volume=");
 console_dec(debug_volume);console_puts("%.\n");
 REG32(AUDIO_BASE+AUDIO_CONTROL)=1u;
 delay_cycles(64u);
 last_count=REG32(AUDIO_BASE+AUDIO_MIC_COUNT);
 last_progress=read_mtime_ticks32();
 for(;;){
  uint32_t now=read_mtime_ticks32();
  uint32_t count=REG32(AUDIO_BASE+AUDIO_MIC_COUNT);
  if(count!=last_count){
   uint32_t delta=count-last_count;
   uint16_t sample=audio_mic24_to_pcm16(REG32(AUDIO_BASE+AUDIO_MIC_SAMPLE));
   if(delta!=1u){missed+=delta-1u;break;}
   if(audio_fifo_full()){missed++;break;}
   REG32(AUDIO_BASE+AUDIO_PLAYBACK)=audio_scale_sample16(sample,debug_volume);
   captured++;
   last_count=count;
   last_progress=now;
   if(captured==32u)underflow_base=REG32(AUDIO_BASE+AUDIO_UNDERFLOWS);
   if(captured>32u&&(captured&0x3fu)==0u&&
      REG32(AUDIO_BASE+AUDIO_UNDERFLOWS)-underflow_base>2u)break;
  }
  if(audio_key_action()==AUDIO_WAIT_STOP)break;
  if((uint32_t)(now-last_progress)>=AUDIO_PROGRESS_TIMEOUT){
   console_puts("Microphone monitor failed: I2S frame counter stopped for 250 ms.\n");
   return AUDIO_ERR_STALLED;
  }
 }
 console_puts("Microphone monitor stopped: samples=");console_dec(captured);
 console_puts(", missed=");console_dec(missed);
 console_puts(", underflows=");console_dec(REG32(AUDIO_BASE+AUDIO_UNDERFLOWS));
 console_puts(", volume=");console_dec(debug_volume);console_puts("%.\n");
 if(missed||(captured>32u&&REG32(AUDIO_BASE+AUDIO_UNDERFLOWS)-underflow_base>2u)){
  console_puts("Microphone monitor failed: dropped samples or sustained playback underflow.\n");
  return AUDIO_ERR_DROPPED;
 }
 return 0;
}
