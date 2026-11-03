`timescale 1ns / 1ps

`define UD #1

module rgmii_interface(
    input        rst,
    input        rx_restart,
    input        speed_100,
    output       rgmii_clk/*synthesis PAP_MARK_DEBUG="1"*/,
    input        rgmii_clk_90p,
    input [7:0]  tx_delay_step,
    input [7:0]  rx_delay_step,
    
    input        mac_tx_data_valid/*synthesis PAP_MARK_DEBUG="1"*/,
    input [7:0]  mac_tx_data/*synthesis PAP_MARK_DEBUG="1"*/,
    output       mac_tx_ready,
    
    output reg       mac_rx_error/*synthesis PAP_MARK_DEBUG="1"*/,
    output reg       mac_rx_data_valid/*synthesis PAP_MARK_DEBUG="1"*/,
    output reg       mac_rx_byte_valid,
    output reg [7:0] mac_rx_data/*synthesis PAP_MARK_DEBUG="1"*/,
    
    input        rgmii_rxc/*synthesis PAP_MARK_DEBUG="1"*/,
    input        rgmii_rx_ctl/*synthesis PAP_MARK_DEBUG="1"*/,
    input [3:0]  rgmii_rxd/*synthesis PAP_MARK_DEBUG="1"*/,
                 
    output       rgmii_txc/*synthesis PAP_MARK_DEBUG="1"*/,
    output       rgmii_tx_ctl/*synthesis PAP_MARK_DEBUG="1"*/,
    output [3:0] rgmii_txd/*synthesis PAP_MARK_DEBUG="1"*/ 
);

