#include "soc.h"

static const uint8_t my_mac[6]={0x02,0x50,0x47,0x32,0x00,0x01};
static uint32_t my_ip=0xc0a80132u; /* default: 192.168.1.50 */
static uint8_t tx[1536],server_mac[6];static uint16_t ip_id;static uint32_t server_ip_active;
static const uint8_t rgmii_eye_steps[]={0,16,32,48,64,80,96,112,128,144,160,176,192,208,224,240,247};
/* Long frames need more eye margin than an ARP reply.  Start near the RGMII
 * 1.5 ns centre and retain several retries at each tap before moving on. */
static const uint8_t rgmii_data_steps[]={224,208,192,176,160,144,128,112,96,80,64,48,32,16,0,240,247};
static const uint16_t tftp_block_sizes[]={512,256,128,64};
static uint8_t rgmii_tx_step=100,rgmii_rx_step=247;
static uint8_t rgmii_data_index;
static void rgmii_set_delay(uint8_t tx_step,uint8_t rx_step){rgmii_tx_step=tx_step;rgmii_rx_step=rx_step;REG32(ETH_BASE+28)=((uint32_t)rx_step<<8)|tx_step;}
static void p16(uint8_t*p,uint16_t v){p[0]=v>>8;p[1]=v;}
static void p32(uint8_t*p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static uint16_t r16(uint32_t o){return ((uint16_t)REG8(ETH_RXBUF+o)<<8)|REG8(ETH_RXBUF+o+1);}
static uint32_t r32(uint32_t o){return ((uint32_t)r16(o)<<16)|r16(o+2);}
static uint32_t eth_crc_byte(uint32_t c,uint8_t d){int k;for(k=0;k<8;k++)c=(c^(d>>k))&1?((c>>1)^0xedb88320u):(c>>1);return c;}
static int frame_fcs_ok(uint32_t n){uint32_t c=0xffffffffu,i;if(n<18||n>2048)return 0;for(i=0;i<n;i++)c=eth_crc_byte(c,REG8(ETH_RXBUF+i));return c==0xdebb20e3u;}
static uint16_t ip_sum(uint8_t*p,uint32_t n){uint32_t s=0,i;for(i=0;i<n;i+=2)s+=((uint16_t)p[i]<<8)|p[i+1];while(s>>16)s=(s&0xffff)+(s>>16);return (uint16_t)~s;}
static void send_frame(uint32_t n){uint32_t i,t=read_mtime_ticks32();while(REG32(ETH_BASE+4)&2){if((uint32_t)(read_mtime_ticks32()-t)>TIMEBASE_HZ/5u)return;}for(i=0;i<n;i++)REG8(ETH_TXBUF+i)=tx[i];REG32(ETH_BASE+12)=n;REG32(ETH_BASE+16)=2;}
static void pop(void){REG32(ETH_BASE+16)=1;}
void eth_init(void){
 /* A JTAG CRAM reconfiguration does not guarantee that the external PHY saw
  * a reset pulse.  Force one at every boot, wait beyond the 2.5 s hardware
  * pulse, then clear stale MAC ownership/error state before link startup. */
 REG32(ETH_BASE+16)=16;
 delay_cycles(TIMEBASE_HZ*4u);
 REG32(ETH_BASE+16)=5;
}
void eth_set_ip(uint32_t ip){my_ip=ip;}

static void arp_request(uint32_t ip){uint32_t i;for(i=0;i<6;i++){tx[i]=0xff;tx[6+i]=my_mac[i];}p16(tx+12,0x0806);p16(tx+14,1);p16(tx+16,0x0800);tx[18]=6;tx[19]=4;p16(tx+20,1);for(i=0;i<6;i++)tx[22+i]=my_mac[i];p32(tx+28,my_ip);for(i=0;i<6;i++)tx[32+i]=0;p32(tx+38,ip);send_frame(42);}
static void arp_reply_from_rx(void){uint32_t i,peer_ip=r32(28);for(i=0;i<6;i++){uint8_t peer=REG8(ETH_RXBUF+22+i);tx[i]=peer;tx[6+i]=my_mac[i];tx[32+i]=peer;}p16(tx+12,0x0806);p16(tx+14,1);p16(tx+16,0x0800);tx[18]=6;tx[19]=4;p16(tx+20,2);for(i=0;i<6;i++)tx[22+i]=my_mac[i];p32(tx+28,my_ip);p32(tx+38,peer_ip);}
static int arp_trial(uint32_t ip){
 uint32_t t,i;
 while(REG32(ETH_BASE+4)&1)pop();
 arp_request(ip);t=read_mtime_ticks32();
 while((uint32_t)(read_mtime_ticks32()-t)<TIMEBASE_HZ/20u){
  if(REG32(ETH_BASE+4)&1){
   uint32_t n=REG32(ETH_BASE+8);
   if(frame_fcs_ok(n)){n-=4;}else{pop();continue;}
   if(n>=42&&r16(12)==0x0806&&r16(20)==2&&r32(28)==ip&&r32(38)==my_ip){
    for(i=0;i<6;i++)server_mac[i]=REG8(ETH_RXBUF+22+i);
    pop();return 1;
   }
   pop();
  }
 }
 return 0;
}

/* Pick the centre of the longest near-perfect run instead of accepting the
 * first lucky ARP reply at an eye edge.  Scores are successful replies out of
 * four attempts. */
static uint8_t eye_pick(const uint8_t *score,uint32_t count,uint8_t best){
 uint32_t i,start=0,len=0,best_start=0,best_len=0;
 uint8_t threshold=(best>=3)?(uint8_t)(best-1):best;
 for(i=0;i<=count;i++){
  if(i<count&&score[i]>=threshold){if(!len)start=i;len++;}
  else{if(len>best_len){best_len=len;best_start=start;}len=0;}
 }
 return rgmii_eye_steps[best_start+(best_len>>1)];
}

static int eye_scan(uint32_t ip,int scan_tx,uint8_t fixed,uint8_t *chosen){
 uint8_t score[sizeof(rgmii_eye_steps)],best=0,tap;uint32_t i,j,settle;
 for(i=0;i<sizeof(rgmii_eye_steps);i++){
  tap=rgmii_eye_steps[i];
  if(scan_tx)rgmii_set_delay(tap,fixed);else rgmii_set_delay(fixed,tap);
  /* IODELAY updates do not require resetting the RGMII IDDR.  Keeping the
   * receive pipeline running also avoids aligning every retransmission with
   * the same marginal sampling phase. */
  REG32(ETH_BASE+16)=4;settle=read_mtime_ticks32();while((uint32_t)(read_mtime_ticks32()-settle)<TIMEBASE_HZ/200u);
  score[i]=0;for(j=0;j<4;j++)score[i]+=(uint8_t)arp_trial(ip);
  if(score[i]>best)best=score[i];
 }
 if(!best)return -1;
 *chosen=eye_pick(score,sizeof(rgmii_eye_steps),best);
 console_puts(scan_tx?"RGMII TX eye=":"RGMII RX eye=");console_dec(*chosen);
 console_puts(" score=");console_dec(best);console_puts("/4\n");
 return 0;
}

static int arp_resolve(uint32_t ip){
 uint8_t calibrated_tx,calibrated_rx,score=0;uint32_t i,settle;
 /* First use the exact delay pair from the board vendor's
  * 2_11_ethernet_test reference design.  Four probes reject a lucky reply
  * at a marginal point without adding a full eye scan to every normal boot. */
 rgmii_set_delay(100,247);REG32(ETH_BASE+16)=4;
 settle=read_mtime_ticks32();while((uint32_t)(read_mtime_ticks32()-settle)<TIMEBASE_HZ/200u);
 for(i=0;i<4;i++)score+=(uint8_t)arp_trial(ip);
 if(score>=3){
  console_puts("RGMII reference delay tx=100 rx=247 score=");console_dec(score);console_puts("/4\n");
  return 0;
 }
 /* If board/cable or implementation placement moves the receive eye, RX
  * must be calibrated first.  Scanning TX while RX cannot validate an ARP
  * reply makes every TX tap look bad and prevents the RX scan entirely. */
 if(!eye_scan(ip,0,100,&calibrated_rx)&&
    !eye_scan(ip,1,calibrated_rx,&calibrated_tx)&&
    !eye_scan(ip,0,calibrated_tx,&calibrated_rx)){
  rgmii_set_delay(calibrated_tx,calibrated_rx);
  score=0;for(i=0;i<4;i++)score+=(uint8_t)arp_trial(ip);
  if(score){console_puts("RGMII delay tx=");console_dec(rgmii_tx_step);console_puts(" rx=");console_dec(rgmii_rx_step);console_puts(" score=");console_dec(score);console_puts("/4\n");return 0;}
 }
 rgmii_set_delay(100,247);
 return -1;
}

static void udp_send(uint16_t sport,uint16_t dport,const uint8_t*data,uint16_t n){uint32_t i;uint16_t total=20+8+n;for(i=0;i<6;i++){tx[i]=server_mac[i];tx[6+i]=my_mac[i];}p16(tx+12,0x0800);tx[14]=0x45;tx[15]=0;p16(tx+16,total);p16(tx+18,ip_id++);p16(tx+20,0);tx[22]=64;tx[23]=17;p16(tx+24,0);p32(tx+26,my_ip);p32(tx+30,server_ip_active);p16(tx+24,ip_sum(tx+14,20));p16(tx+34,sport);p16(tx+36,dport);p16(tx+38,8+n);p16(tx+40,0);for(i=0;i<n;i++)tx[42+i]=data[i];send_frame(42+n);}
static int udp_receive(uint16_t dport,uint16_t *sport,uint32_t *payload,uint32_t *bytes,uint32_t timeout){
 uint32_t t=read_mtime_ticks32();
 while((uint32_t)(read_mtime_ticks32()-t)<timeout){
  if(REG32(ETH_BASE+4)&1){
   uint32_t n=REG32(ETH_BASE+8),l2=14,ip,ihl,u,ul,ip_total;uint16_t et;int fcs_ok=frame_fcs_ok(n);
   if(fcs_ok)n-=4;
   if(n>=14){
    et=r16(12);
    /* Windows does not have to learn a usable neighbour entry from our own
     * ARP request.  Answer its request explicitly so queued TFTP DATA is
     * released even after the host neighbour cache becomes stale. */
    if(et==0x0806&&n>=42&&r16(20)==1&&r32(38)==my_ip){arp_reply_from_rx();pop();send_frame(42);continue;}
    /* Realtek USB adapters may insert an 802.1Q priority tag when VLAN/QoS
     * offload is enabled.  Locate IPv4 after either Ethernet header. */
    if((et==0x8100||et==0x88a8)&&n>=18){et=r16(16);l2=18;}
    ip=l2;
    if(et==0x0800&&n>=ip+28&&(REG8(ETH_RXBUF+ip)&0xf0)==0x40&&REG8(ETH_RXBUF+ip+9)==17){
     ihl=(REG8(ETH_RXBUF+ip)&15)*4;u=ip+ihl;
     ip_total=r16(ip+2);
     /* The private boot link has one client.  The local ephemeral TFTP port
      * is a stronger session key than cached global IP values and remains
      * valid across ARP/VLAN/offload changes. */
     if(ihl>=20&&ip_total>=ihl+8&&ip+ip_total<=n&&r16(u+2)==dport){
      ul=r16(u+4);if(ul>=8&&ul<=ip_total-ihl){
       *sport=r16(u);*payload=u+8;*bytes=ul-8;return 1;
      }
     }
    }
   }
   pop();
  }
 }
 return 0;
}
static void ack(uint16_t local,uint16_t remote,uint16_t block){uint8_t d[4];p16(d,4);p16(d+2,block);udp_send(local,remote,d,4);}
static uint32_t put_dec(uint8_t*r,uint32_t n,uint32_t v){uint32_t d=1000000000u;int started=0;while(d){uint32_t x=v/d;if(x||started||d==1){r[n++]=(uint8_t)('0'+x);started=1;}v%=d;d/=10;}r[n++]=0;return n;}
static int hex_value(uint8_t c){if(c>='0'&&c<='9')return c-'0';if(c>='A'&&c<='F')return c-'A'+10;if(c>='a'&&c<='f')return c-'a'+10;return -1;}
static uint32_t make_rrq(uint8_t*r,const char*name,uint32_t offset,uint16_t block_size){
 uint32_t n=0;
 p16(r,1);n=2;while(*name&&n<240)r[n++]=(uint8_t)*name++;r[n++]=0;
 r[n++]='o';r[n++]='c';r[n++]='t';r[n++]='e';r[n++]='t';r[n++]=0;
 r[n++]='b';r[n++]='l';r[n++]='k';r[n++]='s';r[n++]='i';r[n++]='z';r[n++]='e';r[n++]=0;
 n=put_dec(r,n,block_size);
 r[n++]='o';r[n++]='f';r[n++]='f';r[n++]='s';r[n++]='e';r[n++]='t';r[n++]=0;
 n=put_dec(r,n,offset);
 r[n++]='e';r[n++]='n';r[n++]='c';r[n++]='o';r[n++]='d';r[n++]='i';r[n++]='n';r[n++]='g';r[n++]=0;
 r[n++]='h';r[n++]='e';r[n++]='x';r[n++]='c';r[n++]='r';r[n++]='c';r[n++]=0;
 return n;
}

int tftp_get(uint32_t server_ip,const char*name,uint32_t address,uint32_t limit,uint32_t*outlen){
 uint8_t rrq[300];uint32_t rn=0,total=0,p,n,i,settle;
 uint16_t local=49152,remote=69,sp,expect=1,block,block_size=512;
 const char*file_name=name;
 uint8_t block_size_index=0;
 int retry;
 server_ip_active=server_ip;
 console_puts("ARP ");console_hex(server_ip);console_puts("...\n");
 if(arp_resolve(server_ip)){console_puts("ARP timeout\n");return -2;}
 /* Retain the RX/TX delay pair that passed a complete ARP frame including
  * FCS.  In native 1-Gbit RGMII this measured pair is also the correct DATA
  * sampling point; overriding it with the former 100-Mbit fallback tap made
  * the first long transfer intermittent. */
 /* The vendor reference's RX=247 is excellent for short ARP/OACK frames;
  * long DATA frames have more margin at the measured RX=224 point. */
 rgmii_data_index=0;
 rgmii_set_delay(rgmii_tx_step,rgmii_data_steps[0]);
 settle=read_mtime_ticks32();while((uint32_t)(read_mtime_ticks32()-settle)<TIMEBASE_HZ/200u);

 rn=make_rrq(rrq,file_name,0,block_size);
 console_puts("TFTP RRQ blksize=512...\n");udp_send(local,69,rrq,rn);

 for(retry=0;retry<128;){
  if(!udp_receive(local,&sp,&p,&n,TIMEBASE_HZ/2u)){
   retry++;
   if((retry%8)==0){
    uint8_t abort_packet[5];
    /* Move to another point in the measured RX eye without restarting the
     * IDDR or the MAC.  The vendor reference keeps this path continuously
     * clocked; resetting it during stop-and-wait retransmission can lock all
     * following DATA frames to the same bad phase while short ARPs survive. */
    rgmii_data_index=(uint8_t)((rgmii_data_index+1)%sizeof(rgmii_data_steps));
    rgmii_set_delay(rgmii_tx_step,rgmii_data_steps[rgmii_data_index]);
    p16(abort_packet,5);p16(abort_packet+2,0);abort_packet[4]=0;
    udp_send(local,remote,abort_packet,5);delay_cycles(TIMEBASE_HZ/100u);
    REG32(ETH_BASE+16)=4;delay_cycles(TIMEBASE_HZ/50u);
    block_size_index=(uint8_t)((block_size_index+1)%(sizeof(tftp_block_sizes)/sizeof(tftp_block_sizes[0])));
    block_size=tftp_block_sizes[block_size_index];
    console_puts("\nTFTP recovery ARP...\n");
    delay_cycles(TIMEBASE_HZ*5u);
    if(arp_resolve(server_ip))return -2;
    rgmii_set_delay(rgmii_tx_step,rgmii_data_steps[rgmii_data_index]);
    console_puts("RGMII recovery rx=");console_dec(rgmii_rx_step);console_putc('\n');
    /* Rewind a few already verified bytes before resuming.  They are safely
     * overwritten with identical file data, while the formerly failing byte
     * sequence moves to a different Ethernet/TFTP frame position. */
    if(total){uint32_t rewind=1u+(rgmii_data_index&7u);total=(total>rewind)?total-rewind:0;}
    expect=1;remote=69;retry=0;rn=make_rrq(rrq,file_name,total,block_size);
    console_puts("\nTFTP resume offset=");console_dec(total);console_puts(" blksize=");console_dec(block_size);console_putc('\n');
    udp_send(local,69,rrq,rn);continue;
   }
   /* Do not reset the IDDR while the server may already be retransmitting.
    * That phase-locked race made one lost DATA frame permanently unrecoverable.
    * Clear diagnostics only; the MAC naturally returns to frame-idle at DV low. */
   REG32(ETH_BASE+16)=4;
   settle=read_mtime_ticks32();while((uint32_t)(read_mtime_ticks32()-settle)<TIMEBASE_HZ/200u);
   console_putc('~');
   if(expect==1)udp_send(local,69,rrq,rn);else ack(local,remote,(uint16_t)(expect-1));
   continue;
  }
  if(n>=2){
   uint16_t op=r16(p);
   if(op==6&&expect==1){
    remote=sp;pop();ack(local,remote,0);retry=0;continue;
   }
   if(n>=4){
    block=r16(p+2);
    if(op==3){
     if(expect==1)remote=sp;
     if(sp==remote&&block==expect){
      uint32_t wire_data=n-4,data=(wire_data>=8)?((wire_data-8)>>1):0;
      uint32_t wanted=0,adler_a=1,adler_b=0,value;
      int hi,lo,valid=(wire_data>=8)&&!((wire_data-8)&1u);
      for(i=0;i<wire_data&&valid;i++)if(hex_value(REG8(ETH_RXBUF+p+4+i))<0)valid=0;
      for(i=0;i<8&&valid;i++)wanted=(wanted<<4)|(uint32_t)hex_value(REG8(ETH_RXBUF+p+4+i));
      for(i=0;i<data&&valid;i++){
       hi=hex_value(REG8(ETH_RXBUF+p+12+(i<<1)));lo=hex_value(REG8(ETH_RXBUF+p+13+(i<<1)));value=(uint32_t)((hi<<4)|lo);
       adler_a+=value;if(adler_a>=65521u)adler_a-=65521u;adler_b+=adler_a;if(adler_b>=65521u)adler_b-=65521u;
      }
      if(valid&&wanted!=((adler_b<<16)|adler_a))valid=0;
      if(!valid){pop();continue;}
      if(total+data>limit){pop();return -3;}
      for(i=0;i<data;i++){hi=hex_value(REG8(ETH_RXBUF+p+12+(i<<1)));lo=hex_value(REG8(ETH_RXBUF+p+13+(i<<1)));REG8(address+total+i)=(uint8_t)((hi<<4)|lo);}
      total+=data;pop();ack(local,remote,block);expect++;retry=0;console_putc('.');
      if(wire_data<block_size){console_puts("\nRGMII stable rx=");console_dec(rgmii_rx_step);console_putc('\n');*outlen=total;return 0;}
      if((uint16_t)(expect-1)==2048){
       /* The bundled server ends each 1 MiB transfer session here.  Starting
        * a fresh RRQ/source port avoids the long-lived Windows UDP/USB-NIC
        * stall while preserving the already downloaded DDR prefix. */
       delay_cycles(TIMEBASE_HZ/100u);
       REG32(ETH_BASE+16)=4;delay_cycles(TIMEBASE_HZ/50u);
       rgmii_set_delay(rgmii_tx_step,rgmii_data_steps[rgmii_data_index]);
       expect=1;remote=69;rn=make_rrq(rrq,file_name,total,block_size);
       console_putc('|');udp_send(local,69,rrq,rn);
      }
      continue;
     }
     if(sp==remote&&block==(uint16_t)(expect-1)){pop();ack(local,remote,block);continue;}
    }else if(op==5){console_puts("\nTFTP error\n");pop();return -4;}
   }
  }
  pop();
 }
 return -5;
}

uint32_t parse_ip(const char*s,int*ok){uint32_t ip=0,v;int part;*ok=0;for(part=0;part<4;part++){v=0;if(*s<'0'||*s>'9')return 0;while(*s>='0'&&*s<='9'){v=v*10+(*s++-'0');if(v>255)return 0;}ip=(ip<<8)|v;if(part<3){if(*s++!='.')return 0;}else if(*s)return 0;}*ok=1;return ip;}

/* Camera wire protocol v1.  All header integers are network byte order;
 * RGB565 pixels remain little endian in the DATA payload.  The per-packet
 * CRC covers header bytes 0..35 followed by payload, excluding bytes 36..39.
 * Stop-and-wait makes duplicate/lost packets unambiguous and keeps BRAM use
 * below one Ethernet MTU.  TFTP's ports and state are untouched. */
#define CAM_PORT_BOARD 49061u
#define CAM_PORT_PC    49062u
#define CAM_BYTES      0x001c2000u
#define CAM_CHUNK      1024u
static uint8_t cam_packet[40u + CAM_CHUNK];
static uint8_t cam_reply[40];

static uint32_t cam_get32(const uint8_t *p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint16_t cam_get16(const uint8_t *p){return ((uint16_t)p[0]<<8)|p[1];}
static void cam_make(uint8_t type,uint32_t session,uint32_t frame,
                     uint32_t seq,uint32_t frame_crc,
                     const uint8_t *data,uint16_t length){
 uint32_t i,crc;
 cam_packet[0]='C';cam_packet[1]='A';cam_packet[2]='M';cam_packet[3]='P';
 cam_packet[4]=1;cam_packet[5]=type;p16(cam_packet+6,40);
 p32(cam_packet+8,session);p32(cam_packet+12,frame);p32(cam_packet+16,seq);
 p32(cam_packet+20,CAM_BYTES);p16(cam_packet+24,1280);p16(cam_packet+26,720);
 p16(cam_packet+28,1);p16(cam_packet+30,length);p32(cam_packet+32,frame_crc);
 for(i=0;i<length;i++)cam_packet[40+i]=data[i];
 crc=crc32_update(0xffffffffu,cam_packet,36);
 crc=crc32_update(crc,cam_packet+40,length)^0xffffffffu;
 p32(cam_packet+36,crc);
}

/* 0: timed out, 1: expected reply, 2: Esc, -1: peer error. */
static int cam_wait(uint8_t expected,uint32_t session,uint32_t frame,
                    uint32_t seq,uint32_t frame_crc,uint32_t timeout){
 uint32_t start=read_mtime_ticks32();
 while((uint32_t)(read_mtime_ticks32()-start)<timeout){
  uint32_t n,l2=14,ip,ihl,u,ul,j,crc;uint16_t et;
  int key=console_getc_timeout(1u);
  if(key==0x1b)return 2;
  if(key==' ')console_puts("Camera busy; one photo at a time.\n");
  if(!(REG32(ETH_BASE+4)&1))continue;
  n=REG32(ETH_BASE+8);
  if(!frame_fcs_ok(n)){pop();continue;}
  n-=4;
  if(n<42){pop();continue;}
  et=r16(12);
  if(et==0x0806&&r16(20)==1&&r32(38)==my_ip){arp_reply_from_rx();pop();send_frame(42);continue;}
  if((et==0x8100||et==0x88a8)&&n>=18){et=r16(16);l2=18;}
  ip=l2;ihl=(REG8(ETH_RXBUF+ip)&15u)*4u;u=ip+ihl;
  if(et!=0x0800||n<u+8||ihl<20||REG8(ETH_RXBUF+ip+9)!=17||
     r32(ip+12)!=server_ip_active||r32(ip+16)!=my_ip||
     r16(u+2)!=CAM_PORT_BOARD||r16(u)!=CAM_PORT_PC){pop();continue;}
  ul=r16(u+4);
  if(ul!=48||u+ul>n){pop();continue;}
  for(j=0;j<40;j++)cam_reply[j]=REG8(ETH_RXBUF+u+8+j);
  pop();
  crc=crc32_update(0xffffffffu,cam_reply,36)^0xffffffffu;
  if(cam_reply[0]!='C'||cam_reply[1]!='A'||cam_reply[2]!='M'||cam_reply[3]!='P'||
     cam_reply[4]!=1||cam_get16(cam_reply+6)!=40||
     cam_get32(cam_reply+8)!=session||cam_get32(cam_reply+12)!=frame||
     cam_get32(cam_reply+16)!=seq||cam_get32(cam_reply+20)!=CAM_BYTES||
     cam_get16(cam_reply+24)!=1280||cam_get16(cam_reply+26)!=720||
     cam_get16(cam_reply+28)!=1||cam_get16(cam_reply+30)!=0||
     cam_get32(cam_reply+32)!=frame_crc||cam_get32(cam_reply+36)!=crc)continue;
  if(cam_reply[5]==0x84)return -1;
  if(cam_reply[5]==expected)return 1;
 }
 return 0;
}

static void cam_cancel(uint32_t session,uint32_t frame,uint32_t crc){
 uint32_t i;
 cam_make(4,session,frame,0,crc,0,0);
 for(i=0;i<3;i++)udp_send(CAM_PORT_BOARD,CAM_PORT_PC,cam_packet,40);
}

int camera_transfer(uint32_t frame,const uint8_t *pixels,uint32_t frame_crc){
 uint32_t session=read_mtime_ticks32()^frame^0x43414d50u,seq,off;
 uint16_t length;
 int r,attempt;
 server_ip_active=0xc0a80102u;
 rgmii_set_delay(100,247);
 REG32(ETH_BASE+16)=4;
 for(attempt=0;attempt<4;attempt++){
  int key=console_getc_timeout(1u),found;
  if(key==0x1b)return 1;
  if(key==' ')console_puts("Camera busy; one photo at a time.\n");
  found=arp_trial(server_ip_active);
  key=console_getc_timeout(1u);
  if(key==0x1b)return 1;
  if(key==' ')console_puts("Camera busy; one photo at a time.\n");
  if(found)break;
 }
 if(attempt==4){console_puts("Camera receiver ARP timeout.\n");return -1;}
 /* The measured data eye has better margin for full Ethernet frames. */
 rgmii_set_delay(100,224);
 cam_make(1,session,frame,0,frame_crc,0,0);
 for(attempt=0;attempt<5;attempt++){
  udp_send(CAM_PORT_BOARD,CAM_PORT_PC,cam_packet,40);
  r=cam_wait(0x81,session,frame,0,frame_crc,TIMEBASE_HZ/3u);
  if(r)break;
 }
 if(r!=1){if(r==2)cam_cancel(session,frame,frame_crc);return r==2?1:-1;}
 for(seq=0,off=0;off<CAM_BYTES;seq++,off+=length){
  length=(uint16_t)((CAM_BYTES-off)>CAM_CHUNK?CAM_CHUNK:(CAM_BYTES-off));
  cam_make(2,session,frame,seq,frame_crc,pixels+off,length);
  for(attempt=0;attempt<5;attempt++){
   udp_send(CAM_PORT_BOARD,CAM_PORT_PC,cam_packet,(uint16_t)(40u+length));
   r=cam_wait(0x82,session,frame,seq,frame_crc,TIMEBASE_HZ/3u);
   if(r)break;
  }
  if(r!=1){cam_cancel(session,frame,frame_crc);return r==2?1:-1;}
 }
 cam_make(3,session,frame,seq,frame_crc,0,0);
 for(attempt=0;attempt<15;attempt++){
  udp_send(CAM_PORT_BOARD,CAM_PORT_PC,cam_packet,40);
  r=cam_wait(0x83,session,frame,seq,frame_crc,TIMEBASE_HZ*2u);
  if(r)break;
 }
 if(r!=1){cam_cancel(session,frame,frame_crc);return r==2?1:-1;}
 return 0;
}
