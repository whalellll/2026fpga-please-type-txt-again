#include "soc.h"
#include "sd.h"

#define SD_ID_REG              (SD_BASE+0x00u)
#define SD_VERSION_REG         (SD_BASE+0x04u)
#define SD_CONTROL_REG         (SD_BASE+0x08u)
#define SD_STATUS_REG          (SD_BASE+0x0cu)
#define SD_DIV_REG             (SD_BASE+0x10u)
#define SD_ARGUMENT_REG        (SD_BASE+0x14u)
#define SD_COMMAND_REG         (SD_BASE+0x18u)
#define SD_RESPONSE0_REG       (SD_BASE+0x1cu)
#define SD_RESPONSE1_REG       (SD_BASE+0x20u)
#define SD_RESPONSE2_REG       (SD_BASE+0x24u)
#define SD_RESPONSE3_REG       (SD_BASE+0x28u)
#define SD_ERROR_REG           (SD_BASE+0x2cu)
#define SD_BLOCK_SIZE_REG      (SD_BASE+0x30u)
#define SD_BLOCK_COUNT_REG     (SD_BASE+0x34u)
#define SD_BLOCKS_DONE_REG     (SD_BASE+0x38u)
#define SD_BUFFER_STATUS_REG   (SD_BASE+0x3cu)
#define SD_BUFFER0_INDEX_REG   (SD_BASE+0x40u)
#define SD_BUFFER1_INDEX_REG   (SD_BASE+0x44u)
#define SD_IDLE_CLOCKS_REG     (SD_BASE+0x48u)
#define SD_TX_STATUS_REG       (SD_BASE+0x50u)
#define SD_TX_PUBLISH_REG      (SD_BASE+0x54u)
#define SD_TX_STOP_REG         (SD_BASE+0x58u)
#define SD_BUFFER0_BASE        (SD_BASE+0x100u)
#define SD_BUFFER1_BASE        (SD_BASE+0x300u)

#define SD_HW_ID               0x53444e32u
#define SD_HW_VERSION          0x00050401u
#define SD_HW_VERSION_LEGACY   0x00050400u

#define SD_CONTROL_RESET       (1u<<0)
#define SD_CONTROL_BUS4        (1u<<1)
#define SD_CONTROL_CLEAR       (1u<<2)
#define SD_CONTROL_ABORT       (1u<<3)

#define SD_STATUS_BUSY         (1u<<0)
#define SD_STATUS_DONE         (1u<<1)
#define SD_STATUS_ERROR        (1u<<2)
#define SD_STATUS_CARD         (1u<<3)
#define SD_STATUS_RAW          (1u<<4)
#define SD_STATUS_BUFFER0      (1u<<5)
#define SD_STATUS_BUFFER1      (1u<<6)
#define SD_STATUS_DATA_ACTIVE  (1u<<7)
#define SD_STATUS_CMD_ACTIVE   (1u<<8)
#define SD_STATUS_CLOCK_ACTIVE (1u<<9)
#define SD_STATUS_BUS4         (1u<<10)
#define SD_STATUS_AUTOSTOP     (1u<<11)

#define SD_ERROR_CMD_TIMEOUT   (1u<<0)
#define SD_ERROR_CMD_CRC       (1u<<1)
#define SD_ERROR_CMD_FRAME     (1u<<2)
#define SD_ERROR_DATA_TIMEOUT  (1u<<3)
#define SD_ERROR_DATA_CRC      (1u<<4)
#define SD_ERROR_DATA_END      (1u<<5)
#define SD_ERROR_REMOVED       (1u<<6)
#define SD_ERROR_OVERFLOW      (1u<<7)

#define SD_COMMAND_RESPONSE_NONE       0u
#define SD_COMMAND_RESPONSE_R48        1u
#define SD_COMMAND_RESPONSE_R48_NO_CRC 2u
#define SD_COMMAND_RESPONSE_R136       3u
#define SD_COMMAND_RESPONSE_R48_BUSY   4u
#define SD_COMMAND_DATA                (1u<<9)
#define SD_COMMAND_MULTI               (1u<<10)
#define SD_COMMAND_START               (1u<<11)
#define SD_COMMAND_WRITE               (1u<<12)

#define SD_BUFFER_RELEASE0      (1u<<0)
#define SD_BUFFER_RELEASE1      (1u<<1)

