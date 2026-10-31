`timescale 1ns / 1ps
module tb_mac_conv_window_board_top;
    reg free_clk = 0;
    always #18.518 free_clk = ~free_clk;
    reg rst_board = 0;
    wire uart_txd;
    reg [7:0] received;
    reg [8*80-1:0] transcript = 0;
    reg [8*17-1:0] prefix = 0;
    integer count = 0;
    integer bit_index;
    reg corrupt;

    mac_conv_window_board_top dut (.*);

    task uart_receive;
        begin
            wait (uart_txd == 0);
            repeat (117) @(posedge free_clk);
            if (uart_txd !== 0) $fatal(1, "UART start bit invalid");
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                repeat (234) @(posedge free_clk);
                received[bit_index] = uart_txd;
            end
            repeat (234) @(posedge free_clk);
            if (uart_txd !== 1) $fatal(1, "UART stop bit invalid");
        end
    endtask

    initial begin
        corrupt = $test$plusargs("CORRUPT_EXPECTED");
        #1;
        if (corrupt) dut.expected_rom[0] = dut.expected_rom[0] ^ 32'h1;
        repeat (12) @(posedge free_clk);
        rst_board = 1;
        while (count < 80) begin
            uart_receive();
            transcript = (transcript << 8) | received;
            count = count + 1;
            if (count <= 17) prefix = (prefix << 8) | received;
            if (received == 10) begin
                if (corrupt) begin
                    if (transcript[8*19-1:0] !== {"WINDOW_BOARD_FAIL", 8'd13, 8'd10} || count != 19)
                        $fatal(1, "failure marker mismatch count=%0d line=%0s", count, transcript);
                end else if (prefix !== "WINDOW_BOARD_PASS" || count != 71)
                    $fatal(1, "board marker mismatch: %0s", transcript);
                $display("MAC_CONV_WINDOW_BOARD_TOP_SIM_PASS bytes=%0d line=%0s", count, transcript);
                $finish;
            end
        end
        $fatal(1, "board marker timeout");
    end

    initial begin
        #20000000;
        $fatal(1, "UART board harness timeout");
    end
endmodule
