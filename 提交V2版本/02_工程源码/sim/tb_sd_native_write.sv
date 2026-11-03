`timescale 1ns/1ps
module tb_sd_native_write;
    localparam BASE=32'h1fe13000;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0,wr=0,detect_n=0;
    reg [31:0] addr=0,wdata=0;
    reg [3:0] wstrb=0,card_dat=15;
    reg card_cmd=1;
    wire [31:0] rdata;
    wire hit,sd_clk,cmd_out,cmd_oe,dat_oe;
    wire [3:0] dat_out;
    wire [3:0] dat_in=dat_oe?dat_out:card_dat;
    wire cmd_in=cmd_oe?cmd_out:card_cmd;
    sd_native_mmio #(.RESET_DIV(1),.DEBOUNCE_CYCLES(2),
        .CMD_TIMEOUT_CLOCKS(64),.WRITE_TIMEOUT_CLOCKS(128)) dut(
        .clk(clk),.resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),
        .wstrb(wstrb),.rdata(rdata),.hit(hit),.sd_clk(sd_clk),
        .sd_cmd_in(cmd_in),.sd_cmd_out(cmd_out),.sd_cmd_oe(cmd_oe),
        .sd_dat_in(dat_in),.sd_dat_out(dat_out),.sd_dat_oe(dat_oe),.sd_detect_n(detect_n));
    integer i,lane,bitno,j,k;
    reg [47:0] response;
    reg [39:0] protected_bits;
    reg [6:0] crc7;
    reg [15:0] crc[0:3];
    reg [7:0] expected_byte;
    reg [3:0] expected_nibble;
    reg saw_dat=0;
    always @(posedge clk) if(dat_oe) saw_dat<=1;
    task write_reg(input [31:0] a,input [31:0] d);
        begin @(negedge clk);addr=a;wdata=d;wstrb=15;wr=1;
            @(negedge clk);wr=0;wstrb=0;end
    endtask
    task wait_done;
        integer guard;
        begin guard=0;
            while(dut.busy&&guard<15000)begin @(posedge clk);guard=guard+1;end
            #1;if(guard==15000||!dut.done||sd_clk||dat_oe||cmd_oe)
                $fatal(1,"write did not finish with released pins");
        end
    endtask
    task send_response(input [31:0] payload,input bad_crc);
        integer b;
        begin
            protected_bits={2'b00,6'd24,payload};crc7=0;
            for(b=39;b>=0;b=b-1)begin
                if(crc7[6]^protected_bits[b])crc7={crc7[5:0],1'b0}^7'h09;
                else crc7={crc7[5:0],1'b0};
            end
            response={protected_bits,crc7,1'b1};
            if(bad_crc)response[6]=~response[6];
            wait(cmd_oe);wait(!cmd_oe);card_cmd=response[47];
            for(b=47;b>=0;b=b-1)begin
                @(posedge sd_clk);if(b!=0)begin @(negedge sd_clk);card_cmd=response[b-1];end
            end
            @(negedge sd_clk);card_cmd=1;
        end
    endtask
    task card_write(input [4:0] token,input integer busy_clocks);
        integer b,n,c;
        begin
            send_response(32'h900,0);
            wait(dat_oe);@(posedge sd_clk);
            if(dat_out!=0)$fatal(1,"missing four-lane write start");
            for(n=0;n<4;n=n+1)crc[n]=0;
            for(b=0;b<1024;b=b+1)begin
                @(posedge sd_clk);#1;
                expected_byte=((b/2)*17+3)&255;
                expected_nibble=(b%2==0)?expected_byte[7:4]:expected_byte[3:0];
                if(!dat_oe||dat_out!=expected_nibble)$fatal(1,"write byte/nibble order at %0d: %h/%h",b,dat_out,expected_nibble);
                for(n=0;n<4;n=n+1)begin
                    if(crc[n][15]^dat_out[n])crc[n]={crc[n][14:0],1'b0}^16'h1021;
                    else crc[n]={crc[n][14:0],1'b0};
                end
            end
            for(b=15;b>=0;b=b-1)begin
                @(posedge sd_clk);#1;
                if(dat_out!={crc[3][b],crc[2][b],crc[1][b],crc[0][b]})$fatal(1,"write lane CRC mismatch bit %0d",b);
            end
            @(posedge sd_clk);#1;if(dat_out!=15)$fatal(1,"missing end token");
            wait(!dat_oe);@(negedge sd_clk);card_dat={3'b111,token[4]};
            for(b=4;b>=0;b=b-1)begin
                @(posedge sd_clk);if(dat_oe)$fatal(1,"host drives CRC-status token");
                if(b>0)begin @(negedge sd_clk);card_dat[0]=token[b-1];end
            end
            @(negedge sd_clk);card_dat=14;
            c=0;
            while(c<busy_clocks&&dut.busy)begin
                @(posedge sd_clk or negedge dut.busy);
                if(dut.busy)begin
                    if(dut.done||dat_oe)$fatal(1,"premature DONE or DAT drive while programming");
                    c=c+1;
                end
            end
            @(negedge clk);card_dat=15;
        end
    endtask
    initial begin
        repeat(4)@(posedge clk);@(negedge clk);resetn=1;repeat(5)@(posedge clk);
        write_reg(BASE+8,6);
        for(i=0;i<128;i=i+1)begin
            wdata=0;
            for(j=0;j<4;j=j+1)wdata=wdata|((((i*4+j)*17+3)&255)<<(j*8));
            write_reg(BASE+256+i*4,wdata);
        end
        for(k=0;k<3;k=k+1)begin
            write_reg(BASE+8,6);write_reg(BASE+20,7);
            fork
                card_write(k==1?5'b01011:5'b00101,k==2?200:16);
                write_reg(BASE+24,32'h1858);
            join
            wait_done();
            if(k==0&&(dut.error_sticky||dut.blocks_done!=1))$fatal(1,"valid CMD24 failed");
            if(k==1&&!dut.error_sticky[4])$fatal(1,"CRC rejection not reported");
            if(k==2&&!dut.error_sticky[3])$fatal(1,"programming busy timeout not reported");
        end
        for(k=0;k<2;k=k+1)begin
            write_reg(BASE+8,6);saw_dat=0;
            fork
                send_response(k==0?32'h900:32'h04000900,k==0);
                write_reg(BASE+24,32'h1858);
            join
            wait_done();if(saw_dat||!dut.error_sticky)$fatal(1,"data sent after bad R1");
        end
        write_reg(BASE+8,6);write_reg(BASE+24,32'h1859);wait_done();
        if(!dut.error_sticky[2])$fatal(1,"non-CMD24 write accepted");
        write_reg(BASE+8,6);
        fork
            begin send_response(32'h900,0);wait(dat_oe);repeat(8)@(posedge sd_clk);detect_n=1;end
            write_reg(BASE+24,32'h1858);
        join
        wait_done();if(!dut.error_sticky[6])$fatal(1,"removal did not cancel write");
        $display("SD_NATIVE_WRITE_CRC_BUSY_REJECT_REMOVAL_PASS");$finish;
    end
    initial begin #2000000;$fatal(1,"write bench watchdog");end
endmodule