#define SD_INIT_DIV             62u
#define SD_TRANSFER_DIV         0u
#define SD_MAX_CHUNK_SECTORS    32u
#define SD_COMMAND_TIMEOUT      (TIMEBASE_HZ/2u)
#define SD_DATA_TIMEOUT         (TIMEBASE_HZ)
#define SD_WRITE_STREAM_TIMEOUT (TIMEBASE_HZ*2u)
#define SD_INIT_TIMEOUT         (TIMEBASE_HZ*2u)

#define SD_R1_ERROR_MASK        0xfdffe008u
#define SD_R1_OUT_OF_RANGE      0x80000000u
#define SD_R6_ERROR_MASK        0x0000e000u

static sd_card_info_t card_info;
static int card_initialized;
static int bus4_enabled;
static uint32_t last_hw_error;
static int preerase_supported;

static int hardware_version_valid(uint32_t version)
{return version==SD_HW_VERSION||version==SD_HW_VERSION_LEGACY;}

static void io_fence(void)
{
#ifdef __riscv
 __asm__ volatile ("fence iorw, iorw" ::: "memory");
#endif
}

static uint32_t control_value(uint32_t pulse)
{
 return (bus4_enabled?SD_CONTROL_BUS4:0u)|pulse;
}

static void clear_status(void)
{
 REG32(SD_CONTROL_REG)=control_value(SD_CONTROL_CLEAR);
}

static int error_status(uint32_t errors)
{
 if(errors&SD_ERROR_REMOVED)return SD_ERR_REMOVED;
 if(errors&(SD_ERROR_CMD_TIMEOUT|SD_ERROR_DATA_TIMEOUT))return SD_ERR_TIMEOUT;
 if(errors&(SD_ERROR_CMD_CRC|SD_ERROR_DATA_CRC))return SD_ERR_CRC;
 if(errors&(SD_ERROR_CMD_FRAME|SD_ERROR_DATA_END))return SD_ERR_PROTOCOL;
 if(errors&SD_ERROR_OVERFLOW)return SD_ERR_IO;
 return SD_ERR_IO;
}

static int wait_quiescent(uint32_t timeout)
{
 uint32_t start=read_mtime_ticks32();
 for(;;){
  uint32_t status=REG32(SD_STATUS_REG);
  if(!(status&(SD_STATUS_BUSY|SD_STATUS_DATA_ACTIVE|SD_STATUS_CMD_ACTIVE|
               SD_STATUS_CLOCK_ACTIVE)))return SD_OK;
  if((uint32_t)(read_mtime_ticks32()-start)>=timeout)return SD_ERR_TIMEOUT;
 }
}

static int wait_operation(uint32_t timeout)
{
 uint32_t start=read_mtime_ticks32();
 for(;;){
  uint32_t status=REG32(SD_STATUS_REG);
  if(!(status&SD_STATUS_CARD))return SD_ERR_REMOVED;
  if(status&SD_STATUS_ERROR){
   last_hw_error=REG32(SD_ERROR_REG);
   return error_status(last_hw_error);
  }
  if((status&SD_STATUS_DONE)&&
     !(status&(SD_STATUS_BUSY|SD_STATUS_DATA_ACTIVE|SD_STATUS_CMD_ACTIVE|
               SD_STATUS_CLOCK_ACTIVE)))return SD_OK;
  if((uint32_t)(read_mtime_ticks32()-start)>=timeout){
   return SD_ERR_TIMEOUT;
  }
 }
}

static int run_command(uint32_t index,uint32_t argument,uint32_t response,
                       uint32_t flags,uint32_t timeout)
{
 if(!sd_card_present())return SD_ERR_REMOVED;
 last_hw_error=0;
 clear_status();
 REG32(SD_ARGUMENT_REG)=argument;
 REG32(SD_COMMAND_REG)=SD_COMMAND_START|flags|(response<<6)|(index&0x3fu);
 return wait_operation(timeout);
}

static uint32_t response48_payload(void)
{
 uint32_t low=REG32(SD_RESPONSE0_REG);
 uint32_t high=REG32(SD_RESPONSE1_REG);
 return (low>>8)|((high&0xffu)<<24);
}

