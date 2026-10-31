`timescale 1ns / 1ps
module tb_mac_conv_compact_writer;
    reg clk=0,resetn=0,word_valid=0;
    always #5 clk=~clk;
    reg [31:0] word_addr=0,word_data=0;
    reg [3:0] word_strb=0;
    wire word_ready,error,mem_abort;
    wire mem_req_valid,mem_req_write,mem_w_valid,mem_w_last,mem_rsp_ready;
    wire [31:0] mem_req_addr,mem_w_data;
    wire [2:0] mem_req_len;
    wire [3:0] mem_w_strb;
    wire mem_req_ready,mem_w_ready,mem_rsp_valid,mem_rsp_last,mem_rsp_error;
    reg inject_error=0,inject_bad_last=0,hold_rsp=0;
    reg [31:0] memory[0:16383];
    reg [1:0] mem_state=0;
    integer wait_cycles=0,requests=0,write_beats=0,aborts=0;

    mac_conv_compact_writer #(.DDR_BASE(32'h1000_0000),
                              .DDR_BYTES(64*1024),.TIMEOUT_CYCLES(30)) dut (.*);
    assign mem_req_ready=mem_state==0;
    assign mem_w_ready=mem_state==1;
    assign mem_rsp_valid=mem_state==2 && !hold_rsp && wait_cycles>=2;
    assign mem_rsp_last=!inject_bad_last;
    assign mem_rsp_error=inject_error;
    always @(posedge clk) begin
        if (!resetn) begin
            mem_state<=0;wait_cycles<=0;requests<=0;write_beats<=0;aborts<=0;
        end else if (mem_abort) begin
            mem_state<=0;wait_cycles<=0;aborts<=aborts+1;
        end else case (mem_state)
            0: if (mem_req_valid && mem_req_ready) begin
                if (!mem_req_write || mem_req_len!=0 ||
                    mem_req_addr[1:0]!=0 ||
                    mem_req_addr[11:0]+4>4096)
                    $fatal(1,"invalid compact DDR request");
                requests<=requests+1;mem_state<=1;
            end
            1: if (mem_w_valid && mem_w_ready) begin
                if (!mem_w_last || mem_w_strb==0)
                    $fatal(1,"invalid compact DDR data beat");
                memory[(mem_req_addr-32'h1000_0000)>>2]<=mem_w_data;
                write_beats<=write_beats+1;wait_cycles<=0;mem_state<=2;
            end
            2: if (mem_rsp_valid && mem_rsp_ready) begin
                mem_state<=0;wait_cycles<=0;
            end else wait_cycles<=wait_cycles+1;
        endcase
    end

    task send_word;
        input [31:0] addr,data;
        input [3:0] strb;
        input integer expect_error;
        integer timeout;
        begin
            @(negedge clk);word_addr=addr;word_data=data;word_strb=strb;
            word_valid=1;timeout=0;
            while (!word_ready && !error && timeout<100) begin
                @(negedge clk);timeout=timeout+1;
            end
            if (timeout==100 || (expect_error ? !error : !word_ready))
                $fatal(1,"compact write failed addr=%h ready=%b error=%b",
                       addr,word_ready,error);
            @(negedge clk);word_valid=0;
            @(negedge clk);
        end
    endtask

    initial begin
        repeat(4) @(negedge clk);resetn=1;
        send_word(32'h1000_0ffc,32'h0302_0100,4'hf,0);
        send_word(32'h1000_1000,32'h0000_0004,4'h1,0);
        if (requests!=2 || write_beats!=2 ||
            memory[1023]!=32'h0302_0100 || memory[1024]!=4)
            $fatal(1,"compact boundary writes incorrect");
        inject_error=1;
        send_word(32'h1000_2000,32'h1111_1111,4'hf,1);
        inject_error=0;
        inject_bad_last=1;
        send_word(32'h1000_200c,32'h5555_5555,4'hf,1);
        inject_bad_last=0;
        hold_rsp=1;
        fork
            send_word(32'h1000_2004,32'h2222_2222,4'hf,1);
            begin
                wait(mem_rsp_ready);
                repeat(29) @(posedge clk);
                #1;
                if (error || mem_abort)
                    $fatal(1,"compact response timed out before 30 cycles");
                @(posedge clk);
                #1;
                if (!error || !mem_abort)
                    $fatal(1,"compact response did not abort on cycle 30");
            end
        join
        hold_rsp=0;
        if (aborts!=2 || mem_state!=0)
            $fatal(1,"write timeout did not abort memory ownership aborts=%0d state=%0d",
                   aborts,mem_state);
        send_word(32'h1000_2008,32'h3333_3333,4'hf,0);
        send_word(32'h1000_ffff,32'h4444_4444,4'hf,1);
        $display("MAC_CONV_COMPACT_WRITER_PASS requests=%0d beats=%0d aborts=%0d",
                 requests,write_beats,aborts);
        $finish;
    end
    initial begin #100000;$fatal(1,"compact writer global timeout");end
endmodule
