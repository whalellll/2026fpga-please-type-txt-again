`timescale 1ns/1ps

// Independent model oracle and DMA accounting for the latency candidate.
module tb_pff1_stagea_stream;
    localparam [31:0] SCRATCH=32'h1b000000, DESC=SCRATCH+32'h100;
    localparam [31:0] BASE=SCRATCH+32'h1000, OUT=SCRATCH+32'h2000;
    localparam [31:0] THREAT=32'h10002000, PSQ=32'h12f45000;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg reg_wr_en=0; reg [7:0] reg_wr_addr=0,reg_rd_addr=0;
    reg [31:0] reg_wr_data=0; reg [3:0] reg_wr_strb=4'hf;
    wire [31:0] reg_rd_data;
    wire mem_req_valid,mem_req_write,mem_w_valid,mem_w_last,mem_rsp_ready;
    wire [31:0] mem_req_addr,mem_w_data;
    wire [2:0] mem_req_len; wire [3:0] mem_w_strb;
    reg [1:0] bus_state=0;
    reg [31:0] bus_addr=0;
    reg [3:0] bus_index=0,bus_beats=0;
    reg [5:0] delay_count=0;
    integer wall=0, delay_per_burst=0;
    reg paced=0, inject_read_error=0;
    integer descriptor_bytes=0,model_bytes=0,base_bytes=0,output_bytes=0;
    integer requests=0;
    wire mem_req_ready=bus_state==0 && (!paced || wall%7!=0);
    wire mem_w_ready=bus_state==2 && (!paced || wall%5!=0);
    wire mem_rsp_valid=(bus_state==1 || bus_state==3) && delay_count==0 &&
                       (!paced || wall%3!=0);
    wire mem_rsp_last=bus_state==3 || bus_index+1==bus_beats;
    wire mem_rsp_error=inject_read_error && bus_state==1;
    reg [31:0] scratch[0:16383];
    integer count=0;

    // Former feature function as a task; the four byte lanes used by
    // mem_rsp_rdata are precomputed combinationally from read_address.
    reg [7:0] feature_result;
    task feature;
        input [31:0] addr;
        integer row,lane;
        begin
            if(addr>=THREAT && addr<THREAT+45547*1024) begin
                row=(addr-THREAT)/1024; lane=(addr-THREAT)%1024;
                feature_result=(row*37+lane*29+(lane>>3)*11)^8'ha5;
            end else if(addr>=PSQ && addr<PSQ+16536*1024) begin
                row=(addr-PSQ)/1024; lane=(addr-PSQ)%1024;
                feature_result=(row*13+lane*71+(lane>>4)*7)^8'h36;
            end else feature_result=0;
        end
    endtask
    reg [7:0] fe3, fe2, fe1, fe0;
    always @* begin
        feature(read_address + 32'd3); fe3 = feature_result;
        feature(read_address + 32'd2); fe2 = feature_result;
        feature(read_address + 32'd1); fe1 = feature_result;
        feature(read_address);         fe0 = feature_result;
    end
    wire [31:0] read_address=bus_addr+bus_index*4;
    wire [31:0] mem_rsp_rdata=bus_state!=1 ? 0 :
        (read_address>=SCRATCH && read_address<SCRATCH+65536) ?
        scratch[(read_address-SCRATCH)>>2] :
        {fe3, fe2, fe1, fe0};

    pff1_stagea_gather dut(.*);
    always @(posedge clk) begin
        wall<=wall+1;
        if(!resetn) begin bus_state<=0; delay_count<=0; end
        else begin
            if(delay_count!=0) delay_count<=delay_count-1;
            case(bus_state)
                0: if(mem_req_valid && mem_req_ready) begin
                    if(mem_req_len>7 || mem_req_addr[1:0]!=0 ||
                       mem_req_addr[11:0]+(mem_req_len+1)*4>4096)
                        $fatal(1,"invalid burst %h len=%0d",mem_req_addr,mem_req_len);
                    bus_addr<=mem_req_addr; bus_beats<=mem_req_len+1;
                    bus_index<=0; delay_count<=delay_per_burst;
                    bus_state<=mem_req_write ? 2 : 1;
                    requests<=requests+1;
                    if(mem_req_write) begin
                        if(mem_req_addr<OUT || mem_req_addr+(mem_req_len+1)*4>OUT+2048)
                            $fatal(1,"stray write %h",mem_req_addr);
                        output_bytes<=output_bytes+(mem_req_len+1)*4;
                    end else if(mem_req_addr>=DESC && mem_req_addr<DESC+1024)
                        descriptor_bytes<=descriptor_bytes+(mem_req_len+1)*4;
                    else if(mem_req_addr>=BASE && mem_req_addr<BASE+2048)
                        base_bytes<=base_bytes+(mem_req_len+1)*4;
                    else if((mem_req_addr>=THREAT && mem_req_addr<THREAT+45547*1024) ||
                            (mem_req_addr>=PSQ && mem_req_addr<PSQ+16536*1024))
                        model_bytes<=model_bytes+(mem_req_len+1)*4;
                    else $fatal(1,"stray read %h",mem_req_addr);
                end
                1: if(mem_rsp_valid && mem_rsp_ready) begin
                    if(mem_rsp_last) bus_state<=0;
                    else bus_index<=bus_index+1;
                end
                2: if(mem_w_valid && mem_w_ready) begin
                    if(mem_w_strb!=4'hf || mem_w_last!=(bus_index+1==bus_beats))
                        $fatal(1,"invalid write framing");
                    scratch[(bus_addr-SCRATCH)/4+bus_index]<=mem_w_data;
                    if(mem_w_last) begin bus_state<=3; delay_count<=delay_per_burst; end
                    else bus_index<=bus_index+1;
                end
                3: if(mem_rsp_valid && mem_rsp_ready) bus_state<=0;
            endcase
        end
    end
    task automatic wr(input [7:0] addr,input [31:0] data);
        begin
            @(negedge clk);reg_wr_en=1;reg_wr_addr=addr;reg_wr_data=data;
            @(negedge clk);reg_wr_en=0;
        end
    endtask
    task automatic wait_done;
        integer ticks;
        begin
            reg_rd_addr=8'h0c;ticks=0;
            while(!reg_rd_data[1] && ticks<500000) begin @(negedge clk);ticks++;end
            if(!reg_rd_data[1]) $fatal(1,"DMA did not complete");
        end
    endtask
    task automatic stage(input integer terms);
        integer i;
        reg [31:0] desc;
        begin
            count=terms;
            for(i=0;i<256;i++) begin
                desc=((i%3==0)?32'h80000000:0) | ((i%2)?32'h40000000:0) |
                     ((i%2)?(16535-i):(45546-i));
                scratch[(DESC-SCRATCH)/4+i]=desc;
            end
            for(i=0;i<512;i++) begin
                scratch[(BASE-SCRATCH)/4+i]=((32'h7ff0+i*17)&65535)<<16 |
                                            ((32'hfff0+i*13)&65535);
                scratch[(OUT-SCRATCH)/4+i]=32'hdeadbeef;
            end
            scratch[(OUT-SCRATCH)/4-1]=32'hcafebabe;
            scratch[(OUT-SCRATCH)/4+512]=32'h12345678;
            descriptor_bytes=0;model_bytes=0;base_bytes=0;output_bytes=0;requests=0;
            wr(8'h08,2);wr(8'h10,BASE);wr(8'h14,DESC);wr(8'h18,OUT);wr(8'h1c,terms);
        end
    endtask
    task automatic verify(input integer terms,input integer max_cycles);
        integer lane,i,sum,weight;
        reg [31:0] desc,addr,actual;
        begin
            if(reg_rd_data[2]) $fatal(1,"unexpected error status %h",reg_rd_data);
            for(lane=0;lane<1024;lane++) begin
                sum=(scratch[(BASE-SCRATCH)/4+lane/2]>>(16*(lane%2)))&65535;
                for(i=0;i<terms;i++) begin
                    desc=scratch[(DESC-SCRATCH)/4+i];
                    addr=(desc[30]?PSQ:THREAT)+(desc&65535)*1024+lane;
                    feature(addr);weight=$signed(feature_result);
                    sum=sum+(desc[31]?-weight:weight);
                end
                actual=(scratch[(OUT-SCRATCH)/4+lane/2]>>(16*(lane%2)))&65535;
                if(actual!=(sum&65535)) $fatal(1,"oracle lane=%0d actual=%h expected=%h",lane,actual,sum&65535);
            end
            if(scratch[(OUT-SCRATCH)/4-1]!=32'hcafebabe ||
               scratch[(OUT-SCRATCH)/4+512]!=32'h12345678) $fatal(1,"output canary");
            if(descriptor_bytes!=terms*4 || model_bytes!=terms*1024 ||
               base_bytes!=2048 || output_bytes!=2048)
                $fatal(1,"traffic desc=%0d model=%0d base=%0d out=%0d",descriptor_bytes,model_bytes,base_bytes,output_bytes);
            reg_rd_addr=8'h20;#1;
            if(reg_rd_data>max_cycles) $fatal(1,"cycle budget %0d > %0d",reg_rd_data,max_cycles);
            $display("PFF1_STREAM_CASE_PASS terms=%0d cycles=%0d desc_bytes=%0d model_bytes=%0d bursts=%0d paced=%0d delay=%0d",
                terms,reg_rd_data,descriptor_bytes,model_bytes,requests,paced,delay_per_burst);
        end
    endtask
    integer i;
    initial begin
        repeat(4)@(negedge clk);resetn=1;
        stage(3);wr(8'h08,1);wait_done();verify(3,6000);
        stage(256);wr(8'h08,1);wait_done();verify(256,100000);
        paced=1;delay_per_burst=20;
        stage(256);wr(8'h08,1);wait_done();verify(256,495000);
        stage(256);scratch[(DESC-SCRATCH)/4+255]=32'h40004098;
        wr(8'h08,1);wait_done();
        if(!reg_rd_data[2] || output_bytes || model_bytes) $fatal(1,"late invalid descriptor escaped validation");
        for(i=0;i<512;i++) if(scratch[(OUT-SCRATCH)/4+i]!=32'hdeadbeef) $fatal(1,"error changed output");
        stage(1);wr(8'h1c,32'h201);wr(8'h08,1);wait_done();
        if(!reg_rd_data[2] || requests) $fatal(1,"wrapped count accepted");
        stage(1);wr(8'h18,SCRATCH+32'hff804);wr(8'h08,1);wait_done();
        if(!reg_rd_data[2] || requests) $fatal(1,"scratch boundary accepted");
        stage(1);inject_read_error=1;wr(8'h08,1);wait_done();inject_read_error=0;
        if(!reg_rd_data[2] || output_bytes || model_bytes) $fatal(1,"DDR fault not contained");
        // Recovery after a fault must produce a fresh, data-distinct result.
        stage(1);wr(8'h08,1);wait_done();verify(1,6000);
        $display("PFF1_STAGEA_STREAM_PASS");$finish;
    end
    initial begin #20000000;$fatal(1,"global timeout");end
endmodule
