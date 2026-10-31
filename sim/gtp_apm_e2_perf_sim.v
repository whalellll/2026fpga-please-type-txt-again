`timescale 1ns / 1ps

// Cycle model for the GTP_APM_E2 configurations emitted by MacAccelCore.
// This file is simulation-only and is never included in the PDS project.
module GTP_APM_E2 #(
    parameter GRS_EN = "TRUE",
    parameter USE_POSTADD = 0,
    parameter USE_PREADD = 0,
    parameter PREADD_REG = 0,
    parameter X_REG = 0,
    parameter CXO_REG = 0,
    parameter XB_REG = 0,
    parameter Y_REG = 0,
    parameter Z_REG = 0,
    parameter MULT_REG = 0,
    parameter P_REG = 0,
    parameter MODEY_REG = 0,
    parameter MODEZ_REG = 0,
    parameter MODEIN_REG = 0,
    parameter USE_MULT = 1,
    parameter X_SEL = 0,
    parameter XB_SEL = 0,
    parameter ASYNC_RST = 0,
    parameter USE_SIMD = 0,
    parameter [47:0] P_INIT0 = 48'b0,
    parameter [47:0] P_INIT1 = 48'b0,
    parameter ROUNDMODE_SEL = 0,
    parameter CPO_REG = 0,
    parameter USE_ACCLOW = 0,
    parameter CIN_SEL = 0
) (
    output wire [47:0] P,
    output wire [47:0] CPO,
    output wire        COUT,
    output wire [29:0] CXO,
    output wire [24:0] CXBO,
    input  wire [29:0] X,
    input  wire [29:0] CXI,
    input  wire [24:0] CXBI,
    input  wire [24:0] XB,
    input  wire [17:0] Y,
    input  wire [47:0] Z,
    input  wire [47:0] CPI,
    input  wire        CIN,
    input  wire [2:0]  MODEY,
    input  wire [3:0]  MODEZ,
    input  wire [4:0]  MODEIN,
    input  wire        CLK,
    input  wire        CEX1,
    input  wire        CEX2,
    input  wire        CEX3,
    input  wire        CEXB,
    input  wire        CEY1,
    input  wire        CEY2,
    input  wire        CEZ,
    input  wire        CEPRE,
    input  wire        CEM,
    input  wire        CEP,
    input  wire        CEMODEY,
    input  wire        CEMODEZ,
    input  wire        CEMODEIN,
    input  wire        RSTX,
    input  wire        RSTXB,
    input  wire        RSTY,
    input  wire        RSTZ,
    input  wire        RSTPRE,
    input  wire        RSTM,
    input  wire        RSTP,
    input  wire        RSTMODEY,
    input  wire        RSTMODEZ,
    input  wire        RSTMODEIN
);
    reg signed [29:0] x_reg;
    reg signed [17:0] y_reg;
    reg signed [47:0] p_reg;

    wire signed [47:0] product = x_reg * y_reg;
    wire signed [47:0] post_y =
        (USE_MULT != 0) ? product :
        ((MODEY[1:0] == 2'd2) ? p_reg : 48'sd0);
    wire signed [47:0] post_z =
        (MODEZ[2:0] == 3'd2) ? $signed(Z) :
        ((MODEZ[2:0] == 3'd3) ? $signed(CPI) : 48'sd0);
    wire signed [47:0] cascade_result = post_y + post_z;

    assign CPO = cascade_result;
    assign P = (P_REG != 0) ? p_reg : cascade_result;
    assign COUT = 1'b0;
    assign CXO = 30'b0;
    assign CXBO = 25'b0;

    always @(posedge CLK) begin
        if (RSTX)
            x_reg <= 30'sd0;
        else if (CEX1)
            x_reg <= $signed(X);

        if (RSTY)
            y_reg <= 18'sd0;
        else if (CEY1)
            y_reg <= $signed(Y);

        if (RSTP)
            p_reg <= 48'sd0;
        else if (CEP)
            p_reg <= cascade_result;
    end

    wire unused_inputs = &{1'b0, CXI, CXBI, XB, Z, CIN, MODEY, MODEIN,
                           CEX2, CEX3, CEXB, CEY2, CEZ, CEPRE, CEM,
                           CEMODEY, CEMODEZ, CEMODEIN, RSTXB, RSTZ, RSTPRE,
                           RSTM, RSTMODEY, RSTMODEZ, RSTMODEIN};
    wire unused_parameters = &{1'b0, USE_POSTADD != 0, USE_PREADD != 0,
                               PREADD_REG != 0, X_REG != 0, CXO_REG != 0,
                               XB_REG != 0, Y_REG != 0, Z_REG != 0,
                               MULT_REG != 0, MODEY_REG != 0,
                               MODEZ_REG != 0, MODEIN_REG != 0,
                               USE_MULT != 0, X_SEL != 0, XB_SEL != 0,
                               ASYNC_RST != 0, USE_SIMD != 0,
                               P_INIT0 != 0, P_INIT1 != 0,
                               ROUNDMODE_SEL != 0, CPO_REG != 0,
                               USE_ACCLOW != 0, CIN_SEL != 0,
                               GRS_EN == "TRUE"};
endmodule
