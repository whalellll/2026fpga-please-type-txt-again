`timescale 1ns/1ps
module tb_gui1080_scanout;
    reg pix_clk=0, ddr_clk=0, pix_resetn=0, ddr_resetn=0, ddr_init_done=0;
    always #3.367003367 pix_clk=~pix_clk;
    always #4 ddr_clk=~ddr_clk;
    reg sys_enable=1, sys_requested_buffer=0, sys_clear_underflow_toggle=0;
    reg sys_camera_mode=0;
    wire [27:0] fb_araddr;
    wire [3:0] fb_arid,fb_arlen;
    wire fb_arvalid,fb_urgent,dma_busy_ddr,dma_error_ddr;
    wire fb_arready,fb_rvalid,fb_rlast;
    wire [3:0] fb_rid;
    wire [255:0] fb_rdata;
    wire active_enable_pix,active_buffer_pix,underflow_pix;
    wire [31:0] frame_count_pix,underflow_count_pix;
    wire vs_out,hs_out,de_out;
    wire [7:0] r_out,g_out,b_out;
    video_fb_dma #(.SUPPORT_CAMERA(1),.FB0_BASE(32'h1b800000),.FB1_BASE(32'h1bc00000),
        .H_ACT(1920),.H_FP(88),.H_SYNC(44),.H_BP(148),
        .V_ACT(1080),.V_FP(4),.V_SYNC(5),.V_BP(36)) dut(.*);

    wire [27:0] m_araddr;
    wire [3:0] m_arid,m_arlen;
    wire m_arvalid;
    reg m_arready=0,m_rvalid=0,m_rlast=0;
    reg [3:0] m_rid=0,response_id=0;
    reg [255:0] m_rdata=0;
    wire bridge_ready,bridge_rvalid,bridge_rlast;
    integer bridge_bursts=0;
    ddr_native_read_arbiter arb(
        .clk(ddr_clk),.resetn(ddr_resetn),
        .s0_araddr(28'h6c00000),.s0_aruser_ap(1'b0),.s0_arid(4'd2),
        .s0_arlen(4'd15),.s0_arvalid(ddr_init_done),.s0_arready(bridge_ready),
        .s0_rvalid(bridge_rvalid),.s0_rlast(bridge_rlast),
        .s1_araddr(fb_araddr),.s1_arid(fb_arid),.s1_arlen(fb_arlen),
        .s1_arvalid(fb_arvalid),.s1_urgent(fb_urgent),.s1_arready(fb_arready),
        .s1_rdata(fb_rdata),.s1_rid(fb_rid),.s1_rlast(fb_rlast),.s1_rvalid(fb_rvalid),
        .m_araddr(m_araddr),.m_arid(m_arid),.m_arlen(m_arlen),.m_arvalid(m_arvalid),
        .m_arready(m_arready),.m_rdata(m_rdata),.m_rid(m_rid),
        .m_rlast(m_rlast),.m_rvalid(m_rvalid));

    integer cycles=0,beat=0,length=0,delay_count=0,ar_count=0;
    integer lane,offset,line,pixel_x,read_width,read_bank;
    integer seen_high_line=0,seen_fb1=0,seen_camera=0;
    reg [31:0] burst_addr;
    reg busy=0,stall_response=0;
    reg [15:0] pixel;
    always @(posedge ddr_clk) begin
        cycles<=cycles+1;
        m_arready<=!busy && cycles%11!=0 && !stall_response;
        m_rvalid<=0; m_rlast<=0;
        if (m_arvalid && m_arready) begin
            if (busy) $fatal(1,"request ownership");
            burst_addr=m_araddr*4;
            response_id=m_arid;
            if (m_arid==2) begin
                if(burst_addr!=32'h1b000000) $fatal(1,"bridge address corrupted");
                offset=0;read_width=1920;read_bank=0;bridge_bursts=bridge_bursts+1;
            end else if(m_arid!=14) $fatal(1,"unknown request owner");
            else if (burst_addr>=32'h1bc00000 && burst_addr<32'h1bff4800) begin
                offset=burst_addr-32'h1bc00000; read_width=1920; read_bank=1; seen_fb1=1;
            end else if (burst_addr>=32'h1b800000 && burst_addr<32'h1bbf4800) begin
                offset=burst_addr-32'h1b800000; read_width=1920; read_bank=0;
            end else if (burst_addr>=32'h1b200000 && burst_addr<32'h1b3c2000) begin
                offset=burst_addr-32'h1b200000; read_width=1280; read_bank=0; seen_camera=1;
            end else $fatal(1,"DMA outside framebuffer aperture: %h",burst_addr);
            if (burst_addr[11:0]+(m_arlen+1)*32>4096) $fatal(1,"4K burst crossing");
            if (m_arid==14 && m_arlen!=(read_width==1920 ? 7 : 15)) $fatal(1,"burst length");
            line=offset/(read_width*2);
            if (line>=1024) seen_high_line=1;
            if (offset%(read_width*2)+(m_arlen+1)*32>read_width*2) $fatal(1,"row overread");
            length=m_arlen+1; beat=0; busy=1; delay_count=8+cycles%8;
            if(m_arid==14) ar_count=ar_count+1;
        end else if (busy && !stall_response) begin
            if (delay_count>0) delay_count=delay_count-1;
            else if (cycles%7!=0) begin
                for (lane=0;lane<16;lane=lane+1) begin
                    pixel_x=(offset%(read_width*2))/2+beat*16+lane;
                    pixel=((line%32)<<11)|((pixel_x%64)<<5)|((line+pixel_x+read_bank*8)%32);
                    m_rdata[lane*16+:16]<=pixel;
                end
                m_rid<=response_id; m_rvalid<=1; m_rlast<=beat==length-1;
                if (beat==length-1) busy=0;
                else beat=beat+1;
            end
        end
    end

    integer x=0,y=0,checked_frames=0,checked_pixels=0;
    integer source_x,source_y;
    reg previous_de=0,previous_vs=0,frame_started=0,expected_camera=0,expected_bank=0;
    reg [15:0] expected_pixel;
    reg [7:0] expected_r,expected_g,expected_b;
    always @(negedge pix_clk) if(pix_resetn) begin
        if(vs_out && !previous_vs) begin
            if(frame_started) begin
                if(y!=1080) $fatal(1,"active height=%0d",y);
                checked_frames=checked_frames+1;
            end
            frame_started=active_enable_pix;
            expected_camera=sys_camera_mode;
            expected_bank=sys_requested_buffer;
            x=0;y=0;
        end
        if(de_out && frame_started) begin
            source_x=expected_camera ? x-320 : x;
            source_y=expected_camera ? y-180 : y;
            expected_pixel=0;
            if(!expected_camera || (source_x>=0 && source_x<1280 && source_y>=0 && source_y<720))
                expected_pixel=((source_y%32)<<11)|((source_x%64)<<5)|((source_y+source_x+expected_bank*8)%32);
            expected_r={expected_pixel[15:11],expected_pixel[15:13]};
            expected_g={expected_pixel[10:5],expected_pixel[10:9]};
            expected_b={expected_pixel[4:0],expected_pixel[4:2]};
            if(!stall_response && {r_out,g_out,b_out}!=={expected_r,expected_g,expected_b})
                $fatal(1,"pixel mismatch frame=%0d x=%0d y=%0d rgb=%h expected=%h camera=%0d bank=%0d",
                    checked_frames,x,y,{r_out,g_out,b_out},{expected_r,expected_g,expected_b},expected_camera,expected_bank);
            x=x+1; checked_pixels=checked_pixels+1;
        end else if(previous_de && frame_started) begin
            if(x!=1920) $fatal(1,"active width=%0d",x);
            x=0; y=y+1;
        end
        previous_de=de_out; previous_vs=vs_out;
    end

    initial begin
        #100;ddr_resetn=1;pix_resetn=1;ddr_init_done=1;
        wait(active_enable_pix);wait(de_out);repeat(2000) @(posedge pix_clk);
        sys_requested_buffer=1;
        wait(active_buffer_pix);wait(de_out);repeat(2000) @(posedge pix_clk);
        sys_camera_mode=1;sys_requested_buffer=0;
        wait(dut.active_camera_pix);wait(de_out);repeat(2000) @(posedge pix_clk);
        sys_camera_mode=0;
        wait(!dut.active_camera_pix);wait(checked_frames>=4);
        if(underflow_pix || underflow_count_pix || dma_error_ddr) $fatal(1,"scanout error under 125MHz DDR stalls");
        if(!seen_high_line || !seen_fb1 || !seen_camera) $fatal(1,"coverage incomplete");
        if(bridge_bursts<1000) $fatal(1,"CPU/MAC bridge starved");
        stall_response=1;
        wait(underflow_count_pix!=0);
        if(dma_error_ddr) $fatal(1,"stalls misreported as protocol error");
        $display("GUI1080_SCANOUT_PASS frames=%0d pixels=%0d bursts=%0d bridge-bursts=%0d high-y=PASS flip=PASS camera-crop=PASS underrun-detected=PASS",
            checked_frames,checked_pixels,ar_count,bridge_bursts);
        $finish;
    end
    initial begin #120000000; $fatal(1,"1080p scanout timeout"); end
endmodule