static int check_r1_mask(uint32_t error_mask)
{
 uint32_t response=response48_payload();
 if(response&error_mask){
  return SD_ERR_PROTOCOL;
 }
 return SD_OK;
}

static int check_r1(void)
{
 return check_r1_mask(SD_R1_ERROR_MASK);
}

static int run_r1_command(uint32_t index,uint32_t argument,uint32_t response)
{
 int r=run_command(index,argument,response,0u,SD_COMMAND_TIMEOUT);
 if(r)return r;
 return check_r1();
}

static int run_app_command(uint32_t index,uint32_t argument)
{
 int r=run_r1_command(55u,(uint32_t)card_info.rca<<16,
                      SD_COMMAND_RESPONSE_R48);
 if(r)return r;
 return run_r1_command(index,argument,SD_COMMAND_RESPONSE_R48);
}

static void copy_buffer(uint32_t source,uint8_t *destination,uint32_t bytes)
{
 typedef uint32_t sd_alias_word_t __attribute__((may_alias));
 uint32_t offset;
 if(((uintptr_t)destination&3u)==0u){
  volatile sd_alias_word_t *words=(volatile sd_alias_word_t *)destination;
  for(offset=0;offset<bytes;offset+=4u)words[offset/4u]=REG32(source+offset);
  return;
 }
 for(offset=0;offset<bytes;offset+=4u){
  uint32_t word=REG32(source+offset);
  destination[offset]=(uint8_t)word;
  destination[offset+1u]=(uint8_t)(word>>8);
  destination[offset+2u]=(uint8_t)(word>>16);
  destination[offset+3u]=(uint8_t)(word>>24);
 }
}

static int drain_ready_buffer(uint32_t number,uint32_t block_size,
                              uint32_t block_count,uint8_t *destination,
                              uint32_t *seen,uint32_t *received)
{
 uint32_t index;
 uint32_t source;
 uint32_t release;
 uint32_t bit;
 if(number==0u){
  index=REG32(SD_BUFFER0_INDEX_REG);
  source=SD_BUFFER0_BASE;
  release=SD_BUFFER_RELEASE0;
 }else{
  index=REG32(SD_BUFFER1_INDEX_REG);
  source=SD_BUFFER1_BASE;
  release=SD_BUFFER_RELEASE1;
 }
 if(index>=block_count){
  return SD_ERR_PROTOCOL;
 }
 bit=1u<<index;
 if(*seen&bit){
  REG32(SD_BUFFER_STATUS_REG)=release;
  return SD_OK;
 }
 copy_buffer(source,destination+index*block_size,block_size);
 *seen|=bit;
 (*received)++;
 REG32(SD_BUFFER_STATUS_REG)=release;
 return SD_OK;
}

static int read_data_command(uint32_t index,uint32_t argument,
                             uint32_t block_size,uint32_t block_count,
                             uint8_t *destination,uint32_t multi)
{
 uint32_t received=0;
 uint32_t seen=0;
 uint32_t progress_start;
 int r;
 if(!block_count||block_count>SD_MAX_CHUNK_SECTORS||
    !block_size||block_size>512u||(block_size&3u))return SD_ERR_PROTOCOL;
 if(!sd_card_present())return SD_ERR_REMOVED;
 last_hw_error=0;
 clear_status();
 REG32(SD_BLOCK_SIZE_REG)=block_size;
 REG32(SD_BLOCK_COUNT_REG)=block_count;
 REG32(SD_ARGUMENT_REG)=argument;
 REG32(SD_COMMAND_REG)=SD_COMMAND_START|SD_COMMAND_DATA|
                       (multi?SD_COMMAND_MULTI:0u)|
                       (SD_COMMAND_RESPONSE_R48<<6)|(index&0x3fu);
 progress_start=read_mtime_ticks32();
 for(;;){
  uint32_t status=REG32(SD_STATUS_REG);
  if(!(status&SD_STATUS_CARD))return SD_ERR_REMOVED;
  if(status&SD_STATUS_ERROR){
   last_hw_error=REG32(SD_ERROR_REG);
   return error_status(last_hw_error);
  }
  if(status&SD_STATUS_BUFFER0){
   uint32_t before=received;
   r=drain_ready_buffer(0u,block_size,block_count,destination,&seen,&received);
   if(r)return r;
   if(received!=before)progress_start=read_mtime_ticks32();
   continue;
  }
  if(status&SD_STATUS_BUFFER1){
   uint32_t before=received;
   r=drain_ready_buffer(1u,block_size,block_count,destination,&seen,&received);
   if(r)return r;
   if(received!=before)progress_start=read_mtime_ticks32();
   continue;
  }
  if((status&SD_STATUS_DONE)&&
     !(status&(SD_STATUS_BUSY|SD_STATUS_DATA_ACTIVE|SD_STATUS_CMD_ACTIVE|
               SD_STATUS_CLOCK_ACTIVE))){
   if(received!=block_count){
    return SD_ERR_IO;
   }
   /* The successful multi-block path ends with the controller's automatic
    * CMD12.  SD permits that stop response to report OUT_OF_RANGE when the
    * preceding CMD18 reached the final user block; all other R1 error bits
    * and every non-stop response remain strict. */
   if(multi)
    return check_r1_mask(SD_R1_ERROR_MASK&~SD_R1_OUT_OF_RANGE);
   return check_r1();
  }
  if((uint32_t)(read_mtime_ticks32()-progress_start)>=SD_DATA_TIMEOUT){
   return SD_ERR_TIMEOUT;
  }
 }
}

