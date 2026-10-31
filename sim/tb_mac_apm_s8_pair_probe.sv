`timescale 1ns/1ps
module probe_global_reset; wire GRSNET=1'b1; endmodule
module tb_mac_apm_s8_pair_probe;
    reg clk=0,resetn=0,en=0,pack_mode=0;
    reg signed [17:0] activation=0,weight_lo=0;
    reg signed [7:0] weight_hi=0;
    wire signed [15:0] product_lo,product_hi;
    wire signed [47:0] raw_product;
    wire valid;
    integer packed_cases=0,raw_cases=0,hold_cases=0;
    integer a,b,c,i;
    integer edge8[0:4];
    integer edge16[0:6];
    integer edge18[0:6];
    reg [31:0] random_state=32'h82a73519;
    probe_global_reset GRS_INST();
    always #5 clk=~clk;
    mac_apm_s8_pair_probe dut(.clk(clk),.resetn(resetn),.en(en),.pack_mode(pack_mode),
        .activation(activation),.weight_lo(weight_lo),.weight_hi(weight_hi),
        .product_lo(product_lo),.product_hi(product_hi),.raw_product(raw_product),.valid(valid));

    // Former random_word function as a task with an output operand.
    reg [31:0] random_word_result;
    task random_word;
        begin
            random_word_result=random_state;
            random_word_result=random_word_result^(random_word_result<<13);
            random_word_result=random_word_result^(random_word_result>>17);
            random_word_result=random_word_result^(random_word_result<<5);
            random_state=random_word_result;
        end
    endtask


    task automatic check(input bit packed_mode,input integer x,input integer lo,input integer hi);
        longint signed expected;
        begin
            @(negedge clk);en=1;pack_mode=packed_mode;activation=x;weight_lo=lo;weight_hi=hi;
            @(posedge clk);#1;
            if(valid!==1) $fatal(1,"APM pair must produce a result after one input clock");
            if(packed_mode) begin
                if($signed(product_lo)!==x*lo || $signed(product_hi)!==x*hi)
                    $fatal(1,"paired product mismatch x=%0d lo=%0d hi=%0d got=%0d,%0d expected=%0d,%0d",
                        x,lo,hi,product_lo,product_hi,x*lo,x*hi);
                packed_cases=packed_cases+1;
            end else begin
                expected=longint'(x)*longint'(lo);
                if($signed(raw_product)!==expected || product_hi!==0)
                    $fatal(1,"wide product mismatch x=%0d w=%0d got=%0d expected=%0d",x,lo,raw_product,expected);
                raw_cases=raw_cases+1;
            end
        end
    endtask

    task automatic check_hold;
        reg [15:0] p0,p1;
        reg [47:0] pr;
        begin
            p0=product_lo;p1=product_hi;pr=raw_product;
            @(negedge clk);en=0;pack_mode=~pack_mode;activation=131071;weight_lo=-131072;weight_hi=-128;
            @(posedge clk);#1;
            if(valid!==0 || product_lo!==p0 || product_hi!==p1 || raw_product!==pr)
                $fatal(1,"disabled APM inputs and correction must remain aligned");
            hold_cases=hold_cases+1;
        end
    endtask

    initial begin
        edge8[0]=-128;edge8[1]=-1;edge8[2]=0;edge8[3]=1;edge8[4]=127;
        edge16[0]=-32768;edge16[1]=-32767;edge16[2]=-1;edge16[3]=0;
        edge16[4]=1;edge16[5]=32766;edge16[6]=32767;
        edge18[0]=-131072;edge18[1]=-65536;edge18[2]=-1;edge18[3]=0;
        edge18[4]=1;edge18[5]=65535;edge18[6]=131071;
        repeat(3) @(posedge clk);@(negedge clk);resetn=1;
        for(a=-128;a<=127;a=a+1)
            for(b=-128;b<=127;b=b+1) begin
                check(1,a,b,((a+b)&255)-128);
                check(1,a,((a-b)&255)-128,b);
            end
        for(a=-128;a<=127;a=a+1)
            for(b=-128;b<=127;b=b+1)
                for(c=0;c<5;c=c+1) check(1,edge8[c],a,b);
        for(i=0;i<20000;i=i+1) begin
            random_word();a=(random_word_result&255)-128;
            random_word();b=(random_word_result&255)-128;
            random_word();c=(random_word_result&255)-128;
            check(1,a,b,c);
            if(i%257==0) check_hold();
            if(i%1000==0) check(0,-32768,32767,0);
        end
        for(a=0;a<7;a=a+1)
            for(b=0;b<7;b=b+1) check(0,edge16[a],edge16[b],0);
        for(a=0;a<5;a=a+1)
            for(b=0;b<7;b=b+1) check(0,(a==4?255:a*64),edge18[b],0);
        @(negedge clk);en=0;resetn=0;
        repeat(2) @(posedge clk);#1;
        if(valid!==0 || raw_product!==0) $fatal(1,"reset must clear the aligned product");
        if(packed_cases!=478752 || raw_cases!=104 || hold_cases!=78)
            $fatal(1,"probe coverage counters");
        $display("APM_S8_PAIR_VENDOR_PROBE_PASS packed_vectors=%0d exact_products=%0d wide_vectors=%0d hold_checks=%0d latency_cycles=1 products_per_active_cycle=2",
            packed_cases,packed_cases*2,raw_cases,hold_cases);
        $finish;
    end
    initial begin #100000000; $fatal(1,"APM pair probe timeout"); end
endmodule
