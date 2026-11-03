`timescale 1ns/1ps
module tb_camera_capture_mode;
    reg sys_clk=0,ddr_clk=0,resetn=0;
    reg requested_enable=0,background_request=0,frame_valid=0;
    reg gui_enable=1,gui_buffer=0,camera_buffer=1;
    reg session_idle=1,writer_idle=1;
    reg enable_d1=0,enable_d2=0;
    wire effective_enable,background_active_ddr,background_active_sys,preview;
    wire dma_enable,dma_buffer;
    integer i;
    always #7 sys_clk=~sys_clk;
    always #3 ddr_clk=~ddr_clk;
    always @(posedge ddr_clk or negedge resetn)
        if(!resetn)begin enable_d1<=0;enable_d2<=0;end
        else begin enable_d1<=effective_enable;enable_d2<=enable_d1;end
    camera_capture_mode dut(
        .sys_clk(sys_clk),.sys_resetn(resetn),.ddr_clk(ddr_clk),.ddr_resetn(resetn),
        .requested_enable(requested_enable),.background_request(background_request),
        .frame_valid_sys(frame_valid),.gui_enable_sys(gui_enable),.gui_buffer_sys(gui_buffer),
        .camera_buffer_sys(camera_buffer),.session_idle_ddr(session_idle),
        .writer_idle_ddr(writer_idle),.control_enable_ddr(enable_d2),
        .effective_enable_sys(effective_enable),.background_active_ddr(background_active_ddr),
        .background_active_sys(background_active_sys),.camera_preview_sys(preview),
        .dma_enable_sys(dma_enable),.dma_buffer_sys(dma_buffer));
    initial begin
        #100000;$fatal(1,"capture mode timeout");
    end
    initial begin
        repeat(3)@(posedge sys_clk);resetn=1;
        @(negedge sys_clk);requested_enable=1;frame_valid=1;
        repeat(6)@(posedge sys_clk);#1;
        if(!effective_enable || !preview || !dma_enable || !dma_buffer)
            $fatal(1,"default legacy preview changed");
        session_idle=0;writer_idle=0;
        @(negedge sys_clk);background_request=1;
        #1;if(effective_enable)$fatal(1,"new mode enabled before DDR ack");
        repeat(8)@(posedge sys_clk);#1;
        if(background_active_ddr || background_active_sys || effective_enable)
            $fatal(1,"mode changed during an outstanding DDR write");
        writer_idle=1;session_idle=1;
        repeat(10)@(posedge sys_clk);#1;
        if(!background_active_ddr || !background_active_sys || !effective_enable || preview)
            $fatal(1,"background mode handshake failed");
        session_idle=0;writer_idle=0;
        for(i=0;i<8;i=i+1)begin
            @(negedge sys_clk);camera_buffer=~camera_buffer;gui_buffer=~gui_buffer;
            #1;if(!dma_enable || dma_buffer!==gui_buffer || preview)
                $fatal(1,"background capture switched HDMI away from GUI");
        end
        @(negedge sys_clk);requested_enable=0;
        repeat(6)@(posedge sys_clk);#1;
        if(!dma_enable || dma_buffer!==gui_buffer || preview)
            $fatal(1,"capture stop blanked the GUI");
        background_request=0;
        repeat(6)@(posedge sys_clk);#1;
        if(!background_active_ddr)$fatal(1,"mode released before writer drain");
        writer_idle=1;session_idle=1;
        repeat(10)@(posedge sys_clk);#1;
        if(background_active_sys || background_active_ddr)$fatal(1,"legacy mode did not recover");
        requested_enable=1;
        repeat(5)@(posedge sys_clk);#1;
        if(!preview || dma_buffer!==camera_buffer)$fatal(1,"legacy preview did not recover");
        $display("CAMERA_CAPTURE_MODE_PASS handshake no-preview drain legacy-recovery");$finish;
    end
endmodule
