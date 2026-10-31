`timescale 1ns / 1ps
module tb_mac_conv_weight_dma;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg load_start=0;
    wire load_start_ready, load_busy, load_done, load_error;
    reg [31:0] weight_src=32'h1000_4000;
    reg [5:0] weight_lines=27;
    reg [63:0] model_id=64'h5555_0000_1234_abcd;
    reg [31:0] generation=1, tile_id=7;
    reg activate=0, compute_idle=1, window_done=0;
    wire activate_ready, active_valid, pending_valid;
    wire [63:0] active_model_id;
    wire [31:0] active_generation, active_tile_id, reuse_count;
    wire [5:0] active_lines;
    reg read_en=0;
    reg [4:0] read_addr=0;
    wire read_valid;
    wire [1023:0] read_data;
    wire mem_req_valid, mem_req_write, mem_req_ready;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    wire mem_rsp_valid, mem_rsp_ready, mem_rsp_last, mem_rsp_error;
    wire [31:0] mem_rsp_rdata;
    wire mem_abort;
    wire [31:0] weight_ddr_bytes, cycles;
    reg rsp_active=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    reg inject_error=0;
    reg hold_req=0, hold_rsp=0;
    integer bursts=0, overlap_reads=0, i, j;
    reg [31:0] expected_word;

    mac_conv_weight_dma #(
        .DDR_BASE(32'h1000_0000), .DDR_BYTES(64*1024),
        .TIMEOUT_CYCLES(100)
    ) dut (.*);

    assign mem_req_ready = !rsp_active && !hold_req;
    assign mem_rsp_valid = rsp_active && !hold_rsp;
    assign mem_rsp_last = rsp_left == 1;
    assign mem_rsp_rdata = ((rsp_addr - 32'h1000_4000)>>2);
    assign mem_rsp_error = inject_error;
    always @(posedge clk) begin
        if (!resetn || mem_abort) begin
            rsp_active <= 0; rsp_left <= 0; rsp_addr <= 0;
        end else if (mem_req_valid && mem_req_ready) begin
            if (mem_req_write || mem_req_len>=8 ||
                (mem_req_addr[11:0]+((mem_req_len+1)<<2))>4096)
                $fatal(1,"invalid weight DMA burst");
            bursts <= bursts+1;
            rsp_active <= 1;
            rsp_addr <= mem_req_addr;
            rsp_left <= mem_req_len+1;
        end else if (mem_rsp_valid && mem_rsp_ready) begin
            if (rsp_left == 1) rsp_active <= 0;
            else begin rsp_addr <= rsp_addr+4; rsp_left <= rsp_left-1; end
        end
    end

    task check_line;
        input integer line;
        input [31:0] base;
        begin
            @(negedge clk); read_en=1; read_addr=line;
            @(posedge clk); #1;
            if (!read_valid) $fatal(1,"missing active line %0d",line);
            for (j=0;j<32;j=j+1) begin
                expected_word=base+line*32+j;
                if (read_data[j*32+:32] !== expected_word)
                    $fatal(1,"weight line=%0d word=%0d got=%h expected=%h",
                           line,j,read_data[j*32+:32],expected_word);
            end
            @(negedge clk); read_en=0;
        end
    endtask
    task run_load;
        input [31:0] base;
        input [31:0] gen;
        integer timeout;
        begin
            @(negedge clk);
            if (!load_start_ready) $fatal(1,"weight DMA start blocked");
            weight_src=base;generation=gen;tile_id=gen+6;
            bursts=0;load_start=1;
            @(negedge clk);load_start=0;
            timeout=0;
            while (!load_done && !load_error && timeout<5000) begin
                @(negedge clk);timeout=timeout+1;
            end
            if (timeout==5000 || load_error || !load_done ||
                weight_ddr_bytes!=3456 || bursts!=108 || cycles==0 ||
                !pending_valid)
                $fatal(1,"weight DMA load failed gen=%0d bytes=%0d bursts=%0d cycles=%0d",
                       gen,weight_ddr_bytes,bursts,cycles);
            $display("MAC_CONV_WEIGHT_DMA_LOAD_PASS gen=%0d bytes=%0d bursts=%0d cycles=%0d",
                     gen,weight_ddr_bytes,bursts,cycles);
        end
    endtask

    initial begin
        repeat(4) @(negedge clk);resetn=1;
        run_load(32'h1000_4000,1);
        @(negedge clk);activate=1;
        @(posedge clk);#1;
        if (!active_valid || active_generation!=1 || active_lines!=27 ||
            active_tile_id!=7 || active_model_id!=model_id)
            $fatal(1,"first weight bank metadata/swap failed");
        @(negedge clk);activate=0;compute_idle=0;
        check_line(0,0);
        check_line(26,0);

        // Read active bank repeatedly while DDR fills the inactive bank.
        fork
            run_load(32'h1000_5000,2);
            begin
                repeat(4) @(negedge clk);
                for (i=0;i<27;i=i+1) begin
                    check_line(i,0);
                    overlap_reads=overlap_reads+1;
                end
            end
        join
        if (overlap_reads!=27 || active_generation!=1)
            $fatal(1,"weight load/read overlap or isolation failed");
        @(negedge clk);window_done=1;
        repeat(3) @(negedge clk);
        window_done=0;
        if (reuse_count<2) $fatal(1,"reuse counter failed");
        compute_idle=1;activate=1;
        @(posedge clk);#1;
        if (active_generation!=2 || active_tile_id!=8 || reuse_count!=0)
            $fatal(1,"second bank atomic swap failed");
        @(negedge clk);activate=0;
        check_line(26,1024);
        // Invalid jobs and failed transfers preserve the current active bank.
        @(negedge clk);weight_lines=0;load_start=1;
        @(negedge clk);
        if (!load_error || mem_req_valid || active_generation!=2)
            $fatal(1,"zero-line weight job not rejected cleanly");
        load_start=0;weight_lines=27;
        @(negedge clk);inject_error=1;load_start=1;
        @(negedge clk);load_start=0;
        wait(load_error);
        @(negedge clk);inject_error=0;
        @(negedge clk);
        if (!load_start_ready || active_generation!=2 || pending_valid)
            $fatal(1,"response error damaged active bank");
        hold_req=1;load_start=1;
        @(negedge clk);load_start=0;
        wait(load_error);
        @(negedge clk);hold_req=0;
        @(negedge clk);
        if (!load_start_ready || active_generation!=2)
            $fatal(1,"request timeout damaged active bank");
        hold_rsp=1;load_start=1;
        @(negedge clk);load_start=0;
        wait(mem_abort && load_error);
        @(negedge clk);hold_rsp=0;
        @(negedge clk);
        if (!load_start_ready || rsp_active || active_generation!=2)
            $fatal(1,"response timeout did not abort cleanly");
        run_load(32'h1000_6000,3);
        @(negedge clk);compute_idle=1;activate=1;
        @(posedge clk);#1;
        if (active_generation!=3 || active_tile_id!=9)
            $fatal(1,"third bank activation failed after errors");
        @(negedge clk);activate=0;
        check_line(26,2048);
        $display("MAC_CONV_WEIGHT_DMA_PASS overlap_reads=%0d",overlap_reads);
        $finish;
    end
    initial begin #200000; $fatal(1,"weight DMA global timeout"); end
endmodule
