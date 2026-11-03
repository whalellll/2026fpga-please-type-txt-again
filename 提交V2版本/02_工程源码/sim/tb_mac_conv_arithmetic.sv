`timescale 1ns/1ps
// Independent wide-integer arithmetic oracle; no dependency on RTL encoding.
// Since the RTL helpers were converted from functions to always @* blocks,
// this bench force-drives their input nets and checks the block outputs
// (same exhaustive coverage of dot4/requant semantics).
module tb_mac_conv_arithmetic;
    mac_conv_compute_core dut();
    reg [31:0] a,w;
    reg signed [32:0] value;
    reg [4:0] shift;
    reg [63:0] rng=64'h39a82e7206102026;
    integer i,j,k,s,delta,dots=0,quants=0;
    reg signed [63:0] sum,av,wv,magnitude,rounded,divisor,bound;
    reg [7:0] expected;

    task random64;
        begin
            rng=rng^(rng<<13);rng=rng^(rng>>7);rng=rng^(rng<<17);
        end
    endtask
    task check_dot;
        begin
            sum=0;
            for(k=0;k<4;k=k+1) begin
                av=$signed(a[k*8+:8]);wv=$signed(w[k*8+:8]);
                sum=sum+av*wv;
            end
            force dut.act_word=a;
            force dut.weight_pair={32'h0,w};
            #1;
            if(dut.dot4_lo!==sum[31:0])
                $fatal(1,"dot4 a=%h w=%h actual=%h expected=%h",a,w,dut.dot4_lo,sum[31:0]);
            dots=dots+1;
        end
    endtask
    task check_quant;
        begin
            magnitude=value;
            if(magnitude<0) magnitude=-magnitude;
            divisor=64'sd1<<shift;
            rounded=(magnitude+divisor/2)/divisor;
            if(value<0) rounded=-rounded;
            if(rounded>127) expected=8'h7f;
            else if(rounded < -128) expected=8'h80;
            else expected=rounded[7:0];
            force dut.biased=value;
            force dut.shift_selected=shift;
            #1;
            if(dut.requant_out!==expected)
                $fatal(1,"requant value=%0d shift=%0d actual=%h expected=%h",value,shift,dut.requant_out,expected);
            quants=quants+1;
        end
    endtask
    initial begin
        // Exhaust every signed-byte pair at the four-product sum extremes.
        for(i=0;i<256;i=i+1) for(j=0;j<256;j=j+1) begin
            a={4{8'(i)}};w={4{8'(j)}};check_dot();
        end
        for(i=0;i<20000;i=i+1) begin
            random64();a=rng[31:0];w=rng[63:32];check_dot();
        end
        for(s=0;s<32;s=s+1) begin
            shift=s;
            value=-33'sh100000000;check_quant();
            value=33'sh0ffffffff;check_quant();
            // Tie, just below/above tie, and both saturation boundaries.
            for(i=0;i<=130;i=i+1) for(delta=-1;delta<=1;delta=delta+1) begin
                bound=(64'(i)<<s)+((64'sd1<<s)/2)+delta;
                if(bound>=0 && bound<=64'shffffffff) begin
                    value=bound;check_quant();value=-bound;check_quant();
                end
            end
        end
        for(i=0;i<50000;i=i+1) begin
            random64();value=rng[32:0];shift=rng[37:33];check_quant();
        end
        $display("MAC_CONV_ARITHMETIC_PASS dot4=%0d requant=%0d all_shifts=32 signed33_extremes=enabled",dots,quants);
        $finish;
    end
endmodule