static void stop_failed_transfer(uint32_t multi)
{
 uint32_t saved_error=last_hw_error;
 uint32_t blocks_done=REG32(SD_BLOCKS_DONE_REG);
 uint32_t blocks_expected=REG32(SD_BLOCK_COUNT_REG);
 uint32_t manual_stop=multi&&(blocks_done<blocks_expected);
 REG32(SD_CONTROL_REG)=control_value(SD_CONTROL_ABORT);
 (void)wait_quiescent(SD_COMMAND_TIMEOUT);
 if(manual_stop&&sd_card_present()){
  (void)run_command(12u,0u,SD_COMMAND_RESPONSE_R48_BUSY,0u,
                    SD_COMMAND_TIMEOUT);
 }
 clear_status();
 last_hw_error=saved_error;
}

static int parse_csd(void)
{
 uint32_t csd0=REG32(SD_RESPONSE0_REG);
 uint32_t csd1=REG32(SD_RESPONSE1_REG);
 uint32_t csd2=REG32(SD_RESPONSE2_REG);
 uint32_t csd3=REG32(SD_RESPONSE3_REG);
 uint32_t structure=(csd3>>30)&3u;
 (void)csd0;
 if(structure==1u){
  uint32_t c_size=((csd2&0x3fu)<<16)|(csd1>>16);
  if(!card_info.high_capacity)return SD_ERR_UNSUPPORTED;
  if(c_size==0x003fffffu)return SD_ERR_UNSUPPORTED;
  card_info.sector_count=(c_size+1u)<<10;
 }else if(structure==0u){
  uint32_t read_bl_len=(csd2>>16)&15u;
  uint32_t c_size=((csd2&0x3ffu)<<2)|(csd1>>30);
  uint32_t c_size_mult=(csd1>>15)&7u;
  uint32_t shift=read_bl_len+c_size_mult+2u;
  if(card_info.high_capacity)return SD_ERR_UNSUPPORTED;
  if(shift<9u||shift-9u>=20u||
     (c_size+1u)>(0xffffffffu>>(shift-9u)))return SD_ERR_UNSUPPORTED;
  card_info.sector_count=(c_size+1u)<<(shift-9u);
  if(card_info.sector_count>0x00800000u)return SD_ERR_UNSUPPORTED;
 }else return SD_ERR_UNSUPPORTED;
 if(!card_info.sector_count)return SD_ERR_UNSUPPORTED;
 return SD_OK;
}

int sd_card_present(void)
{
 if(REG32(SD_ID_REG)!=SD_HW_ID)return 0;
 if(!hardware_version_valid(REG32(SD_VERSION_REG)))return 0;
 return (REG32(SD_STATUS_REG)&SD_STATUS_CARD)!=0;
}

int sd_card_raw_present(void)
{
 if(REG32(SD_ID_REG)!=SD_HW_ID)return 0;
 if(!hardware_version_valid(REG32(SD_VERSION_REG)))return 0;
 return (REG32(SD_STATUS_REG)&SD_STATUS_RAW)!=0;
}

