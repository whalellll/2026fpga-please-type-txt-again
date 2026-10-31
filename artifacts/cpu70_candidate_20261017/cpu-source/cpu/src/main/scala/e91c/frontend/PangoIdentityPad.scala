package e91c.frontend

import chisel3._

// One shared, combinational pad for the I-cache refill RAM write data.
// EmitCore appends the canonical implementation to CoreTop.sv; there is no
// companion Verilog file for a downstream project to accidentally omit.
class PangoIdentityPad extends BlackBox {
  override def desiredName: String = PangoIdentityPad.moduleName
  val io = IO(new Bundle {
    val dataIn = Input(UInt(128.W))
    val dataOut = Output(UInt(128.W))
  })
}

object PangoIdentityPad {
  val moduleName = "PangoIdentityPad"
  val verilog = """module PangoIdentityPad(
    |  input  [127:0] dataIn,
    |  output [127:0] dataOut
    |);
    |`ifdef SYNTHESIS
    |  genvar pad_pair;
    |  generate
    |    for (pad_pair = 0; pad_pair < 64; pad_pair = pad_pair + 1) begin : data_pad
    |      (* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) u_hold_dual_lut (
    |        .I0(dataIn[2*pad_pair]), .I1(dataIn[2*pad_pair+1]),
    |        .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
    |        .Z5(dataOut[2*pad_pair]), .Z(dataOut[2*pad_pair+1])
    |      );
    |    end
    |  endgenerate
    |`else
    |  assign dataOut = dataIn;
    |`endif
    |endmodule
    |""".stripMargin
}