//=============================================================
//  RGMII TX 
//=============================================================
    // Gigabit RGMII transfers a complete byte per 125 MHz cycle.  In
    // 100-Mbit mode the PHY exposes the MII nibble stream at 25 MHz and the
    // falling edge duplicates the rising-edge nibble.  Hold each MAC byte
    // for two clocks.  Acknowledge it when its low nibble starts so a
    // registered MAC producer has the following high-nibble cycle to put
    // the next byte on the bus.
    reg tx_half;
    always @(posedge rgmii_clk or posedge rst) begin
        if (rst || !mac_tx_data_valid)
            tx_half <= 1'b0;
        else if (speed_100)
            tx_half <= ~tx_half;
        else
            tx_half <= 1'b0;
    end
    assign mac_tx_ready = !speed_100 || !tx_half;
    wire [3:0] tx_nibble = tx_half ? mac_tx_data[7:4]
                                   : mac_tx_data[3:0];

    wire       rgmii_txc_obuf;
    wire       rgmii_txc_tbuf;
    wire       rgmii_tx_ctl_obuf;
    wire       rgmii_tx_ctl_tbuf;
    wire [3:0] rgmii_txd_obuf;
    wire [3:0] rgmii_txd_tbuf;

    generate 
        genvar i;
        for (i=0; i<4; i=i+1) 
        begin : rgmii_tx_data  
            GTP_ODDR_E1 #(
                .GRS_EN    (  "TRUE"             ),                 
                .ODDR_MODE (  "SAME_EDGE"        ),                 
                .RS_TYPE   (  "ASYNC_RESET"      )                  
            ) rgmii_txd_ddr(                                        
                .Q         (  rgmii_txd_obuf[i]  ),// OUTPUT            
                .CE        (  1'b1               ),// INPUT           
                .CLK       (  rgmii_clk          ),// INPUT           
                .D0        (  speed_100 ? tx_nibble[i] : mac_tx_data[i]   ),// INPUT
                .D1        (  speed_100 ? tx_nibble[i] : mac_tx_data[i+4] ),// INPUT
                .RS        (  rst                ) // INPUT           
            );      
            
           GTP_OUTBUF #(
            .IOSTANDARD ("LVCMOS33"),
            .SLEW_RATE ("FAST"),
            .DRIVE_STRENGTH ("4")
          )u_rgmii_txd_obuf (
            .I (rgmii_txd_obuf[i]),
            .O (rgmii_txd[i]     ) 
          );

        end
    endgenerate
    
    GTP_ODDR_E1 #(
        .GRS_EN    (  "TRUE"                    ),
        .ODDR_MODE (  "SAME_EDGE"               ),
        .RS_TYPE   (  "ASYNC_RESET"             ) 
    ) rgmii_tdv_ddr(
        .Q         (  rgmii_tx_ctl_obuf         ),// OUTPUT    
        .CE        (  1'b1                      ),// INPUT   
        .CLK       (  rgmii_clk                 ),// INPUT   
        .D0        (  mac_tx_data_valid         ),// INPUT   
        .D1        (  mac_tx_data_valid ^ 1'b0  ),// INPUT   
        .RS        (  rst                       ) // INPUT   
    );                                       
    
   GTP_OUTBUF#(
      .IOSTANDARD ("LVCMOS33"),
      .SLEW_RATE ("FAST"),
      .DRIVE_STRENGTH ("4")
   ) u_rgmii_tx_ctl_obuf (
      .I (rgmii_tx_ctl_obuf),
      .O (rgmii_tx_ctl) 
   );
    
   GTP_ODDR_E1 #(
        .GRS_EN    (  "TRUE"          ),
        .ODDR_MODE (  "SAME_EDGE"     ),
        .RS_TYPE   (  "ASYNC_RESET"   ) 
   ) rgmii_txc_ddr(
        .Q         (  rgmii_txc_obuf  ),// OUTPUT    
        .CE        (  1'b1            ),// INPUT   
        .CLK       (  rgmii_clk       ),// INPUT   
        .D0        (  1'b1            ),// INPUT   
        .D1        (  1'b0            ),// INPUT   
        .RS        (  rst             ) // INPUT   
   );
    
    wire [7:0] delay_step_c ;
    wire [7:0] delay_step_clk ;
    wire       rgmii_txc_dly;
    
    // PG2L100H output IOLDELAY permits only its single delay chain in PDS25.
    // Keep the software unit (two 5 ps taps) and the default100 delay: double
    // the binary step before Gray encoding. Single-chain maximum is247 taps,
    // so the highest whole software unit is123. Clamp direct wrapper callers
    // too; eth_mac_mmio reads back the same effective limited setting.
    wire [7:0] tx_delay_effective = tx_delay_step > 8'd123 ? 8'd123 : tx_delay_step;
    assign delay_step_c = {tx_delay_effective[6:0], 1'b0};
    
    assign delay_step_clk=((delay_step_c>>1)^delay_step_c);  // only support gray code
    
    GTP_IODELAY_E2 #(
        .DELAY_STEP_SEL ("PORT"),//PORT PARAMETER
        .DELAY_STEP_VALUE(8'd0)
    ) tx_clk_delay (
        .DI            (  rgmii_txc_obuf  ),// rx clk input                      
        .DELAY_SEL     (  1'b0            ),
        .DELAY_STEP    (  delay_step_clk  ),                                    
        .DO            (  rgmii_txc_dly   ),// rx clk output                    
        .EN_N          (  1'b0            ) // INPUT                            
    );                                                                                                            
    
   GTP_OUTBUF#(
        .IOSTANDARD ("LVCMOS33"),
        .SLEW_RATE ("FAST"),
        .DRIVE_STRENGTH ("4")
   ) u_rgmii_txc_obuf (
       .I (rgmii_txc_dly),
       .O (rgmii_txc) 
);

//=============================================================
//  RGMII RX 
//=============================================================
    wire        rgmii_rxc_ibuf;
    wire        rgmii_rxc_dly;
    wire        rgmii_rx_ctl_ibuf;
    wire [3:0]  rgmii_rxd_ibuf;

    wire [7:0] delay_step_b ;
    wire [7:0] delay_step_gray ;
    
    assign delay_step_b = rx_delay_step;   // 0~247, approximately 10 ps/step
    
    assign delay_step_gray=((delay_step_b>>1)^delay_step_b);  // only support gray code
    
//    GTP_INBUF #(
//        .IOSTANDARD("DEFAULT"),
//        .TERM_DDR("ON")
//    ) u_rgmii_rxc_ibuf (
//        .O(rgmii_rxc_ibuf),// OUTPUT  
//        .I(rgmii_rxc) // INPUT  
//    );
    
    parameter DELAY_STEP = 8'hE6;
//    
//    GTP_IODELAY_E2 #(
//        .DELAY_STEP_VALUE   (  DELAY_STEP          ),
//        .DELAY_STEP_SEL     (  "PARAMETER"              ),
//        .TDELAY_EN          (  "FALSE"             )
//    ) GTP_IODELAY_E2_inst0 (                                                             
//        .DI                  (  rgmii_rxc_ibuf     ),// rx clk input                      
//        .DELAY_SEL           (  1'b1               ),                                    
//        .DELAY_STEP          (  delay_step_gray    ),                                    
//        .DO                  (  rgmii_rxc_dly    ),// rx clk output 
//        .EN_N                (  1'b0               )                   
//    );

    GTP_CLKBUFG GTP_CLKBUFG_RXSHFT(
        .CLKIN     (rgmii_rxc),//rgmii_rxc_ibuf
        .CLKOUT    (rgmii_clk)
    );

    GTP_INBUF #(
        .IOSTANDARD("LVCMOS33"),
        .TERM_DDR()
    ) u_rgmii_rx_ctl_ibuf (
        .O(rgmii_rx_ctl_ibuf),// OUTPUT  
        .I(rgmii_rx_ctl) // INPUT  
    );
    
    wire  rgmii_rx_ctl_delay;

    GTP_IODELAY_E2 #(
        .DELAY_STEP_VALUE(  DELAY_STEP          ),
        .DELAY_STEP_SEL  (  "PORT"              ),
        .TDELAY_EN       (  "FALSE"             )
    ) delay_rgmii_rx_ctl (
        .DELAY_STEP      (  delay_step_gray     ),// INPUT[7:0]         
        .DO              (  rgmii_rx_ctl_delay  ),// OUTPUT             
        .DELAY_SEL       (  1'b1                ),// INPUT              
        .DI              (  rgmii_rx_ctl_ibuf   ),// INPUT              
        .EN_N            (  1'b0                ) // INPUT              
    );

    wire       gmii_ctl;
    wire       rgmii_rx_valid_xor_error;
    GTP_IDDR_E1 #(
        .GRS_EN       (  "TRUE"                    ),
        .IDDR_MODE    (  "SAME_PIPELINED"          ),
        .RS_TYPE      (  "SYNC_RESET"              )
    ) rgmii_rx_ctl_in (  
        .Q0           (  gmii_ctl                  ), // OUTPUT  
        .Q1           (  rgmii_rx_valid_xor_error  ), // OUTPUT  
        .CE           (  1'b1                      ), // INPUT  
        .CLK          (  rgmii_clk                 ),// INPUT  
        .D            (  rgmii_rx_ctl_delay        ),  // INPUT  
        .RS           (  rst | rx_restart          )  // INPUT  
    );
    
    wire [5:0] rx_ctl_nc;
    
    wire [3:0] rgmii_rxd_delay;
    wire [23:0] rxd_nc;
    wire [7:0]  gmii_rxd;
    reg          rx_half;
    reg          rx_frame_started;
    reg [3:0]    rx_low_nibble;
    always @(posedge rgmii_clk)
    begin
        if (rst || rx_restart) begin
            mac_rx_data <= 8'h00;
            mac_rx_data_valid <= 1'b0;
            mac_rx_byte_valid <= 1'b0;
            mac_rx_error <= 1'b0;
            rx_half <= 1'b0;
            rx_frame_started <= 1'b0;
            rx_low_nibble <= 4'h0;
        end else begin
            mac_rx_byte_valid <= 1'b0;
            mac_rx_error <= gmii_ctl ^ rgmii_rx_valid_xor_error;
            if (!gmii_ctl) begin
                rx_half <= 1'b0;
                rx_frame_started <= 1'b0;
                mac_rx_data_valid <= 1'b0;
            end else if (speed_100) begin
                if (!rx_half) begin
                    rx_low_nibble <= gmii_rxd[3:0];
                    rx_half <= 1'b1;
                    // Do not expose RX_DV before the first complete byte.
                    // The MAC uses the RX_DV rising edge to discard the first
                    // preamble byte; asserting it on the first nibble would
                    // shift every 100-Mbit frame by one byte.
                    mac_rx_data_valid <= rx_frame_started;
                end else begin
                    mac_rx_data <= {gmii_rxd[3:0],rx_low_nibble};
                    mac_rx_byte_valid <= 1'b1;
                    rx_half <= 1'b0;
                    rx_frame_started <= 1'b1;
                    mac_rx_data_valid <= 1'b1;
                end
            end else begin
                mac_rx_data <= gmii_rxd;
                mac_rx_byte_valid <= gmii_ctl;
                mac_rx_data_valid <= gmii_ctl;
                rx_half <= 1'b0;
                rx_frame_started <= gmii_ctl;
            end
        end
    end

    generate 
        genvar j;
        for (j=0; j<4; j=j+1)
        begin : rgmii_rx_data

            GTP_INBUF #(
                .IOSTANDARD("LVCMOS33"),
                .TERM_DDR()
            ) u_rgmii_rxd_ibuf (
                .O(rgmii_rxd_ibuf[j]),// OUTPUT  
                .I(rgmii_rxd[j]) // INPUT  
            );

            GTP_IODELAY_E2 #(
                .DELAY_STEP_VALUE(  DELAY_STEP          ),
                .DELAY_STEP_SEL  (  "PORT"              ),
                .TDELAY_EN       (  "FALSE"             )
            ) delay_rgmii_rxd (
                .DELAY_STEP      (  delay_step_gray     ),// INPUT[7:0]         
                .DO              (  rgmii_rxd_delay[j]  ),// OUTPUT             
                .DELAY_SEL       (  1'b1                ),// INPUT              
                .DI              (  rgmii_rxd_ibuf[j]   ),// INPUT              
                .EN_N            (  1'b0                ) // INPUT              
            );

            GTP_IDDR_E1 #(
                .GRS_EN           (  "TRUE"             ),
                .IDDR_MODE        (  "SAME_PIPELINED"   ),
                .RS_TYPE          (  "ASYNC_RESET"      ) 
            ) rgmii_rx_ctl_in     (
                .Q0               (  gmii_rxd[j]        ),// OUTPUT     
                .Q1               (  gmii_rxd[j+4]      ),// OUTPUT     
                .CE               (  1'b1               ),// INPUT      
                .CLK              (  rgmii_clk          ),// INPUT      
                .D                (  rgmii_rxd_delay[j] ),// INPUT      
                .RS               (  rst | rx_restart   ) // INPUT      
            );
        end
    endgenerate

    
endmodule