void sd_release(void)
{
 card_initialized=0;
 if(REG32(SD_ID_REG)!=SD_HW_ID)return;
 REG32(SD_CONTROL_REG)=control_value(SD_CONTROL_ABORT);
 (void)wait_quiescent(SD_COMMAND_TIMEOUT);
 bus4_enabled=0;
 REG32(SD_CONTROL_REG)=SD_CONTROL_RESET;
 REG32(SD_DIV_REG)=SD_INIT_DIV;
 REG32(SD_CONTROL_REG)=SD_CONTROL_CLEAR;
}

const sd_card_info_t *sd_card_info(void)
{
 return &card_info;
}

int sd_init(void)
{
 uint8_t scr[8];
 uint32_t response;
 uint32_t start;
 int ready=0;
 int r;
 card_initialized=0;
 bus4_enabled=0;
 last_hw_error=0;
 card_info.ocr=0;
 card_info.sector_count=0;
 card_info.transfer_hz=0;
 card_info.rca=0;
 card_info.version2=0;
 card_info.high_capacity=0;
 card_info.bus_width=0;
 preerase_supported=1;
 if(REG32(SD_ID_REG)!=SD_HW_ID||!hardware_version_valid(REG32(SD_VERSION_REG)))
  return SD_ERR_IO;
 if(!(REG32(SD_STATUS_REG)&SD_STATUS_CARD))return SD_ERR_NO_CARD;

 REG32(SD_CONTROL_REG)=SD_CONTROL_RESET;
 REG32(SD_DIV_REG)=SD_INIT_DIV;
 REG32(SD_BLOCK_SIZE_REG)=512u;
 REG32(SD_BLOCK_COUNT_REG)=1u;
 clear_status();
 r=wait_quiescent(SD_COMMAND_TIMEOUT);
 if(r)return r;
 clear_status();
 REG32(SD_IDLE_CLOCKS_REG)=80u;
 r=wait_operation(SD_COMMAND_TIMEOUT);
 if(r)return r;

 r=run_command(0u,0u,SD_COMMAND_RESPONSE_NONE,0u,SD_COMMAND_TIMEOUT);
 if(r)return r;
 r=run_command(8u,0x000001aau,SD_COMMAND_RESPONSE_R48,0u,
               SD_COMMAND_TIMEOUT);
 if(r==SD_ERR_TIMEOUT){
  /* Version 1.x SDSC cards are allowed not to answer CMD8.  Keep this
   * compatibility path, but do not hide CRC/framing/removal failures as a
   * legacy card. */
  r=wait_quiescent(SD_COMMAND_TIMEOUT);
  if(r)return r;
  clear_status();
 }else if(r){
  return r;
 }else{
  response=response48_payload();
  if(response&0x00400000u){
   /* An R1 ILLEGAL_COMMAND response also identifies a pre-v2 card. */
   card_info.version2=0u;
  }else{
   if(response!=0x000001aau)return SD_ERR_UNSUPPORTED;
   card_info.version2=1u;
  }
 }

 start=read_mtime_ticks32();
 do{
  r=run_r1_command(55u,0u,SD_COMMAND_RESPONSE_R48);
  if(r)return r;
  r=run_command(41u,card_info.version2?0x40ff8000u:0x00ff8000u,
                SD_COMMAND_RESPONSE_R48_NO_CRC,0u,
                SD_COMMAND_TIMEOUT);
  if(r)return r;
  card_info.ocr=response48_payload();
  if(card_info.ocr&0x80000000u){ready=1;break;}
 }while((uint32_t)(read_mtime_ticks32()-start)<SD_INIT_TIMEOUT);
 if(!ready)return SD_ERR_TIMEOUT;
 if(!(card_info.ocr&0x00ff8000u))return SD_ERR_UNSUPPORTED;
 card_info.high_capacity=(uint8_t)((card_info.ocr>>30)&1u);

 r=run_command(2u,0u,SD_COMMAND_RESPONSE_R136,0u,SD_COMMAND_TIMEOUT);
 if(r)return r;
 card_info.cid[0]=REG32(SD_RESPONSE0_REG);
 card_info.cid[1]=REG32(SD_RESPONSE1_REG);
 card_info.cid[2]=REG32(SD_RESPONSE2_REG);
 card_info.cid[3]=REG32(SD_RESPONSE3_REG);
 r=run_command(3u,0u,SD_COMMAND_RESPONSE_R48,0u,SD_COMMAND_TIMEOUT);
 if(r)return r;
 response=response48_payload();
 if(response&SD_R6_ERROR_MASK)return SD_ERR_PROTOCOL;
 card_info.rca=(uint16_t)(response>>16);
 if(!card_info.rca)return SD_ERR_PROTOCOL;

 r=run_command(9u,(uint32_t)card_info.rca<<16,
               SD_COMMAND_RESPONSE_R136,0u,SD_COMMAND_TIMEOUT);
 if(r)return r;
 r=parse_csd();
 if(r)return r;
 r=run_r1_command(7u,(uint32_t)card_info.rca<<16,
                  SD_COMMAND_RESPONSE_R48_BUSY);
 if(r)return r;
 if(!card_info.high_capacity){
  r=run_r1_command(16u,512u,SD_COMMAND_RESPONSE_R48);
  if(r)return r;
 }

 r=run_r1_command(55u,(uint32_t)card_info.rca<<16,
                  SD_COMMAND_RESPONSE_R48);
 if(r)return r;
 r=read_data_command(51u,0u,8u,1u,scr,0u);
 if(r)return r;
 if(!(scr[1]&0x04u))return SD_ERR_UNSUPPORTED;
 r=run_app_command(42u,0u);
 if(r)return r;
 r=run_app_command(6u,2u);
 if(r)return r;

 bus4_enabled=1;
 REG32(SD_CONTROL_REG)=control_value(SD_CONTROL_CLEAR);
 if(!(REG32(SD_STATUS_REG)&SD_STATUS_BUS4))return SD_ERR_PROTOCOL;
 REG32(SD_DIV_REG)=SD_TRANSFER_DIV;
 REG32(SD_BLOCK_SIZE_REG)=512u;
 card_info.bus_width=4u;
 card_info.transfer_hz=SYS_CLOCK_HZ/(2u*(SD_TRANSFER_DIV+1u));
 card_initialized=1;
 return SD_OK;
}

