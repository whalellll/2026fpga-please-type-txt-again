`timescale 1ns/1ps

// Independent byte-queue/serial-time model. Run both normal RTL and SYNTHESIS
// with the vendor GTP_LUT6D model; the latter exercises the retained LUT INIT.
module tb_uart_tx_fifo_hold_pad;
    parameter integer PTR_W = 4;
    localparam integer FIFO_DEPTH = (1 << PTR_W);
    localparam integer BAUD_DIV = 4;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg push = 0;
    reg [7:0] push_data = 0;
    wire full, empty, idle, tx;
    uart_tx_fifo #(.BAUD_DIV(BAUD_DIV), .FIFO_DEPTH(FIFO_DEPTH), .PTR_W(PTR_W)) dut (
        .clk(clk), .resetn(resetn), .push(push), .push_data(push_data),
        .full(full), .empty(empty), .idle(idle), .tx(tx)
    );
    wire reference_full, reference_empty, reference_idle, reference_tx;
    uart_tx_fifo_unpadded_reference #(.BAUD_DIV(BAUD_DIV), .FIFO_DEPTH(FIFO_DEPTH), .PTR_W(PTR_W)) original (
        .clk(clk), .resetn(resetn), .push(push), .push_data(push_data),
        .full(reference_full), .empty(reference_empty), .idle(reference_idle), .tx(reference_tx)
    );

    reg [7:0] accepted_bytes [0:4095];
    integer accepted = 0, taken = 0;
    integer age = 0;
    reg serial_busy = 0, expected_tx = 1;
    reg [9:0] frame = 10'h3ff;
    reg take_byte, accept_byte;
    integer checked_cycles = 0, accepted_total = 0, frames_total = 0;
    integer rejected_full = 0, simultaneous = 0, active_reset = 0;
    reg [FIFO_DEPTH-1:0] write_addresses_seen = 0;

    always @(posedge clk) begin
        if (!resetn) begin
            if (serial_busy || accepted != taken) active_reset = active_reset + 1;
            accepted = 0; taken = 0; age = 0;
            serial_busy = 0; expected_tx = 1;
            frame = 10'h3ff;
        end else begin
            take_byte = !serial_busy && (accepted != taken);
            accept_byte = push && ((accepted - taken) < FIFO_DEPTH);
            if (push && !accept_byte) rejected_full = rejected_full + 1;
            if (take_byte && accept_byte) simultaneous = simultaneous + 1;
            if (take_byte) begin
                frame = {1'b1, accepted_bytes[taken], 1'b0};
                taken = taken + 1;
                serial_busy = 1; age = 0; expected_tx = 0;
                frames_total = frames_total + 1;
            end else if (serial_busy) begin
                age = age + 1;
                if (age == 10 * BAUD_DIV) begin
                    serial_busy = 0; expected_tx = 1;
                end else if ((age % BAUD_DIV) == 0) begin
                    expected_tx = frame[age / BAUD_DIV];
                end
            end
            if (accept_byte) begin
                if (accepted >= 4096) $fatal(1, "Test queue capacity exhausted");
                accepted_bytes[accepted] = push_data;
                write_addresses_seen[accepted % FIFO_DEPTH] = 1'b1;
                accepted = accepted + 1;
                accepted_total = accepted_total + 1;
            end
        end
        #1;
        checked_cycles = checked_cycles + 1;
        if ({tx, full, empty, idle} !== {reference_tx, reference_full, reference_empty, reference_idle})
            $fatal(1, "UART padded/original cycle mismatch cycle=%0d", checked_cycles);
        if (tx !== expected_tx || full !== ((accepted-taken) == FIFO_DEPTH) ||
            empty !== (accepted == taken) || idle !== (!serial_busy && accepted == taken))
            $fatal(1, "UART cycle mismatch cycle=%0d tx=%b/%b queue=%0d busy=%b flags=%b%b%b",
                   checked_cycles, tx, expected_tx, accepted-taken, serial_busy, full, empty, idle);
        if (resetn && dut.fifo_write_address !== dut.wr_ptr)
            $fatal(1, "Write-address pad changed an address");
    end

    integer i;
    reg [15:0] traffic = 16'hc35a;
    initial begin
        repeat (4) @(negedge clk);
        resetn = 1;
        // Empty-to-active followed by sustained overrun: full writes are ignored,
        // while accepted writes and serial dequeue may occur on the same edge.
        for (i = 0; i < 2200; i = i + 1) begin
            push = 1; push_data = i[7:0];
            @(negedge clk);
        end
        resetn = 0; push = 1; push_data = 8'ha5;
        repeat (3) @(negedge clk);
        resetn = 1;
        for (i = 0; i < 2200; i = i + 1) begin
            traffic = {traffic[14:0], traffic[15] ^ traffic[13] ^ traffic[12] ^ traffic[10]};
            push = traffic[0] | traffic[3]; push_data = traffic[15:8];
            @(negedge clk);
        end
        push = 0;
        while (!idle) @(negedge clk);
        // Transmit all byte values, including 00/FF/55/AA, with FIFO wraparound.
        for (i = 0; i < 256; i = i + 1) begin
            while (full) @(negedge clk);
            push = 1; push_data = i[7:0];
            @(negedge clk); push = 0;
        end
        while (!idle) @(negedge clk);
        repeat (3) @(negedge clk);
        if (write_addresses_seen !== {FIFO_DEPTH{1'b1}} || accepted_total < 256 ||
            frames_total < 256 || rejected_full == 0 || simultaneous == 0 || active_reset == 0)
            $fatal(1, "UART directed coverage incomplete");
        $display("UART_TX_FIFO_HOLD_PAD_PASS ptr_w=%0d cycles=%0d accepted=%0d frames=%0d full_reject=%0d simultaneous=%0d active_reset=%0d addresses=%h",
                 PTR_W, checked_cycles, accepted_total, frames_total, rejected_full,
                 simultaneous, active_reset, write_addresses_seen);
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1, "UART directed test exceeded cycle limit");
    end
endmodule
