`timescale 1ns/1ps
module tb_mac_conv_config;
    reg [8:0] width=6,height=6;
    reg [15:0] channels=3,output_channels=16;
    reg [2:0] kernel=6,padding=0;
    reg [1:0] stride=1;
    reg [5:0] weight_lines=27;
    integer c,k,l,oc,i,total=0;
    reg expected;
    reg [63:0] rng=64'h09a107e0102026;
    reg [63:0] scalar_count,needed_rows,padded_w,padded_h;
    mac_conv_compute_core dut(.width(width),.height(height),.channels(channels),
        .output_channels(output_channels),.kernel(kernel),.stride(stride),
        .padding(padding),.weight_lines(weight_lines));
    task check;
        begin
            scalar_count=channels;scalar_count=scalar_count*kernel*kernel;
            needed_rows=(scalar_count+3)/4;
            padded_w=width+2*padding;padded_h=height+2*padding;
            expected=width>0 && height>0 && channels>=1 && channels<=4 &&
                output_channels>=1 && output_channels<=16 &&
                (kernel==1 || kernel==3 || kernel==6) && (stride==1 || stride==2) &&
                padding<kernel && padded_w>=kernel && padded_h>=kernel &&
                scalar_count<=128 && weight_lines==needed_rows;
            #1;
            if(dut.valid_config !== expected)
                $fatal(1,"config w=%0d h=%0d cin=%0d cout=%0d k=%0d s=%0d pad=%0d rows=%0d actual=%b expected=%b",
                    width,height,channels,output_channels,kernel,stride,padding,weight_lines,dut.valid_config,expected);
            total=total+1;
        end
    endtask
    initial begin
        // Every Cin value: ensure high bits cannot alias a supported tile.
        for(c=0;c<65536;c=c+1) for(k=1;k<=6;k=k+1) if(k==1 || k==3 || k==6) begin
            channels=c;kernel=k;
            for(l=0;l<3;l=l+1) begin
                weight_lines=l==0 ? 0 : l==1 ? (c*k*k+3)/4 : 32;
                check();
            end
        end
        channels=3;
        for(oc=0;oc<65536;oc=oc+1) for(k=1;k<=6;k=k+1) if(k==1 || k==3 || k==6) begin
            output_channels=oc;kernel=k;weight_lines=(3*k*k+3)/4;check();
        end
        // Accepted small tiles, invalid Cout tails and every weight-row count.
        for(c=1;c<=4;c=c+1) for(k=0;k<8;k=k+1)
            for(oc=0;oc<=17;oc=oc+1) for(l=0;l<64;l=l+1) begin
                channels=c;kernel=k;output_channels=oc;weight_lines=l;check();
            end
        for(i=0;i<20000;i=i+1) begin
            rng=rng^(rng<<13);rng=rng^(rng>>7);rng=rng^(rng<<17);
            width=rng[8:0];height=rng[17:9];channels=rng[20:18];
            output_channels=rng[25:21];kernel=rng[28:26];stride=rng[30:29];
            padding=rng[33:31];weight_lines=rng[39:34];check();
        end
        $display("MAC_CONV_CONFIG_PASS checks=%0d exhaustive_cin16=true exhaustive_cout16=true invalid_high_bits=true",total);
        $finish;
    end
endmodule
