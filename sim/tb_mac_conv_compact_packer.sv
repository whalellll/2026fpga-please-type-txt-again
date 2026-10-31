`timescale 1ns / 1ps
module tb_mac_conv_compact_packer;
    reg abort=0;
    reg clk=0,resetn=0,start=0;
    always #5 clk=~clk;
    wire start_ready,byte_ready,word_valid,done,error;
    reg [31:0] base_addr=32'h1b08_0000,total_bytes=0;
    wire byte_valid,byte_last;
    wire [7:0] byte_data;
    wire word_ready;
    wire [31:0] word_addr,word_data,output_ddr_bytes;
    wire [3:0] word_strb;
    reg [7:0] expected[0:143];
    integer byte_index=0,word_index=0,number=0,tick=0,active=0;
    integer i;

    mac_conv_compact_packer dut (.*);
    assign byte_valid=active && byte_index<number && tick%5!=2;
    assign byte_data=expected[byte_index];
    assign byte_last=byte_index==number-1;
    assign word_ready=tick%7==3;
    always @(posedge clk) begin
        if (!resetn) begin
            byte_index<=0;word_index<=0;tick<=0;
        end else begin
            tick<=tick+1;
            if (byte_valid && byte_ready) byte_index<=byte_index+1;
            if (word_valid && word_ready) begin
                if (word_addr!==base_addr+word_index*4)
                    $fatal(1,"compact address mismatch word=%0d addr=%h",word_index,word_addr);
                for (i=0;i<4;i=i+1)
                    if (word_index*4+i<number) begin
                        if (!word_strb[i] ||
                            word_data[i*8 +: 8]!==expected[word_index*4+i])
                            $fatal(1,"compact byte mismatch word=%0d lane=%0d",word_index,i);
                    end else if (word_strb[i])
                        $fatal(1,"compact last strobe includes invalid lane");
                word_index<=word_index+1;
            end
        end
    end

    task run_case;
        input string name;
        input integer bytes_to_send;
        integer timeout;
        begin
            $readmemh($sformatf("sim/vectors/yolo_compute_%s_expected.hex",name),
                      expected,0,name=="point_tail" ? 19 : bytes_to_send-1);
            @(negedge clk);
            if (!start_ready) $fatal(1,"packer not idle");
            total_bytes=bytes_to_send;number=bytes_to_send;
            byte_index=0;word_index=0;active=1;start=1;
            @(negedge clk);start=0;
            timeout=0;
            while (!done && !error && timeout<10000) begin
                @(negedge clk);timeout=timeout+1;
            end
            if (error || !done || timeout==10000 ||
                byte_index!=bytes_to_send ||
                word_index!=(bytes_to_send+3)/4 ||
                output_ddr_bytes!=bytes_to_send)
                $fatal(1,"packer failed %s bytes=%0d words=%0d ddr=%0d",
                       name,byte_index,word_index,output_ddr_bytes);
            active=0;
            $display("MAC_CONV_COMPACT_PACKER_CASE_PASS name=%s bytes=%0d words=%0d",
                     name,bytes_to_send,word_index);
            @(negedge clk);
        end
    endtask

    initial begin
        repeat(4) @(negedge clk);resetn=1;
        run_case("point_tail",20);
        run_case("point_tail",5);
        run_case("border",72);
        run_case("first_kernel",144);
        $display("MAC_CONV_COMPACT_PACKER_PASS");$finish;
    end
    initial begin #1000000;$fatal(1,"packer global timeout");end
endmodule
