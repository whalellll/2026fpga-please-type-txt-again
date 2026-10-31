`timescale 1ns/1ps

module tb_ch9350_linux_no_toolbar;
    localparam integer BAUD_DIV = 8;
    reg clk = 1'b0;
    reg resetn = 1'b0;
    reg ch9350_uart_rx = 1'b1;
    wire gui_speed_2x;

    always #5 clk = ~clk;

    ch9350_hid_core #(
        .UART_BAUD_DIV(BAUD_DIV), .GUI_PROFILE(1),
        .REPEAT_DELAY_CYCLES(10000), .REPEAT_PERIOD_CYCLES(1000)
    ) dut (
        .clk(clk), .resetn(resetn), .ch9350_uart_rx(ch9350_uart_rx),
        .key_ready(1'b1), .gui_speed_2x(gui_speed_2x)
    );

    task send_byte;
        input [7:0] value;
        integer bit_index;
        begin
            @(negedge clk);
            ch9350_uart_rx = 1'b0;
            repeat (BAUD_DIV) @(posedge clk);
            for (bit_index = 0; bit_index < 8;
                 bit_index = bit_index + 1) begin
                @(negedge clk);
                ch9350_uart_rx = value[bit_index];
                repeat (BAUD_DIV) @(posedge clk);
            end
            @(negedge clk);
            ch9350_uart_rx = 1'b1;
            repeat (BAUD_DIV) @(posedge clk);
        end
    endtask

    task send_mouse;
        input [7:0] buttons;
        input [7:0] dx;
        input [7:0] dy;
        begin
            send_byte(8'h57); send_byte(8'hab); send_byte(8'h02);
            send_byte(buttons); send_byte(dx); send_byte(dy); send_byte(8'h00);
            repeat (4) @(posedge clk);
        end
    endtask

    initial begin
        repeat (8) @(posedge clk);
        resetn = 1'b1;
        repeat (8) @(posedge clk);

        // Move to x=760,y=27, inside the former Linux SPEED button, then
        // click. A removed toolbar must not leave an invisible hot spot.
        send_mouse(0, 8'h78, 8'h81);
        send_mouse(0, 8'h00, 8'h81);
        send_mouse(0, 8'h00, 8'hb1);
        send_mouse(1, 8'h00, 8'h00);
        if (gui_speed_2x !== 1'b0)
            $fatal(1, "LINUX_INVISIBLE_SPEED_HOTSPOT_PRESENT");

        $display("PASS tb_ch9350_linux_no_toolbar");
        $finish;
    end
endmodule
