`timescale 1ns/1ps
// Serial I2S source -> synchronous capture RAM -> MMIO peek/pop.
module tb_audio_capture_chain;
    reg clk=0,resetn=0,wr=0,mic_sd=0;
    reg [31:0] addr=0,wdata=0;
    reg [3:0] wstrb=0;
    wire [31:0] rdata,count,underflows,overflows;
    wire [23:0] latest,head;
    wire [15:0] play_data;
    wire [4:0] play_level;
    wire [2:0] capture_level;
    wire bclk,ws,amp,play_write,play_full,clear,pop,empty,full,hit;
    integer serial_index=0,source_frame=0;
    reg [23:0] serial_word;
    integer i;
    reg [31:0] saved_count,saved_drops;
    always #5 clk=~clk;
    i2s_audio_duplex #(.ADD_STEP(1),.WRAP_POINT(1),.MIC_FIFO_ADDR_BITS(2)) audio(
        .clk(clk),.resetn(resetn),.counter_clear(clear),.mic_sd(mic_sd),
        .i2s_bclk(bclk),.i2s_ws(ws),.amp_sd(amp),
        .sample_write(play_write),.sample_data(play_data),.fifo_full(play_full),
        .fifo_level(play_level),.microphone_sample(latest),.microphone_count(count),
        .playback_underflows(underflows),.microphone_read(pop),
        .microphone_fifo_data(head),.microphone_fifo_empty(empty),
        .microphone_fifo_full(full),.microphone_fifo_level(capture_level),
        .microphone_overflows(overflows));
    audio_mmio regs(.clk(clk),.resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),
        .wstrb(wstrb),.rdata(rdata),.hit(hit),.sample_write(play_write),
        .sample_data(play_data),.fifo_full(play_full),.fifo_level(play_level),
        .microphone_sample(latest),.microphone_count(count),
        .playback_underflows(underflows),.counter_clear(clear),.microphone_read(pop),
        .microphone_fifo_data(head),.microphone_fifo_empty(empty),
        .microphone_fifo_full(full),.microphone_fifo_level({7'b0,capture_level}),
        .microphone_overflows(overflows));
    // Independent transmitter: one 24-bit left-slot sample per stereo frame.
    always @(posedge bclk) if(resetn) begin
        if(serial_index==63) begin serial_index=0;source_frame=source_frame+1;end
        else serial_index=serial_index+1;
    end
    always @(negedge bclk) begin
        serial_word=24'h800100+source_frame*256;
        if(resetn&&serial_index>=1&&serial_index<=24)
            mic_sd=serial_word[24-serial_index];
        else mic_sd=0;
    end
    task control;
        input [31:0] value;
        begin
            @(negedge clk);addr=32'h1fe00608;wdata=value;wstrb=1;wr=1;
            @(negedge clk);wr=0;
            repeat(2)@(negedge clk);
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);resetn=1;
        wait(count==4);@(negedge clk);
        if(capture_level!==4||!full||overflows!==0)$fatal(1,"capture fill/count");
        saved_count=count;
        for(i=0;i<4;i=i+1)begin
            addr=32'h1fe00620;#1;
            if(rdata!==(32'h00800100+i*256))$fatal(1,"serial sample order %0d: %h",i,rdata);
            // Reading head is nondestructive; only CONTROL.POP consumes it.
            repeat(2)@(negedge clk);
            if(capture_level!==(4-i))$fatal(1,"peek changed level");
            control(2);
        end
        addr=32'h1fe00624;#1;
        if(rdata!==1||count!==saved_count)$fatal(1,"empty FIFO or mic counter");
        wait(count==10);@(negedge clk);
        if(capture_level!==4||overflows!==2)$fatal(1,"capture overflow/drop-newest");
        saved_drops=overflows;
        addr=32'h1fe00620;#1;
        if(rdata!==32'h00800500)$fatal(1,"overflow replaced oldest sample");
        control(3); // clear and pop together: clear dominates in capture FIFO.
        if(capture_level!==0||count!==0||overflows!==0)$fatal(1,"clear did not reset capture");
        wait(count==1);@(negedge clk);
        if(capture_level!==1||overflows!==0)$fatal(1,"capture failed after clear");
        $display("AUDIO_CAPTURE_CHAIN_PASS prior_drops=%0d",saved_drops);$finish;
    end
    initial begin #100000;$fatal(1,"audio capture chain timeout");end
endmodule
