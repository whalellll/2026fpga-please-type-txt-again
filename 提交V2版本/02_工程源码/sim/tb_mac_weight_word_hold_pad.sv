`timescale 1ns/1ps
module tb_mac_weight_word_hold_pad;
  reg clk=0; always #10 clk=~clk;
  reg rstn=0,word_we=0,wide_we=0,re=0;
  reg [31:0] wa=0,ra=0,word_data=0;
  reg [4:0] wi=0;
  reg [1023:0] wide_data=0;
  wire [1023:0] word_q,wide_q;
  reg [1023:0] previous_word,previous_wide;
  reg [31:0] expected;
  integer line,word_index;
  Bank1R1W_1_compact #(.WORD_WRITE(1)) word_bank(
    .io_clk(clk),.io_rstN(rstn),.io_we(1'b0),.io_re(re),.io_waddr(wa),.io_raddr(ra),
    .io_wdata(1024'b0),.io_wordWe(word_we),.io_wordIndex(wi),.io_wordData(word_data),.io_rdata(word_q));
  Bank1R1W_1_compact #(.WORD_WRITE(0)) wide_bank(
    .io_clk(clk),.io_rstN(rstn),.io_we(wide_we),.io_re(re),.io_waddr(wa),.io_raddr(ra),
    .io_wdata(wide_data),.io_wordWe(1'b0),.io_wordIndex(5'b0),.io_wordData(32'b0),.io_rdata(wide_q));
  initial begin
    #1000000;$fatal(1,"weight word hold test timeout");
  end
  initial begin
    repeat(2)@(negedge clk);rstn=1;
    for(line=0;line<64;line=line+1)begin
      for(word_index=0;word_index<32;word_index=word_index+1)begin
        @(negedge clk);wa=line;wi=word_index;word_we=1;
        word_data=32'h80310207^(line*32'h01010101)^(word_index*32'h10204081);
      end
    end
    @(negedge clk);word_we=0;
    for(line=0;line<64;line=line+1)begin
      @(negedge clk);wa=line;wide_we=1;
      for(word_index=0;word_index<32;word_index=word_index+1)
        wide_data[word_index*32+:32]=(32'h80310207^(line*32'h01010101)^(word_index*32'h10204081))^32'hffeeddcc;
    end
    @(negedge clk);wide_we=0;
    for(line=0;line<64;line=line+1)begin
      previous_word=word_q;previous_wide=wide_q;
      @(negedge clk);ra=line;re=1;#1;
      if(word_q!==previous_word||wide_q!==previous_wide)$fatal(1,"read changed before enabled edge");
      @(posedge clk);#1;
      for(word_index=0;word_index<32;word_index=word_index+1)begin
        expected=32'h80310207^(line*32'h01010101)^(word_index*32'h10204081);
        if(word_q[word_index*32+:32]!==expected)$fatal(1,"word data mismatch line%0d word%0d",line,word_index);
        if(wide_q[word_index*32+:32]!==(expected^32'hffeeddcc))$fatal(1,"wide data mismatch");
      end
    end
    @(negedge clk);re=0;previous_word=word_q;previous_wide=wide_q;ra=17;
    repeat(3)@(posedge clk);#1;
    if(word_q!==previous_word||wide_q!==previous_wide)$fatal(1,"disabled read changed");
    @(negedge clk);wa=64;word_we=1;wide_we=1;wi=7;word_data=32'hdeadbeef;wide_data=0;
    @(negedge clk);wa=32'hffffffff;
    @(negedge clk);word_we=0;wide_we=0;ra=0;re=1;
    @(posedge clk);#1;
    for(word_index=0;word_index<32;word_index=word_index+1)begin
      expected=32'h80310207^(word_index*32'h10204081);
      if(word_q[word_index*32+:32]!==expected||wide_q[word_index*32+:32]!==(expected^32'hffeeddcc))$fatal(1,"out of range write aliased");
    end
    @(negedge clk);rstn=0;#1;
    if(word_q!==1024'b0||wide_q!==1024'b0)$fatal(1,"read reset mismatch");
    @(negedge clk);rstn=1;ra=63;re=1;
    @(posedge clk);#1;
    for(word_index=0;word_index<32;word_index=word_index+1)begin
      expected=32'h80310207^(63*32'h01010101)^(word_index*32'h10204081);
      if(word_q[word_index*32+:32]!==expected)$fatal(1,"capacity/reset retention mismatch");
    end
    $display("MAC_WEIGHT_WORD_HOLD_IDENTITY_CAPACITY_AND_CYCLE_PASS lines=64 words=32");$finish;
  end
endmodule