int sd_read_sectors(uint32_t lba,uint32_t count,uint8_t *buffer)
{
 uint32_t done=0;
 if(!card_initialized||!buffer)return SD_ERR_IO;
 if(!count)return SD_OK;
 if(lba>=card_info.sector_count||count>card_info.sector_count-lba)
  return SD_ERR_UNSUPPORTED;
 while(done<count){
  uint32_t chunk=count-done;
  uint32_t argument;
  int attempt;
  int r=SD_ERR_IO;
  if(chunk>SD_MAX_CHUNK_SECTORS)chunk=SD_MAX_CHUNK_SECTORS;
  argument=card_info.high_capacity?lba+done:(lba+done)<<9;
  for(attempt=0;attempt<2;attempt++){
   r=read_data_command(chunk==1u?17u:18u,argument,512u,chunk,
                       buffer+done*512u,chunk>1u);
   if(!r)break;
   stop_failed_transfer(chunk>1u);
   if(!sd_card_present())break;
  }
  if(r){
   console_puts("MicroSD read failed at LBA ");console_dec(lba+done);
   console_puts(" after retry, error ");console_dec((uint32_t)-r);
    if(last_hw_error){console_puts(" hw=");console_hex(last_hw_error);}
    console_putc('\n');
    sd_release();
   return r;
  }
  done+=chunk;
 }
 return SD_OK;
}

int sd_read_sector(uint32_t lba,uint8_t *buffer)
{
 return sd_read_sectors(lba,1u,buffer);
}

static void fill_write_buffer(uint32_t number,const uint8_t *buffer)
{
 typedef uint32_t sd_alias_word_t __attribute__((may_alias));
 uint32_t offset,base=number?SD_BUFFER1_BASE:SD_BUFFER0_BASE;
 if(((uintptr_t)buffer&3u)==0u){
  volatile const sd_alias_word_t *words=(volatile const sd_alias_word_t *)buffer;
  for(offset=0;offset<512u;offset+=4u)REG32(base+offset)=words[offset/4u];
 }else{
  for(offset=0;offset<512u;offset+=4u)
   REG32(base+offset)=(uint32_t)buffer[offset]|
    ((uint32_t)buffer[offset+1u]<<8)|((uint32_t)buffer[offset+2u]<<16)|
    ((uint32_t)buffer[offset+3u]<<24);
 }
}

