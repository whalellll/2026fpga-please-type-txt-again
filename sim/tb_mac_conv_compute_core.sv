`timescale 1ns / 1ps
module tb_mac_conv_compute_core;
    parameter integer MAX_FIRST_KERNEL_CYCLES = 100000;
    reg abort=0;
    reg clk=0,resetn=0,start=0;
    always #5 clk=~clk;
    wire start_ready,tap_ready,weight_read_en,out_valid,out_last,done,error;
    wire [4:0] weight_read_addr;
    wire [7:0] out_data;
    wire [31:0] cycles;
    reg [8:0] width=0,height=0;
    reg [15:0] channels=0,output_channels=0;
    reg [2:0] kernel=0,padding=0;
    reg [1:0] stride=0;
    reg [5:0] weight_lines=0;
    reg [511:0] quant_bias=0;
    reg [79:0] quant_shift=0;
    wire tap_valid;
    wire [31:0] tap_data;
    wire [8:0] tap_x,tap_y;
    wire [2:0] tap_kx,tap_ky;
    wire [7:0] tap_tile=0;
    reg weight_read_valid=0;
    reg [1023:0] weight_read_data=0;
    wire out_ready;
    reg [31:0] taps[0:323];
    reg [31:0] weight_words[0:1023];
    reg [1023:0] rows[0:31];
    reg [7:0] expected[0:143];
    integer input_index=0,output_index=0,weight_reads=0,tick=0;
    integer expected_taps=0,expected_bytes=0,expected_lines=0;
    integer ow=0,oh=0,active=0;
    integer j;

    mac_conv_compute_core dut (.*);

    assign tap_valid = active && input_index < expected_taps && tick%5 != 1;
    assign tap_data = taps[input_index];
    assign tap_x = (input_index/(kernel*kernel))%ow;
    assign tap_y = (input_index/(kernel*kernel))/ow;
    assign tap_kx = input_index%kernel;
    assign tap_ky = (input_index/kernel)%kernel;
    assign out_ready = tick%7 != 3;
    always @(posedge clk) begin
        if (!resetn) begin
            input_index<=0;output_index<=0;weight_reads<=0;tick<=0;
            weight_read_valid<=0;weight_read_data<=0;
        end else begin
            tick<=tick+1;
            weight_read_valid<=weight_read_en;
            if (weight_read_en) begin
                if (weight_read_addr != weight_reads%expected_lines)
                    $fatal(1,"weight row order got=%0d expected=%0d",
                           weight_read_addr,weight_reads%expected_lines);
                weight_read_data<=rows[weight_read_addr];
                weight_reads<=weight_reads+1;
            end
            if (tap_valid && tap_ready) input_index<=input_index+1;
            if (out_valid && out_ready) begin
                if (output_index>=expected_bytes ||
                    out_data !== expected[output_index] ||
                    out_last != (output_index==expected_bytes-1))
                    $fatal(1,"output mismatch byte=%0d got=%02x expected=%02x last=%b",
                           output_index,out_data,expected[output_index],out_last);
                output_index<=output_index+1;
            end
        end
    end

    task run_case;
        input string name;
        input [8:0] w,h;
        input [15:0] cin,cout;
        input [2:0] k,pad;
        input [1:0] step;
        input integer lines,ntaps,nbytes;
        integer timeout,oc;
        begin
            $readmemh($sformatf("sim/vectors/yolo_compute_%s_taps.hex",name),
                      taps,0,ntaps-1);
            $readmemh($sformatf("sim/vectors/yolo_compute_%s_weights.hex",name),
                      weight_words,0,lines*32-1);
            $readmemh($sformatf("sim/vectors/yolo_compute_%s_expected.hex",name),
                      expected,0,nbytes-1);
            for (j=0;j<32;j=j+1)
                for (integer t=0;t<32;t=t+1)
                    rows[j][t*32 +: 32]=weight_words[j*32+t];
            @(negedge clk);
            if (!start_ready) $fatal(1,"compute core not idle");
            width=w;height=h;channels=cin;output_channels=cout;
            kernel=k;padding=pad;stride=step;weight_lines=lines;
            ow=(w+2*pad-k)/step+1;oh=(h+2*pad-k)/step+1;
            expected_taps=ntaps;expected_bytes=nbytes;expected_lines=lines;
            input_index=0;output_index=0;weight_reads=0;active=1;
            quant_bias=0;quant_shift=0;
            for (oc=0;oc<16;oc=oc+1) begin
                quant_bias[oc*32 +: 32]=oc*13-50;
                quant_shift[oc*5 +: 5]=(oc%4)+2;
            end
            start=1;
            @(negedge clk);start=0;
            timeout=0;
            while (!done && !error && timeout<100000) begin
                @(negedge clk);timeout=timeout+1;
            end
            if (timeout==100000 || error || !done ||
                input_index!=ntaps || output_index!=nbytes ||
                weight_reads!=ow*oh*lines || cycles==0)
                $fatal(1,"compute failed %s taps=%0d/%0d bytes=%0d/%0d reads=%0d/%0d cycles=%0d",
                       name,input_index,ntaps,output_index,nbytes,
                       weight_reads,ow*oh*lines,cycles);
            if (name == "first_kernel" && cycles > MAX_FIRST_KERNEL_CYCLES)
                $fatal(1,"conv array cycle budget exceeded: %0d > %0d",
                       cycles, MAX_FIRST_KERNEL_CYCLES);
            active=0;
            $display("MAC_CONV_COMPUTE_CASE_PASS name=%s taps=%0d rows=%0d bytes=%0d cycles=%0d",
                     name,ntaps,weight_reads,nbytes,cycles);
            @(negedge clk);
        end
    endtask

    task run_extreme_case;
        input string name;
        input [7:0] activation_byte,weight_byte,result_byte;
        integer timeout;
        begin
            for (j=0;j<36;j=j+1) taps[j]={8'b0,activation_byte,activation_byte,activation_byte};
            for (j=0;j<32;j=j+1) rows[j]=0;
            for (j=0;j<27;j=j+1)
                rows[j][31:0]={weight_byte,weight_byte,weight_byte,weight_byte};
            expected[0]=result_byte;
            @(negedge clk);
            if (!start_ready) $fatal(1,"extreme compute core not idle");
            width=6;height=6;channels=3;output_channels=1;
            kernel=6;padding=0;stride=1;weight_lines=27;
            ow=1;oh=1;expected_taps=36;expected_bytes=1;expected_lines=27;
            input_index=0;output_index=0;weight_reads=0;active=1;
            quant_bias=0;quant_shift=0;
            start=1;
            @(negedge clk);start=0;
            timeout=0;
            while (!done && !error && timeout<100000) begin
                @(negedge clk);timeout=timeout+1;
            end
            if (timeout==100000 || error || !done || input_index!=36 ||
                output_index!=1 || weight_reads!=27)
                $fatal(1,"extreme compute failed %s taps=%0d bytes=%0d reads=%0d",
                       name,input_index,output_index,weight_reads);
            active=0;
            $display("MAC_CONV_EXTREME_CASE_PASS name=%s cycles=%0d",name,cycles);
            @(negedge clk);
        end
    endtask

    initial begin
        repeat(4) @(negedge clk);resetn=1;
        run_case("point_tail",2,2,4,5,1,0,1,1,4,20);
        run_case("border",3,3,4,8,3,1,1,9,81,72);
        run_case("first_kernel",7,7,3,16,6,2,2,27,324,144);
        run_extreme_case("positive",8'h80,8'h80,8'h7f);
        run_extreme_case("negative",8'h80,8'h7f,8'h80);
        $display("MAC_CONV_COMPUTE_CORE_PASS");
        $finish;
    end
    initial begin #5000000;$fatal(1,"compute core global timeout");end
endmodule
