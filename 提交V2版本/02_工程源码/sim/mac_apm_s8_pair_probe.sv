// Standalone arithmetic research. Not connected to the SoC/PDS source list.
// One 25x18 multiply plus the APM postadder computes two exact S8 products.
module mac_apm_s8_pair_probe(
    input wire clk,resetn,en,pack_mode,
    input wire signed [17:0] activation,weight_lo,
    input wire signed [7:0] weight_hi,
    output wire signed [15:0] product_lo,product_hi,
    output wire signed [47:0] raw_product,
    output reg valid
);
    // A = signed(w_hi)*2^17 + unsigned(w_lo).
    // P = A*x + 32768 - (w_lo[7] ? x*256 : 0)
    //   = signed(w_hi)*x*2^17 + signed(w_lo)*x + 32768.
    // The biased low term is in [16512,49152], so it cannot carry or borrow
    // into the high term, including (-128)*(-128). Removing 32768 flips bit15.
    wire [24:0] packed_weight={weight_hi,9'b0,weight_lo[7:0]};
    wire [24:0] wide_weight={{7{weight_lo[17]}},weight_lo};
    wire [24:0] selected_weight=pack_mode ? packed_weight : wide_weight;
    wire [17:0] selected_activation=pack_mode ? {{10{activation[7]}},activation[7:0]} : activation;
    reg pack_r,low_sign_r;
    reg [8:0] low_bias_r;
    wire [8:0] selected_bias=low_sign_r ? low_bias_r : 9'd128;
    wire [47:0] correction={31'b0,selected_bias,8'b0};
    wire [47:0] result;
    always @(posedge clk) begin
        if(!resetn) begin
            valid<=0;pack_r<=0;low_sign_r<=0;low_bias_r<=9'd128;
        end else begin
            valid<=en;
            if(en) begin
                pack_r<=pack_mode;low_sign_r<=weight_lo[7];
                low_bias_r<=9'd128-{activation[7],activation[7:0]};
            end
        end
    end
    GTP_APM_E2 #(.GRS_EN("FALSE"),.USE_POSTADD(1),.USE_PREADD(0),.USE_MULT(1),
        .X_REG(1),.Y_REG(1),.Z_REG(0),.MULT_REG(0),.P_REG(0),.CPO_REG(0),
        .MODEIN_REG(0),.MODEY_REG(0),.MODEZ_REG(0),.USE_SIMD(0),.ASYNC_RST(0)) apm (
        .CLK(clk),.X({{5{selected_weight[24]}},selected_weight}),.Y(selected_activation),
        .XB(25'b0),.CXI(30'b0),.CXBI(25'b0),.Z(correction),.CPI(48'b0),.CIN(1'b0),
        .MODEY(3'b001),.MODEZ(pack_r ? 4'b0010 : 4'b0000),.MODEIN(5'b00010),
        .CEX1(en),.CEX2(en),.CEX3(en),.CEXB(1'b0),.CEY1(en),.CEY2(en),
        .CEZ(1'b0),.CEPRE(1'b0),.CEM(1'b0),.CEP(1'b0),
        .CEMODEY(1'b0),.CEMODEZ(1'b0),.CEMODEIN(1'b0),
        .RSTX(!resetn),.RSTXB(!resetn),.RSTY(!resetn),.RSTZ(!resetn),
        .RSTPRE(!resetn),.RSTM(!resetn),.RSTP(!resetn),
        .RSTMODEY(!resetn),.RSTMODEZ(!resetn),.RSTMODEIN(!resetn),
        .CPO(),.P(result),.COUT(),.CXO(),.CXBO());
    assign raw_product=result;
    assign product_lo=pack_r ? {~result[15],result[14:0]} : result[15:0];
    assign product_hi=pack_r ? result[32:17] : 16'b0;
endmodule