int sd_write_sector(uint32_t lba,const uint8_t *buffer)
{
 uint32_t start,status;
 int r;
 if(!card_initialized||!buffer)return SD_ERR_IO;
 if(!card_info.high_capacity||card_info.bus_width!=4u||lba>=card_info.sector_count)
  return SD_ERR_UNSUPPORTED;
 if(!sd_card_present())return SD_ERR_REMOVED;
 r=wait_quiescent(SD_COMMAND_TIMEOUT);
 if(r)return r;
 clear_status();
 fill_write_buffer(0u,buffer);
 REG32(SD_BLOCK_SIZE_REG)=512u;
 REG32(SD_BLOCK_COUNT_REG)=1u;
 REG32(SD_ARGUMENT_REG)=lba;
 io_fence();
 REG32(SD_COMMAND_REG)=SD_COMMAND_START|SD_COMMAND_WRITE|
                      (SD_COMMAND_RESPONSE_R48<<6)|24u;
 start=read_mtime_ticks32();
 for(;;){
  status=REG32(SD_STATUS_REG);
  if(!(status&SD_STATUS_RAW)){r=SD_ERR_REMOVED;break;}
  // An error response can precede programming busy. Drain it before any
  // reset, retry, new command or Esc cleanup at the filesystem layer.
  if((status&SD_STATUS_DONE)&&!(status&(SD_STATUS_BUSY|SD_STATUS_DATA_ACTIVE|
                                      SD_STATUS_CMD_ACTIVE|SD_STATUS_CLOCK_ACTIVE))){
   if(status&SD_STATUS_ERROR){
    last_hw_error=REG32(SD_ERROR_REG);r=error_status(last_hw_error);
   }else r=check_r1();
   break;
  }
  if((uint32_t)(read_mtime_ticks32()-start)>=SD_DATA_TIMEOUT){r=SD_ERR_TIMEOUT;break;}
 }
 if(!r){
  r=run_r1_command(13u,(uint32_t)card_info.rca<<16,SD_COMMAND_RESPONSE_R48);
  if(!r&&(response48_payload()&0x00001f00u)!=0x00000900u)r=SD_ERR_PROTOCOL;
 }
 if(r){
  (void)wait_quiescent(SD_DATA_TIMEOUT);
  sd_release();
 }
 return r;
}

static int preerase_write_blocks(uint32_t count)
{
 uint32_t errors;int r;
 if(!preerase_supported)return SD_OK;
 r=run_r1_command(55u,(uint32_t)card_info.rca<<16,SD_COMMAND_RESPONSE_R48);
 if(r)return r;
 /* CMD55 must arm the application-command interpretation. Otherwise command
  * 23 could mean ordinary SET_BLOCK_COUNT instead of the intended ACMD23. */
 if(!(response48_payload()&0x20u))return SD_ERR_PROTOCOL;
 r=run_command(23u,count,SD_COMMAND_RESPONSE_R48,0u,SD_COMMAND_TIMEOUT);
 if(r)return r;
 errors=response48_payload()&SD_R1_ERROR_MASK;
 /* Only an otherwise valid ILLEGAL_COMMAND response permits fallback.
  * CRC, timeout, address, write-protect and all other failures stay fatal. */
 if(errors==0x00400000u){preerase_supported=0;return SD_OK;}
 return errors||!(response48_payload()&0x20u)?SD_ERR_PROTOCOL:SD_OK;
}

static void publish_write_buffer(uint32_t bank)
{
 /* Payload stores must reach the controller before ownership is published;
  * publication must reach it before a start command or producer reuse. */
 io_fence();REG32(SD_TX_PUBLISH_REG)=1u<<bank;io_fence();
}

