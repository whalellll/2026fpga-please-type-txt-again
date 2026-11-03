`timescale 1ns/1ps
// Pin-level CMD25 contract: real four-lane data/CRC/status/busy/stop signals.
module tb_sd_native_multiblock;
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
    sd_native_mmio #(.RESET_DIV(0),.DEBOUNCE_CYCLES(2),
        .CMD_TIMEOUT_CLOCKS(64),.WRITE_TIMEOUT_CLOCKS(128),
        .TX_WAIT_TIMEOUT_CYCLES(1000)) dut(
        .clk(clk),.resetn(resetn),.addr(addr),.wr(wr),.wdata(wdata),
        .wstrb(wstrb),.rdata(rdata),.hit(hit),.sd_clk(sd_clk),
        .sd_cmd_in(cmd_in),.sd_cmd_out(cmd_out),.sd_cmd_oe(cmd_oe),
        .sd_dat_in(dat_in),.sd_dat_out(dat_out),.sd_dat_oe(dat_oe),.sd_detect_n(detect_n));
    reg [47:0] host_command;
    integer host_bits,cmd25_count=0,cmd12_count=0;
    reg saw_data=0;
    reg [31:0] stop_payload=32'h900;
    always @(posedge cmd_oe) begin host_command=0;host_bits=0;end
    always @(posedge sd_clk) if(cmd_oe)begin
        host_command={host_command[46:0],cmd_out};host_bits=host_bits+1;
    end
    always @(posedge clk) if(dat_oe)saw_data<=1;

    task write_reg(input [31:0] a,input [31:0] d);
        begin @(negedge clk);addr=a;wdata=d;wstrb=15;wr=1;
            @(negedge clk);wr=0;wstrb=0;end
    endtask
    task check_word(input [31:0] a,input [31:0] expected);
        begin @(negedge clk);addr=a;#1;
            if(rdata!==expected)
                $fatal(1,"CMD25 CPU mirror addr=%h got=%h expected=%h",
                    a,rdata,expected);
        end
    endtask
    task fill_bank(input integer bank,input integer block);
        integer i,j;reg [31:0] word;
        begin
            for(i=0;i<128;i=i+1)begin
                word=0;
                for(j=0;j<4;j=j+1)
                    word=word|((((i*4+j)*17+3+block*29)&255)<<(j*8));
                write_reg(BASE+256+bank*512+i*4,word);
            end
            write_reg(BASE+84,bank==0?1:2);
        end
    endtask
    task prepare(input integer count,input integer banks);
        begin
            write_reg(BASE+8,1);write_reg(BASE+8,6);
            write_reg(BASE+20,7);write_reg(BASE+52,count);
            fill_bank(0,0);if(banks==2)fill_bank(1,1);
            // Attempts to overwrite a published bank must be ignored.
            write_reg(BASE+256,32'hdeadbeef);
            if(banks==2)write_reg(BASE+768,32'hbadc0ffe);
            check_word(BASE+256,32'h36251403);
            if(banks==2)check_word(BASE+768,32'h53423120);
            saw_data=0;
            stop_payload=32'h900;
        end
    endtask
    task wait_done;
        integer guard;
        begin guard=0;
            while(dut.busy&&guard<25000)begin @(posedge clk);guard=guard+1;end
            #1;if(guard==25000||!dut.done||sd_clk||dat_oe||cmd_oe||
                dut.tx0_full||dut.tx1_full||dut.write_multi_active)
                $fatal(1,"CMD25 did not drain/release ownership and pins");
        end
    endtask
    task send_response(input [5:0] index,input [31:0] payload,input bad_crc);
        integer b;reg [39:0] bits;reg [6:0] crc;reg [47:0] frame;
        begin
            bits={2'b00,index,payload};crc=0;
            for(b=39;b>=0;b=b-1)begin
                if(crc[6]^bits[b])crc={crc[5:0],1'b0}^7'h09;
                else crc={crc[5:0],1'b0};
            end
            frame={bits,crc,1'b1};if(bad_crc)frame[6]=~frame[6];
            wait(cmd_oe);wait(!cmd_oe);#1;
            if(host_bits!=48||host_command[45:40]!=index)
                $fatal(1,"expected command%0d got%0d/%0d",index,host_command[45:40],host_bits);
            if(index==25)cmd25_count=cmd25_count+1;
            else if(index==12)cmd12_count=cmd12_count+1;
            card_cmd=frame[47];
            for(b=47;b>=0;b=b-1)begin
                @(posedge sd_clk);if(b!=0)begin @(negedge sd_clk);card_cmd=frame[b-1];end
            end
            @(negedge sd_clk);card_cmd=1;
        end
    endtask
    task receive_block(input integer block,input [4:0] token,input integer busy_clocks);
        integer b,n,c;reg [15:0] crc[0:3];reg [7:0] byte_value;reg [3:0] nibble;
        begin
            wait(dat_oe);@(posedge sd_clk);#1;
            if(dat_out!=0)$fatal(1,"missing CMD25 four-lane start");
            for(n=0;n<4;n=n+1)crc[n]=0;
            for(b=0;b<1024;b=b+1)begin
                @(posedge sd_clk);#1;
                byte_value=((b/2)*17+3+block*29)&255;
                nibble=(b%2==0)?byte_value[7:4]:byte_value[3:0];
                if(!dat_oe||dat_out!=nibble)
                    $fatal(1,"CMD25 block%0d nibble%0d %h/%h",block,b,dat_out,nibble);
                for(n=0;n<4;n=n+1)begin
                    if(crc[n][15]^dat_out[n])crc[n]={crc[n][14:0],1'b0}^16'h1021;
                    else crc[n]={crc[n][14:0],1'b0};
                end
            end
            for(b=15;b>=0;b=b-1)begin
                @(posedge sd_clk);#1;
                if(dat_out!={crc[3][b],crc[2][b],crc[1][b],crc[0][b]})
                    $fatal(1,"CMD25 block%0d laneCRC bit%0d",block,b);
            end
            @(posedge sd_clk);#1;if(dat_out!=15)$fatal(1,"CMD25 end token");
            wait(!dat_oe);@(negedge sd_clk);card_dat={3'b111,token[4]};
            for(b=4;b>=0;b=b-1)begin
                @(posedge sd_clk);if(dat_oe)$fatal(1,"host drives CRCstatus");
                if(b>0)begin @(negedge sd_clk);card_dat[0]=token[b-1];end
            end
            @(negedge sd_clk);card_dat=14;c=0;
            while(c<busy_clocks&&dut.busy&&dut.state==19)begin
                @(posedge sd_clk or negedge dut.busy);#1;
                if(dut.busy)begin
                    if(dut.done||dat_oe)$fatal(1,"premature DONE/DAT drive while busy");
                    c=c+1;
                end
            end
            @(negedge clk);card_dat=15;
        end
    endtask
    task stop_response(input bad_crc,input integer busy_clocks);
        integer c;
        begin
            send_response(12,stop_payload,bad_crc);card_dat=14;c=0;
            while(c<busy_clocks&&dut.busy)begin
                @(posedge sd_clk or negedge dut.busy);#1;
                if(dut.busy)begin
                    if(dut.done||dat_oe)$fatal(1,"premature stop busy completion");
                    c=c+1;
                end
            end
            @(negedge clk);card_dat=15;
        end
    endtask
    integer k,n;
    initial begin
        repeat(4)@(posedge clk);@(negedge clk);resetn=1;repeat(5)@(posedge clk);
        addr=BASE+4;#1;if(rdata!=32'h00050401)$fatal(1,"CMD25 hardware version");
        // Two prefilled banks plus concurrent reuse. Published/active writes
        // cannot corrupt the bytes checked at the physical DAT pins.
        prepare(4,2);
        fork
            begin send_response(25,32'h900,0);
                for(n=0;n<4;n=n+1)receive_block(n,5'b00101,16);
                stop_response(0,8);
            end
            begin
                wait(dut.state==14&&dut.data_byte_count>20);
                write_reg(BASE+384,32'hdeadbeef);
                // Word 32 is still ahead of the serializer. Its CPU view
                // and the later pin-level byte/CRC stream must both retain
                // the published value after the forbidden host write.
                check_word(BASE+384,32'hb6a59483);
                wait(dut.state==20&&dut.blocks_done==2&&!sd_clk);
                repeat(20)begin @(posedge clk);
                    if(sd_clk||dat_oe)$fatal(1,"resumable producer gap not paused low");
                end
                fill_bank(0,2);
                check_word(BASE+256,32'h705f4e3d);
                wait(!dut.tx1_full);fill_bank(1,3);
                check_word(BASE+768,32'h8d7c6b5a);
            end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(dut.error_sticky||dut.blocks_done!=4)$fatal(1,"CMD25 stream4 failed");
        // Cancel during an in-flight payload: exactly that block completes,
        // then CRCstatus, busy and CMD12 drain precede terminal completion.
        prepare(4,2);
        fork
            begin send_response(25,32'h900,0);receive_block(0,5'b00101,20);stop_response(0,8);end
            begin wait(dut.state==14&&dut.data_byte_count>20);write_reg(BASE+88,1);end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(dut.error_sticky||dut.blocks_done!=1||!dut.write_stop_requested)
            $fatal(1,"CMD25 mid-block graceful stop failed");
        // No producer for bank1: pause low, then watchdog invokes CMD12.
        prepare(3,1);
        fork
            begin send_response(25,32'h900,0);receive_block(0,5'b00101,8);
                wait(dut.state==20&&!sd_clk);repeat(50)begin
                    @(posedge clk);if(sd_clk||dat_oe||cmd_oe)$fatal(1,"producer gap clock not low");
                end
                stop_response(0,8);
            end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(!dut.error_sticky[3]||dut.blocks_done!=1)$fatal(1,"producer timeout missed");
        // Explicit cancellation of the same paused producer state succeeds.
        prepare(3,1);
        fork
            begin send_response(25,32'h900,0);receive_block(0,5'b00101,8);stop_response(0,8);end
            begin wait(dut.state==20&&dut.blocks_done==1);write_reg(BASE+88,1);end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(dut.error_sticky||dut.blocks_done!=1)$fatal(1,"paused cancel failed");
        // A rejected CRCstatus drains its programming busy before stopping.
        prepare(2,2);
        fork
            begin send_response(25,32'h900,0);receive_block(0,5'b01011,20);stop_response(0,8);end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(!dut.error_sticky[4]||dut.blocks_done!=0)$fatal(1,"CMD25 CRCreject failed");
        // Initial command R1 failure and initial response CRC failure both
        // send no payload and still stop the possibly accepted write session.
        for(k=0;k<2;k=k+1)begin
            prepare(2,2);
            fork
                begin send_response(25,k==0?32'h04000900:32'h900,k!=0);stop_response(0,8);end
                write_reg(BASE+24,32'h1c59);
            join
            wait_done();if(saw_data||!dut.error_sticky)$fatal(1,"data after bad CMD25 R1");
        end
        // Stop response CRC/R1 error and programming timeout never succeed.
        for(k=0;k<3;k=k+1)begin
            prepare(2,2);
            if(k==2)stop_payload=32'h04000900;
            fork
                begin send_response(25,32'h900,0);receive_block(0,5'b00101,8);
                    receive_block(1,5'b00101,8);stop_response(k==0,k==1?200:8);
                end
                write_reg(BASE+24,32'h1c59);
            join
            wait_done();if(dut.blocks_done!=2||!(k==0?dut.error_sticky[1]:k==1?dut.error_sticky[3]:dut.error_sticky[7]))
                $fatal(1,"bad CMD12 completion accepted");
        end
        // Current-block busy timeout still executes the CMD12 recovery path.
        prepare(2,2);
        fork
            begin send_response(25,32'h900,0);receive_block(0,5'b00101,200);stop_response(0,8);end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(!dut.error_sticky[3]||dut.blocks_done)$fatal(1,"CMD25 busy timeout missed");
        // Physical removal releases all pads and ownership without retry.
        prepare(2,2);
        fork
            begin send_response(25,32'h900,0);wait(dat_oe);repeat(16)@(posedge sd_clk);detect_n=1;end
            write_reg(BASE+24,32'h1c59);
        join
        wait_done();if(!dut.error_sticky[6])$fatal(1,"CMD25 removal missed");
        if(cmd25_count!=12||cmd12_count!=11)$fatal(1,"unexpected retry/stop count %0d/%0d",cmd25_count,cmd12_count);
        $display("SD_NATIVE_CMD25_STREAM_OWNERSHIP_CANCEL_STARVATION_CRC_BUSY_STOP_REMOVAL_PASS");$finish;
    end
    initial begin #3000000;$fatal(1,"CMD25 pin bench watchdog");end
endmodule
