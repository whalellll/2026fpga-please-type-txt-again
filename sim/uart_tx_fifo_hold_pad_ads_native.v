module uart_tx_fifo
(
    input [7:0] push_data,
    input N25,
    input clk,
    input push,
    input \u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ,
    output empty,
    output full,
    output idle,
    output tx
);
    wire [3:0] N36;
    wire [7:0] N39;
    wire [3:0] N42;
    wire [3:0] N53;
    wire N98;
    wire N150;
    wire [4:0] N153;
    wire N159;
    wire N163;
    wire N164;
    wire N167;
    wire [15:0] N168;
    wire N178;
    wire N189_1;
    wire N190;
    wire [3:0] N191;
    wire N194;
    wire _N29740;
    wire _N29741;
    wire _N29742;
    wire _N29743;
    wire _N31354;
    wire _N31370;
    wire _N73358;
    wire _N73359;
    wire _N73363;
    wire _N73364;
    wire _N353009;
    wire _N356506;
    wire [15:0] baud_count;
    wire [4:0] count;
    wire [3:0] fifo_write_address;
    wire [3:0] pad_address_in;
    wire pop;
    wire [3:0] rd_ptr;
    wire [3:0] tx_bit;
    wire tx_busy;
    wire [9:0] tx_shift;

    GTP_LUT6 /* N15 */ #(
            .INIT(64'b0101010101010101010101010101010101010101010101010101010101010100))
        N15 (
            .Z (pop),
            .I0 (tx_busy),
            .I1 (count[0]),
            .I2 (count[1]),
            .I3 (count[2]),
            .I4 (count[3]),
            .I5 (count[4]));
	// LUT = (~I0&I1)|(~I0&I2)|(~I0&I3)|(~I0&I4)|(~I0&I5) ;
	// ../../rtl/soc/uart_tx_fifo.v:62

    GTP_LUT6D /* N24 */ #(
            .INIT(64'b0000000000000000000000000000000000000000000000000000000000000001))
        N24 (
            .Z (idle),
            .Z5 (empty),
            .I0 (count[4]),
            .I1 (count[0]),
            .I2 (count[1]),
            .I3 (count[2]),
            .I4 (count[3]),
            .I5 (tx_busy));
	// LUT = ~I0&~I1&~I2&~I3&~I4&~I5 ;
	// Z5 = ~I0&~I1&~I2&~I3&~I4 ;
	// ../../rtl/soc/uart_tx_fifo.v:66

    GTP_LUT6D /* N36_sum1 */ #(
            .INIT(64'b0110011001100110011001100110011001010101010101010101010101010101))
        N36_sum1 (
            .Z (N36[1]),
            .Z5 (N36[0]),
            .I0 (pad_address_in[0]),
            .I1 (pad_address_in[1]),
            .I2 (),
            .I3 (),
            .I4 (),
            .I5 (1'b1));
	// LUT = I1^I0 ;
	// Z5 = ~I0 ;

    GTP_LUT6D /* N36_sum2 */ #(
            .INIT(64'b0111100001111000011110000111100001111111100000000111111110000000))
        N36_sum2 (
            .Z (N36[2]),
            .Z5 (N36[3]),
            .I0 (pad_address_in[0]),
            .I1 (pad_address_in[1]),
            .I2 (pad_address_in[2]),
            .I3 (pad_address_in[3]),
            .I4 (),
            .I5 (1'b1));
	// LUT = (I0&I1&~I2)|(~I1&I2)|(~I0&I2) ;
	// Z5 = (I0&I1&I2&~I3)|(~I2&I3)|(~I1&I3)|(~I0&I3) ;

    GTP_LUT6D /* N42_sum1 */ #(
            .INIT(64'b0110011001100110011001100110011001111000011110000111100001111000))
        N42_sum1 (
            .Z (N42[1]),
            .Z5 (N42[2]),
            .I0 (rd_ptr[0]),
            .I1 (rd_ptr[1]),
            .I2 (rd_ptr[2]),
            .I3 (),
            .I4 (),
            .I5 (1'b1));
	// LUT = I1^I0 ;
	// Z5 = (I0&I1&~I2)|(~I1&I2)|(~I0&I2) ;

    GTP_LUT6D /* N42_sum3 */ #(
            .INIT(64'b0111111110000000011111111000000001010101010101010101010101010101))
        N42_sum3 (
            .Z (N42[3]),
            .Z5 (N42[0]),
            .I0 (rd_ptr[0]),
            .I1 (rd_ptr[1]),
            .I2 (rd_ptr[2]),
            .I3 (rd_ptr[3]),
            .I4 (),
            .I5 (1'b1));
	// LUT = (I0&I1&I2&~I3)|(~I2&I3)|(~I1&I3)|(~I0&I3) ;
	// Z5 = ~I0 ;

    GTP_LUT6D /* N56_3 */ #(
            .INIT(64'b1111001111100010110100011100000001010101010101010101010101010101))
        N56_3 (
            .Z (_N73358),
            .Z5 (N53[0]),
            .I0 (tx_bit[0]),
            .I1 (tx_bit[3]),
            .I2 (tx_shift[0]),
            .I3 (tx_shift[7]),
            .I4 (tx_shift[8]),
            .I5 (1'b1));
	// LUT = (I0&~I1&I4)|(~I0&~I1&I3)|(I1&I2) ;
	// Z5 = ~I0 ;

    GTP_LUT6D /* N56_4 */ #(
            .INIT(64'b1111111110101010010101010000000001111000011110000111100001111000))
        N56_4 (
            .Z (_N73359),
            .Z5 (N53[2]),
            .I0 (tx_bit[0]),
            .I1 (tx_bit[1]),
            .I2 (tx_bit[2]),
            .I3 (tx_shift[3]),
            .I4 (tx_shift[4]),
            .I5 (1'b1));
	// LUT = (I0&I4)|(~I0&I3) ;
	// Z5 = (I0&I1&~I2)|(~I1&I2)|(~I0&I2) ;

    GTP_LUT6D /* N56_8 */ #(
            .INIT(64'b1111111111111010111101011111000001100110011001100110011001100110))
        N56_8 (
            .Z (_N73363),
            .Z5 (N53[1]),
            .I0 (tx_bit[0]),
            .I1 (tx_bit[1]),
            .I2 (tx_bit[3]),
            .I3 (tx_shift[1]),
            .I4 (tx_shift[2]),
            .I5 (1'b1));
	// LUT = (I0&I4)|(~I0&I3)|(I2) ;
	// Z5 = I1^I0 ;

    GTP_LUT5 /* N56_9 */ #(
            .INIT(32'b11111010110010100011101000001010))
        N56_9 (
            .Z (_N73364),
            .I0 (_N73363),
            .I1 (tx_bit[0]),
            .I2 (tx_bit[2]),
            .I3 (tx_shift[5]),
            .I4 (tx_shift[6]));
	// LUT = (I0&~I2)|(~I1&I2&I3)|(I1&I2&I4) ;

    GTP_LUT6D /* N61_1_maj0_1 */ #(
            .INIT(64'b1110111011101110111011101110111000000000000000000000000000000001))
        N61_1_maj0_1 (
            .Z (_N31354),
            .Z5 (_N356506),
            .I0 (baud_count[0]),
            .I1 (baud_count[1]),
            .I2 (baud_count[5]),
            .I3 (baud_count[6]),
            .I4 (baud_count[7]),
            .I5 (1'b1));
	// LUT = (I1)|(I0) ;
	// Z5 = ~I0&~I1&~I2&~I3&~I4 ;

    GTP_LUT6 /* N61_1_maj4_1 */ #(
            .INIT(64'b1111111111111111111111111111111111111111111111111111111111111110))
        N61_1_maj4_1 (
            .Z (_N31370),
            .I0 (baud_count[0]),
            .I1 (baud_count[1]),
            .I2 (baud_count[2]),
            .I3 (baud_count[3]),
            .I4 (baud_count[4]),
            .I5 (baud_count[5]));
	// LUT = (I0)|(I1)|(I2)|(I3)|(I4)|(I5) ;

    GTP_LUT6D /* N104 */ #(
            .INIT(64'b0000000000000001000000000000000001010101010101010101010101010101))
        N104 (
            .Z (full),
            .Z5 (N98),
            .I0 (count[0]),
            .I1 (count[1]),
            .I2 (count[2]),
            .I3 (count[3]),
            .I4 (count[4]),
            .I5 (1'b1));
	// LUT = ~I0&~I1&~I2&~I3&I4 ;
	// Z5 = ~I0 ;
	// ../../rtl/soc/uart_tx_fifo.v:64

    GTP_LUT6D /* N150 */ #(
            .INIT(64'b0110011001100110011001100110011011001111110011111100111111001111))
        N150_vname (
            .Z (N150),
            .Z5 (N168[0]),
            .I0 (push),
            .I1 (pop),
            .I2 (baud_count[0]),
            .I3 (),
            .I4 (),
            .I5 (1'b1));
    // defparam N150_vname.orig_name = N150;
	// LUT = I1^I0 ;
	// Z5 = (~I2)|(I1) ;

    GTP_LUT6D /* N153_5_sum2_3 */ #(
            .INIT(64'b1010011001100101010110011001101010100101010110101010010101011010))
        N153_5_sum2_3 (
            .Z (N153[2]),
            .Z5 (N153[1]),
            .I0 (pop),
            .I1 (tx_busy),
            .I2 (count[0]),
            .I3 (count[1]),
            .I4 (count[2]),
            .I5 (1'b1));
	// LUT = (I0&~I2&~I3&~I4)|(I0&I1&~I3&~I4)|(~I0&I2&I3&~I4)|(~I0&~I1&I3&~I4)|(I0&I1&~I2&~I4)|(~I0&~I1&I2&~I4)|(~I0&~I2&~I3&I4)|(~I0&I1&~I3&I4)|(I0&I2&I3&I4)|(I0&~I1&I3&I4)|(~I0&I1&~I2&I4)|(I0&~I1&I2&I4) ;
	// Z5 = I3^I2^I0 ;

    GTP_LUT6 /* N153_5_sum3_3 */ #(
            .INIT(64'b0011011101110110111101110111010111001000100010010000100010001010))
        N153_5_sum3_3 (
            .Z (N153[3]),
            .I0 (pop),
            .I1 (tx_busy),
            .I2 (count[0]),
            .I3 (count[1]),
            .I4 (count[2]),
            .I5 (count[3]));
	// LUT = (~I0&~I4&I5)|(~I1&I2&I5)|(~I1&I3&I5)|(I0&I1&~I3&~I5)|(I0&I1&~I2&~I5)|(I2&I3&~I4&I5)|(~I0&I1&~I3&I5)|(~I0&I1&~I2&I5)|(I0&~I1&I4&I5)|(I0&~I2&~I3&~I4&~I5)|(I1&I2&I3&I4&~I5)|(~I0&~I1&~I2&~I3&I4&~I5) ;

    GTP_LUT6 /* N153_5_sum4_4 */ #(
            .INIT(64'b0111111111111111111111111111111010000000000000000000000000000000))
        N153_5_sum4_4 (
            .Z (N153[4]),
            .I0 (tx_busy),
            .I1 (count[0]),
            .I2 (count[1]),
            .I3 (count[2]),
            .I4 (count[3]),
            .I5 (count[4]));
	// LUT = (I0&~I4&I5)|(I1&~I3&I5)|(~I2&I3&I5)|(~I2&I4&I5)|(~I1&I2&I5)|(~I0&I2&I5)|(I0&I1&I2&I3&I4&~I5) ;

    GTP_LUT6D /* N163 */ #(
            .INIT(64'b1010101010100010101010101010101000111111111111111100000000000000))
        N163_vname (
            .Z (N163),
            .Z5 (N53[3]),
            .I0 (N159),
            .I1 (tx_bit[0]),
            .I2 (tx_bit[1]),
            .I3 (tx_bit[2]),
            .I4 (tx_bit[3]),
            .I5 (1'b1));
    // defparam N163_vname.orig_name = N163;
	// LUT = (I0&~I4)|(I0&I3)|(I0&I2)|(I0&~I1) ;
	// Z5 = (I1&I2&I3&~I4)|(~I3&I4)|(~I2&I4)|(~I1&I4) ;

    GTP_LUT2 /* N164 */ #(
            .INIT(4'b1110))
        N164_vname (
            .Z (N164),
            .I0 (pop),
            .I1 (N25));
    // defparam N164_vname.orig_name = N164;
	// LUT = (I0)|(I1) ;
	// ../../rtl/soc/uart_tx_fifo.v:58

    GTP_LUT6 /* N167 */ #(
            .INIT(64'b1111111111111111111111111111111111111111111111111111111111111110))
        N167_vname (
            .Z (N167),
            .I0 (tx_busy),
            .I1 (count[0]),
            .I2 (count[1]),
            .I3 (count[2]),
            .I4 (count[3]),
            .I5 (count[4]));
    // defparam N167_vname.orig_name = N167;
	// LUT = (I0)|(I1)|(I2)|(I3)|(I4)|(I5) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6D /* \N168[1]  */ #(
            .INIT(64'b0100000101000001010000010100000101010101000000000000000001010101))
        \N168[1]  (
            .Z (N168[1]),
            .Z5 (N168[6]),
            .I0 (N194),
            .I1 (baud_count[0]),
            .I2 (baud_count[1]),
            .I3 (baud_count[6]),
            .I4 (_N31370),
            .I5 (1'b1));
	// LUT = (~I0&~I1&~I2)|(~I0&I1&I2) ;
	// Z5 = (~I0&~I3&~I4)|(~I0&I3&I4) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6D /* \N168[2]  */ #(
            .INIT(64'b1111111010101011111111101010101111111111111111101010101010101011))
        \N168[2]  (
            .Z (N168[2]),
            .Z5 (N168[3]),
            .I0 (N194),
            .I1 (baud_count[0]),
            .I2 (baud_count[1]),
            .I3 (baud_count[2]),
            .I4 (baud_count[3]),
            .I5 (1'b1));
	// LUT = (~I1&~I2&~I3)|(I2&I3)|(I1&I3)|(I0) ;
	// Z5 = (~I1&~I2&~I3&~I4)|(I3&I4)|(I2&I4)|(I1&I4)|(I0) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6 /* \N168[4]  */ #(
            .INIT(64'b0101010101010101010101010101010000000000000000000000000000000001))
        \N168[4]  (
            .Z (N168[4]),
            .I0 (N194),
            .I1 (baud_count[0]),
            .I2 (baud_count[1]),
            .I3 (baud_count[2]),
            .I4 (baud_count[3]),
            .I5 (baud_count[4]));
	// LUT = (~I0&I1&I5)|(~I0&I2&I5)|(~I0&I3&I5)|(~I0&I4&I5)|(~I0&~I1&~I2&~I3&~I4&~I5) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6 /* \N168[5]  */ #(
            .INIT(64'b1111111111111111101010101010101011111111111111101010101010101011))
        \N168[5]  (
            .Z (N168[5]),
            .I0 (N194),
            .I1 (baud_count[2]),
            .I2 (baud_count[3]),
            .I3 (baud_count[4]),
            .I4 (baud_count[5]),
            .I5 (_N31354));
	// LUT = (I0)|(I1&I4)|(I2&I4)|(I3&I4)|(I4&I5)|(~I1&~I2&~I3&~I4&~I5) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6D /* \N168[7]  */ #(
            .INIT(64'b1111101011111010111010111110101111111111101010101111111010101011))
        \N168[7]  (
            .Z (N168[7]),
            .Z5 (N168[8]),
            .I0 (N194),
            .I1 (baud_count[6]),
            .I2 (baud_count[7]),
            .I3 (baud_count[8]),
            .I4 (_N31370),
            .I5 (1'b1));
	// LUT = (~I1&~I2&~I4)|(I2&I4)|(I1&I2)|(I0) ;
	// Z5 = (~I1&~I2&~I3&~I4)|(I3&I4)|(I2&I3)|(I1&I3)|(I0) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6 /* N177_1 */ #(
            .INIT(64'b0000000000000000000000000000001000000000000000000000000000000000))
        N177_1 (
            .Z (N159),
            .I0 (tx_busy),
            .I1 (baud_count[2]),
            .I2 (baud_count[3]),
            .I3 (baud_count[4]),
            .I4 (baud_count[8]),
            .I5 (_N356506));
	// LUT = I0&~I1&~I2&~I3&~I4&I5 ;

    GTP_LUT6 /* N178 */ #(
            .INIT(64'b1111111111111111111111111111111100000000000010000000000000000000))
        N178_vname (
            .Z (N178),
            .I0 (N159),
            .I1 (tx_bit[0]),
            .I2 (tx_bit[1]),
            .I3 (tx_bit[2]),
            .I4 (tx_bit[3]),
            .I5 (N25));
    // defparam N178_vname.orig_name = N178;
	// LUT = (I5)|(I0&I1&~I2&~I3&I4) ;
	// ../../rtl/soc/uart_tx_fifo.v:60

    GTP_LUT6 /* N190 */ #(
            .INIT(64'b0000000010101010000000001111000000000000110011000000000011110000))
        N190_vname (
            .Z (N190),
            .I0 (_N73358),
            .I1 (_N73359),
            .I2 (_N73364),
            .I3 (pop),
            .I4 (tx_bit[1]),
            .I5 (tx_bit[2]));
    // defparam N190_vname.orig_name = N190;
	// LUT = (I2&~I3&~I4)|(I1&~I3&I4&~I5)|(I0&~I3&I4&I5) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6D /* \N191_5[1]  */ #(
            .INIT(64'b0111100001111000011110000111100001111111111111111000000000000000))
        \N191_5[1]  (
            .Z (N191[1]),
            .Z5 (N191[3]),
            .I0 (pop),
            .I1 (rd_ptr[0]),
            .I2 (rd_ptr[1]),
            .I3 (rd_ptr[2]),
            .I4 (rd_ptr[3]),
            .I5 (1'b1));
	// LUT = (I0&I1&~I2)|(~I1&I2)|(~I0&I2) ;
	// Z5 = (I0&I1&I2&I3&~I4)|(~I3&I4)|(~I2&I4)|(~I1&I4)|(~I0&I4) ;

    GTP_LUT6D /* \N191_5[2]  */ #(
            .INIT(64'b0111111110000000011111111000000001100110011001100110011001100110))
        \N191_5[2]  (
            .Z (N191[2]),
            .Z5 (N191[0]),
            .I0 (pop),
            .I1 (rd_ptr[0]),
            .I2 (rd_ptr[1]),
            .I3 (rd_ptr[2]),
            .I4 (),
            .I5 (1'b1));
	// LUT = (I0&I1&I2&~I3)|(~I2&I3)|(~I1&I3)|(~I0&I3) ;
	// Z5 = I1^I0 ;

    GTP_LUT6 /* N194 */ #(
            .INIT(64'b1010101010101010101010101010101110101010101010101010101010101010))
        N194_vname (
            .Z (N194),
            .I0 (pop),
            .I1 (baud_count[2]),
            .I2 (baud_count[3]),
            .I3 (baud_count[4]),
            .I4 (baud_count[8]),
            .I5 (_N356506));
    // defparam N194_vname.orig_name = N194;
	// LUT = (I0)|(~I1&~I2&~I3&~I4&I5) ;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[0]  (
            .Q (baud_count[0]),
            .CE (N167),
            .CLK (clk),
            .D (N168[0]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[1]  (
            .Q (baud_count[1]),
            .CE (N167),
            .CLK (clk),
            .D (N168[1]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[2]  (
            .Q (baud_count[2]),
            .CE (N167),
            .CLK (clk),
            .D (N168[2]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[3]  (
            .Q (baud_count[3]),
            .CE (N167),
            .CLK (clk),
            .D (N168[3]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[4]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[4]  (
            .Q (baud_count[4]),
            .CE (N167),
            .CLK (clk),
            .D (N168[4]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[5]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[5]  (
            .Q (baud_count[5]),
            .CE (N167),
            .CLK (clk),
            .D (N168[5]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[6]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[6]  (
            .Q (baud_count[6]),
            .CE (N167),
            .CLK (clk),
            .D (N168[6]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[7]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[7]  (
            .Q (baud_count[7]),
            .CE (N167),
            .CLK (clk),
            .D (N168[7]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \baud_count[8]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \baud_count[8]  (
            .Q (baud_count[8]),
            .CE (N167),
            .CLK (clk),
            .D (N168[8]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \count[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \count[0]  (
            .Q (count[0]),
            .CE (N150),
            .CLK (clk),
            .D (N98),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \count[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \count[1]  (
            .Q (count[1]),
            .CE (N150),
            .CLK (clk),
            .D (N153[1]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \count[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \count[2]  (
            .Q (count[2]),
            .CE (N150),
            .CLK (clk),
            .D (N153[2]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \count[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \count[3]  (
            .Q (count[3]),
            .CE (N150),
            .CLK (clk),
            .D (N153[3]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \count[4]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \count[4]  (
            .Q (count[4]),
            .CE (N150),
            .CLK (clk),
            .D (N153[4]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_RAM32X2DP /* fifo_0 */ #(
            .INIT_0(32'b00000000000000000000000000000000), 
            .INIT_1(32'b00000000000000000000000000000000))
        fifo_0 (
            .DO ({N39[1], N39[0]}),
            .DI ({push_data[1], push_data[0]}),
            .RADDR ({1'b0, _N29743, _N29742, _N29741, _N29740}),
            .WADDR ({1'b0, fifo_write_address[3], fifo_write_address[2], fifo_write_address[1], fifo_write_address[0]}),
            .WCLK (clk),
            .WE (push));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_RAM32X2DP /* fifo_1 */ #(
            .INIT_0(32'b00000000000000000000000000000000), 
            .INIT_1(32'b00000000000000000000000000000000))
        fifo_1 (
            .DO ({N39[3], N39[2]}),
            .DI ({push_data[3], push_data[2]}),
            .RADDR ({1'b0, _N29743, _N29742, _N29741, _N29740}),
            .WADDR ({1'b0, fifo_write_address[3], fifo_write_address[2], fifo_write_address[1], fifo_write_address[0]}),
            .WCLK (clk),
            .WE (push));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_RAM32X2DP /* fifo_2 */ #(
            .INIT_0(32'b00000000000000000000000000000000), 
            .INIT_1(32'b00000000000000000000000000000000))
        fifo_2 (
            .DO ({N39[5], N39[4]}),
            .DI ({push_data[5], push_data[4]}),
            .RADDR ({1'b0, _N29743, _N29742, _N29741, _N29740}),
            .WADDR ({1'b0, fifo_write_address[3], fifo_write_address[2], fifo_write_address[1], fifo_write_address[0]}),
            .WCLK (clk),
            .WE (push));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_RAM32X2DP /* fifo_3 */ #(
            .INIT_0(32'b00000000000000000000000000000000), 
            .INIT_1(32'b00000000000000000000000000000000))
        fifo_3 (
            .DO ({N39[7], N39[6]}),
            .DI ({push_data[7], push_data[6]}),
            .RADDR ({1'b0, _N29743, _N29742, _N29741, _N29740}),
            .WADDR ({1'b0, fifo_write_address[3], fifo_write_address[2], fifo_write_address[1], fifo_write_address[0]}),
            .WCLK (clk),
            .WE (push));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_R /* \fifo_addrreg_1[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \fifo_addrreg_1[0]  (
            .Q (_N29740),
            .CLK (clk),
            .D (N191[0]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));

    GTP_DFF_R /* \fifo_addrreg_1[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \fifo_addrreg_1[1]  (
            .Q (_N29741),
            .CLK (clk),
            .D (N191[1]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));

    GTP_DFF_R /* \fifo_addrreg_1[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \fifo_addrreg_1[2]  (
            .Q (_N29742),
            .CLK (clk),
            .D (N191[2]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));

    GTP_DFF_R /* \fifo_addrreg_1[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \fifo_addrreg_1[3]  (
            .Q (_N29743),
            .CLK (clk),
            .D (N191[3]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));

    GTP_DFF_RE /* \rd_ptr[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \rd_ptr[0]  (
            .Q (rd_ptr[0]),
            .CE (pop),
            .CLK (clk),
            .D (N42[0]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \rd_ptr[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \rd_ptr[1]  (
            .Q (rd_ptr[1]),
            .CE (pop),
            .CLK (clk),
            .D (N42[1]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \rd_ptr[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \rd_ptr[2]  (
            .Q (rd_ptr[2]),
            .CE (pop),
            .CLK (clk),
            .D (N42[2]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \rd_ptr[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \rd_ptr[3]  (
            .Q (rd_ptr[3]),
            .CE (pop),
            .CLK (clk),
            .D (N42[3]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* tx */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        tx_vname (
            .Q (tx),
            .CE (N189_1),
            .CLK (clk),
            .D (N190),
            .S (N178));
    // defparam tx_vname.orig_name = tx;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \tx_bit[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \tx_bit[0]  (
            .Q (tx_bit[0]),
            .CE (N163),
            .CLK (clk),
            .D (N53[0]),
            .R (N164));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \tx_bit[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \tx_bit[1]  (
            .Q (tx_bit[1]),
            .CE (N163),
            .CLK (clk),
            .D (N53[1]),
            .R (N164));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \tx_bit[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \tx_bit[2]  (
            .Q (tx_bit[2]),
            .CE (N163),
            .CLK (clk),
            .D (N53[2]),
            .R (N164));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \tx_bit[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \tx_bit[3]  (
            .Q (tx_bit[3]),
            .CE (N163),
            .CLK (clk),
            .D (N53[3]),
            .R (N164));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF /* tx_busy */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        tx_busy_vname (
            .Q (tx_busy),
            .CLK (clk),
            .D (_N353009));
    // defparam tx_busy_vname.orig_name = tx_busy;
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_LUT6D /* tx_ce_fix_2 */ #(
            .INIT(64'b1111111111111010111111111111101000001100000011000000110000001100))
        tx_ce_fix_2 (
            .Z (N189_1),
            .Z5 (_N353009),
            .I0 (N159),
            .I1 (N167),
            .I2 (N178),
            .I3 (pop),
            .I4 (),
            .I5 (1'b1));
	// LUT = (I3)|(I2)|(I0) ;
	// Z5 = I1&~I2 ;

    GTP_DFF_SE /* \tx_shift[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[0]  (
            .Q (tx_shift[0]),
            .CE (pop),
            .CLK (clk),
            .D (1'b0),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[1]  (
            .Q (tx_shift[1]),
            .CE (pop),
            .CLK (clk),
            .D (N39[0]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[2]  (
            .Q (tx_shift[2]),
            .CE (pop),
            .CLK (clk),
            .D (N39[1]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[3]  (
            .Q (tx_shift[3]),
            .CE (pop),
            .CLK (clk),
            .D (N39[2]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[4]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[4]  (
            .Q (tx_shift[4]),
            .CE (pop),
            .CLK (clk),
            .D (N39[3]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[5]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[5]  (
            .Q (tx_shift[5]),
            .CE (pop),
            .CLK (clk),
            .D (N39[4]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[6]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[6]  (
            .Q (tx_shift[6]),
            .CE (pop),
            .CLK (clk),
            .D (N39[5]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[7]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[7]  (
            .Q (tx_shift[7]),
            .CE (pop),
            .CLK (clk),
            .D (N39[6]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_SE /* \tx_shift[8]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b1))
        \tx_shift[8]  (
            .Q (tx_shift[8]),
            .CE (pop),
            .CLK (clk),
            .D (N39[7]),
            .S (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \wr_ptr[0]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \wr_ptr[0]  (
            .Q (pad_address_in[0]),
            .CE (push),
            .CLK (clk),
            .D (N36[0]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \wr_ptr[1]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \wr_ptr[1]  (
            .Q (pad_address_in[1]),
            .CE (push),
            .CLK (clk),
            .D (N36[1]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \wr_ptr[2]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \wr_ptr[2]  (
            .Q (pad_address_in[2]),
            .CE (push),
            .CLK (clk),
            .D (N36[2]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    GTP_DFF_RE /* \wr_ptr[3]  */ #(
            .GRS_EN("TRUE"), 
            .INIT(1'b0))
        \wr_ptr[3]  (
            .Q (pad_address_in[3]),
            .CE (push),
            .CLK (clk),
            .D (N36[3]),
            .R (\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 ));
	// ../../rtl/soc/uart_tx_fifo.v:68

    (* PAP_DONT_TOUCH *) GTP_LUT6D /* \write_address_pad[0].u_hold_dual_lut  */ #(
            .INIT(64'b1100110011001100110011001100110010101010101010101010101010101010))
        \write_address_pad[0].u_hold_dual_lut  (
            .Z (fifo_write_address[1]),
            .Z5 (fifo_write_address[0]),
            .I0 (pad_address_in[0]),
            .I1 (pad_address_in[1]),
            .I2 (1'b0),
            .I3 (1'b0),
            .I4 (1'b0),
            .I5 (1'b1));
	// LUT = (I0&~I5)|(I1&I5) ;
	// Z5 = I0 ;
	// ../../rtl/soc/uart_tx_fifo.v:43

    (* PAP_DONT_TOUCH *) GTP_LUT6D /* \write_address_pad[1].u_hold_dual_lut  */ #(
            .INIT(64'b1100110011001100110011001100110010101010101010101010101010101010))
        \write_address_pad[1].u_hold_dual_lut  (
            .Z (fifo_write_address[3]),
            .Z5 (fifo_write_address[2]),
            .I0 (pad_address_in[2]),
            .I1 (pad_address_in[3]),
            .I2 (1'b0),
            .I3 (1'b0),
            .I4 (1'b0),
            .I5 (1'b1));
	// LUT = (I0&~I5)|(I1&I5) ;
	// Z5 = I0 ;
	// ../../rtl/soc/uart_tx_fifo.v:43


endmodule