static int write_multiple_command(uint32_t lba,uint32_t count,
                                  const uint8_t *buffer,
                                  sd_write_poll_fn poll,void *user)
{
 uint32_t submitted=0,completed=0,progress_start,status,tx;
 int cancelled=0,r;
 r=wait_quiescent(SD_COMMAND_TIMEOUT);if(r)return r;
 if(poll&&poll(user))return SD_ERR_ABORTED;
 /* This hint may discard the unwritten remainder when interrupted, so the
  * caller must own every reserved sector in the complete contiguous batch. */
 r=preerase_write_blocks(count);if(r)goto fail;
 clear_status();
 REG32(SD_BLOCK_SIZE_REG)=512u;
 REG32(SD_BLOCK_COUNT_REG)=count;
 fill_write_buffer(0u,buffer);publish_write_buffer(0u);submitted=1u;
 fill_write_buffer(1u,buffer+512u);publish_write_buffer(1u);submitted=2u;
 REG32(SD_ARGUMENT_REG)=lba;
 io_fence();
 REG32(SD_COMMAND_REG)=SD_COMMAND_START|SD_COMMAND_WRITE|SD_COMMAND_MULTI|
                       (SD_COMMAND_RESPONSE_R48<<6)|25u;
 progress_start=read_mtime_ticks32();
 for(;;){
  status=REG32(SD_STATUS_REG);
  if(!(status&SD_STATUS_RAW)){r=SD_ERR_REMOVED;break;}
  if((status&SD_STATUS_DONE)&&!(status&(SD_STATUS_BUSY|SD_STATUS_DATA_ACTIVE|
                                      SD_STATUS_CMD_ACTIVE|SD_STATUS_CLOCK_ACTIVE))){
   if(status&SD_STATUS_ERROR){
    last_hw_error=REG32(SD_ERROR_REG);r=error_status(last_hw_error);
   }else if(!cancelled&&REG32(SD_BLOCKS_DONE_REG)!=count)r=SD_ERR_IO;
   else r=check_r1(); /* Automatic CMD12 response, strict for writes. */
   break;
  }
  if(!cancelled&&poll&&poll(user)){
   cancelled=1;REG32(SD_TX_STOP_REG)=1u;progress_start=read_mtime_ticks32();
  }
  tx=REG32(SD_BLOCKS_DONE_REG);
  if(tx!=completed){completed=tx;progress_start=read_mtime_ticks32();}
  if(!cancelled&&!(status&SD_STATUS_ERROR)&&submitted<count){
   uint32_t bank=submitted&1u;
   tx=REG32(SD_TX_STATUS_REG);
   if(!(tx&(1u<<bank))){
    fill_write_buffer(bank,buffer+submitted*512u);
    publish_write_buffer(bank);submitted++;
   }
  }
  if((uint32_t)(read_mtime_ticks32()-progress_start)>=SD_WRITE_STREAM_TIMEOUT){
   REG32(SD_TX_STOP_REG)=1u;r=SD_ERR_TIMEOUT;break;
  }
 }
 if(!r){
  r=run_r1_command(13u,(uint32_t)card_info.rca<<16,SD_COMMAND_RESPONSE_R48);
  if(!r&&(response48_payload()&0x00001f00u)!=0x00000900u)r=SD_ERR_PROTOCOL;
 }
 if(!r)return cancelled?SD_ERR_ABORTED:SD_OK;
fail:
 /* No uncertain write retry. Attempt bounded drain, then invalidate the
  * session; the FAT caller may reinitialize the same CID for rollback. */
 (void)wait_quiescent(SD_WRITE_STREAM_TIMEOUT);
 sd_release();return r;
}

int sd_write_sectors(uint32_t lba,uint32_t count,const uint8_t *buffer,
                     sd_write_poll_fn poll,void *user)
{
 uint32_t done=0;int r;
 if(!card_initialized||!buffer)return SD_ERR_IO;
 if(!count)return SD_OK;
 if(!card_info.high_capacity||card_info.bus_width!=4u||
    lba>=card_info.sector_count||count>card_info.sector_count-lba)
  return SD_ERR_UNSUPPORTED;
 while(done<count){
  uint32_t chunk=count-done;
  if(chunk>SD_MAX_CHUNK_SECTORS)chunk=SD_MAX_CHUNK_SECTORS;
  if(chunk==1u||REG32(SD_VERSION_REG)==SD_HW_VERSION_LEGACY){
   if(poll&&poll(user))return SD_ERR_ABORTED;
   r=sd_write_sector(lba+done,buffer+done*512u);chunk=1u;
  }else{
   r=write_multiple_command(lba+done,chunk,buffer+done*512u,poll,user);
  }
  if(r)return r;
  done+=chunk;
 }
 return SD_OK;
}
