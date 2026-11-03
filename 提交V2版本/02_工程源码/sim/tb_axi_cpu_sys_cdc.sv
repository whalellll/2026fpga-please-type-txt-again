`timescale 1ns/1ps

module tb_axi_cpu_sys_cdc;
    integer cpu_half = 7, sys_half = 11, sys_phase = 3;
    reg [31:0] seed = 32'h1a2b_3c4d;
    reg [31:0] cpu_rng = 1, sys_rng = 1;
    reg cpu_clk = 0, sys_clk = 0, reset_request = 0;
    always #(cpu_half) cpu_clk = ~cpu_clk;
    initial begin
        if ($value$plusargs("cpu_half=%d", cpu_half)) begin end
        if ($value$plusargs("sys_half=%d", sys_half)) begin end
        if ($value$plusargs("sys_phase=%d", sys_phase)) begin end
        if ($value$plusargs("seed=%d", seed)) begin end
        if (cpu_half < 2 || sys_half < 2 || sys_phase < 1 || seed == 0)
            $fatal(1, "bad clock parameters");
        #(sys_phase);
        forever #(sys_half) sys_clk = ~sys_clk;
    end

    reg [2:0] cpu_reset_pipe = 0, sys_reset_pipe = 0;
    always @(posedge cpu_clk or negedge reset_request)
        if (!reset_request) cpu_reset_pipe <= 0;
        else cpu_reset_pipe <= {cpu_reset_pipe[1:0],1'b1};
    always @(posedge sys_clk or negedge reset_request)
        if (!reset_request) sys_reset_pipe <= 0;
        else sys_reset_pipe <= {sys_reset_pipe[1:0],1'b1};
    wire cpu_resetn = cpu_reset_pipe[2];
    wire sys_resetn = sys_reset_pipe[2];

    integer epoch = 0;
    integer cpu_cycles = 0, sys_cycles = 0;
    integer ar_sent = 0, aw_sent = 0, w_sent = 0, r_recv = 0, b_recv = 0;
    integer ar_recv = 0, aw_recv = 0, w_recv = 0, r_sent = 0, b_sent = 0;
    reg [57:0] s_ar_payload = 0, s_aw_payload = 0;
    reg [40:0] s_w_payload = 0;
    reg s_arvalid = 0, s_awvalid = 0, s_wvalid = 0;
    wire s_arready, s_awready, s_wready;
    wire [57:0] m_ar_payload, m_aw_payload;
    wire [40:0] m_w_payload;
    wire m_arvalid, m_awvalid, m_wvalid;
    wire m_arready = sys_resetn && sys_rng[0];
    wire m_awready = sys_resetn && sys_rng[4];
    // This downstream model accepts W only after the matching AW.  The
    // upstream sends W first, so the W FIFO fills without blocking AW.
    wire m_wready = sys_resetn && (aw_recv > w_recv/8) && sys_rng[8];
    reg [38:0] m_r_payload = 0;
    reg [5:0] m_b_payload = 0;
    reg m_rvalid = 0, m_bvalid = 0;
    wire m_rready, m_bready;
    wire [38:0] s_r_payload;
    wire [5:0] s_b_payload;
    wire s_rvalid, s_bvalid;
    wire s_rready = cpu_resetn && cpu_rng[3];
    wire s_bready = cpu_resetn && cpu_rng[7];

    axi_cpu_sys_cdc dut(
        .cpu_clk(cpu_clk),.cpu_resetn(cpu_resetn),
        .sys_clk(sys_clk),.sys_resetn(sys_resetn),
        .s_ar_payload(s_ar_payload),.s_arvalid(s_arvalid),.s_arready(s_arready),
        .m_ar_payload(m_ar_payload),.m_arvalid(m_arvalid),.m_arready(m_arready),
        .s_aw_payload(s_aw_payload),.s_awvalid(s_awvalid),.s_awready(s_awready),
        .m_aw_payload(m_aw_payload),.m_awvalid(m_awvalid),.m_awready(m_awready),
        .s_w_payload(s_w_payload),.s_wvalid(s_wvalid),.s_wready(s_wready),
        .m_w_payload(m_w_payload),.m_wvalid(m_wvalid),.m_wready(m_wready),
        .m_r_payload(m_r_payload),.m_rvalid(m_rvalid),.m_rready(m_rready),
        .s_r_payload(s_r_payload),.s_rvalid(s_rvalid),.s_rready(s_rready),
        .m_b_payload(m_b_payload),.m_bvalid(m_bvalid),.m_bready(m_bready),
        .s_b_payload(s_b_payload),.s_bvalid(s_bvalid),.s_bready(s_bready));

    // Every VALID and payload must remain stable after a stalled edge,
    // including the FIFO output after its pointer has crossed the clock.
    reg hold_s_ar = 0, hold_s_aw = 0, hold_s_w = 0;
    reg hold_s_r = 0, hold_s_b = 0;
    reg [57:0] old_s_ar, old_s_aw;
    reg [40:0] old_s_w;
    reg [38:0] old_s_r;
    reg [5:0] old_s_b;
    always @(posedge cpu_clk) begin
        if (!cpu_resetn) begin
            hold_s_ar <= 0; hold_s_aw <= 0; hold_s_w <= 0;
            hold_s_r <= 0; hold_s_b <= 0;
        end else begin
            if (hold_s_ar && (!s_arvalid || s_ar_payload !== old_s_ar))
                $fatal(1,"stalled CPU AR changed");
            if (hold_s_aw && (!s_awvalid || s_aw_payload !== old_s_aw))
                $fatal(1,"stalled CPU AW changed");
            if (hold_s_w && (!s_wvalid || s_w_payload !== old_s_w))
                $fatal(1,"stalled CPU W changed");
            if (hold_s_r && (!s_rvalid || s_r_payload !== old_s_r))
                $fatal(1,"stalled CPU R changed");
            if (hold_s_b && (!s_bvalid || s_b_payload !== old_s_b))
                $fatal(1,"stalled CPU B changed");
            hold_s_ar <= s_arvalid && !s_arready; old_s_ar <= s_ar_payload;
            hold_s_aw <= s_awvalid && !s_awready; old_s_aw <= s_aw_payload;
            hold_s_w <= s_wvalid && !s_wready; old_s_w <= s_w_payload;
            hold_s_r <= s_rvalid && !s_rready; old_s_r <= s_r_payload;
            hold_s_b <= s_bvalid && !s_bready; old_s_b <= s_b_payload;
        end
    end
    reg hold_m_ar = 0, hold_m_aw = 0, hold_m_w = 0;
    reg hold_m_r = 0, hold_m_b = 0;
    reg [57:0] old_m_ar, old_m_aw;
    reg [40:0] old_m_w;
    reg [38:0] old_m_r;
    reg [5:0] old_m_b;
    always @(posedge sys_clk) begin
        if (!sys_resetn) begin
            hold_m_ar <= 0; hold_m_aw <= 0; hold_m_w <= 0;
            hold_m_r <= 0; hold_m_b <= 0;
        end else begin
            if (hold_m_ar && (!m_arvalid || m_ar_payload !== old_m_ar))
                $fatal(1,"stalled SYS AR changed");
            if (hold_m_aw && (!m_awvalid || m_aw_payload !== old_m_aw))
                $fatal(1,"stalled SYS AW changed");
            if (hold_m_w && (!m_wvalid || m_w_payload !== old_m_w))
                $fatal(1,"stalled SYS W changed");
            if (hold_m_r && (!m_rvalid || m_r_payload !== old_m_r))
                $fatal(1,"stalled SYS R changed");
            if (hold_m_b && (!m_bvalid || m_b_payload !== old_m_b))
                $fatal(1,"stalled SYS B changed");
            hold_m_ar <= m_arvalid && !m_arready; old_m_ar <= m_ar_payload;
            hold_m_aw <= m_awvalid && !m_awready; old_m_aw <= m_aw_payload;
            hold_m_w <= m_wvalid && !m_wready; old_m_w <= m_w_payload;
            hold_m_r <= m_rvalid && !m_rready; old_m_r <= m_r_payload;
            hold_m_b <= m_bvalid && !m_bready; old_m_b <= m_b_payload;
        end
    end

    always @(posedge cpu_clk) begin
        if (!cpu_resetn) begin
            cpu_rng <= seed ^ 32'h5a5a_75e3;
            cpu_cycles <= 0;
            ar_sent <= 0; aw_sent <= 0; w_sent <= 0;
            r_recv <= 0; b_recv <= 0;
            s_arvalid <= 0; s_awvalid <= 0; s_wvalid <= 0;
        end else begin
            cpu_rng <= {cpu_rng[30:0],
                cpu_rng[31] ^ cpu_rng[21] ^ cpu_rng[1] ^ cpu_rng[0]};
            cpu_cycles <= cpu_cycles + 1;
            if (s_arvalid && s_arready) begin
                s_arvalid <= 0; ar_sent <= ar_sent + 1;
            end else if (!s_arvalid && ar_sent < 4) begin
                s_ar_payload <= {4'(ar_sent),
                    (32'h1000_0000 | (epoch << 20) | (ar_sent << 5)),
                    8'd7,3'd2,2'd1,2'd0,4'd3,3'd0};
                s_arvalid <= 1;
            end
            if (s_awvalid && s_awready) begin
                s_awvalid <= 0; aw_sent <= aw_sent + 1;
            end else if (!s_awvalid && aw_sent < 4 && cpu_cycles > 24) begin
                s_aw_payload <= {4'(aw_sent),
                    (32'h2000_0000 | (epoch << 20) | (aw_sent << 5)),
                    8'd7,3'd2,2'd1,2'd0,4'd3,3'd0};
                s_awvalid <= 1;
            end
            if (s_wvalid && s_wready) begin
                s_wvalid <= 0; w_sent <= w_sent + 1;
            end else if (!s_wvalid && w_sent < 32) begin
                s_w_payload <= {4'(w_sent/8),
                    (32'h5500_0000 | (epoch << 16) | w_sent),
                    ((w_sent % 2 == 0) ? 4'hf : 4'h5),
                    (w_sent % 8 == 7)};
                s_wvalid <= 1;
            end
            if (s_rvalid && s_rready) begin
                if (s_r_payload !== {4'(r_recv/8),
                    (32'haa00_0000 | (epoch << 16) | r_recv),
                    ((r_recv/8 == 2) ? 2'b10 : 2'b00),
                    (r_recv % 8 == 7)})
                    $fatal(1,"R changed, lost, duplicated, or crossed reset at %0d",r_recv);
                r_recv <= r_recv + 1;
            end
            if (s_bvalid && s_bready) begin
                if (s_b_payload !== {4'(b_recv),
                    ((b_recv == 2) ? 2'b10 : 2'b00)})
                    $fatal(1,"B changed, lost, duplicated, or crossed reset at %0d",b_recv);
                b_recv <= b_recv + 1;
            end
        end
    end

    always @(posedge sys_clk) begin
        if (!sys_resetn) begin
            sys_rng <= seed;
            sys_cycles <= 0;
            ar_recv <= 0; aw_recv <= 0; w_recv <= 0;
            r_sent <= 0; b_sent <= 0;
            m_rvalid <= 0; m_bvalid <= 0;
        end else begin
            sys_rng <= {sys_rng[30:0],
                sys_rng[31] ^ sys_rng[21] ^ sys_rng[1] ^ sys_rng[0]};
            sys_cycles <= sys_cycles + 1;
            if (m_arvalid && m_arready) begin
                if (m_ar_payload !== {4'(ar_recv),
                    (32'h1000_0000 | (epoch << 20) | (ar_recv << 5)),
                    8'd7,3'd2,2'd1,2'd0,4'd3,3'd0})
                    $fatal(1,"AR changed, lost, duplicated, or crossed reset at %0d",ar_recv);
                ar_recv <= ar_recv + 1;
            end
            if (m_awvalid && m_awready) begin
                if (m_aw_payload !== {4'(aw_recv),
                    (32'h2000_0000 | (epoch << 20) | (aw_recv << 5)),
                    8'd7,3'd2,2'd1,2'd0,4'd3,3'd0})
                    $fatal(1,"AW changed, lost, duplicated, or crossed reset at %0d",aw_recv);
                aw_recv <= aw_recv + 1;
            end
            if (m_wvalid && m_wready) begin
                if (m_w_payload !== {4'(w_recv/8),
                    (32'h5500_0000 | (epoch << 16) | w_recv),
                    ((w_recv % 2 == 0) ? 4'hf : 4'h5),
                    (w_recv % 8 == 7)})
                    $fatal(1,"W changed, lost, duplicated, or crossed reset at %0d",w_recv);
                w_recv <= w_recv + 1;
            end
            if (m_rvalid && m_rready) begin
                m_rvalid <= 0; r_sent <= r_sent + 1;
            end else if (!m_rvalid && r_sent < 32 && ar_recv > r_sent/8) begin
                m_r_payload <= {4'(r_sent/8),
                    (32'haa00_0000 | (epoch << 16) | r_sent),
                    ((r_sent/8 == 2) ? 2'b10 : 2'b00),
                    (r_sent % 8 == 7)};
                m_rvalid <= 1;
            end
            if (m_bvalid && m_bready) begin
                m_bvalid <= 0; b_sent <= b_sent + 1;
            end else if (!m_bvalid && b_sent < 4 && w_recv >= 8*(b_sent+1)) begin
                m_b_payload <= {4'(b_sent),((b_sent == 2) ? 2'b10 : 2'b00)};
                m_bvalid <= 1;
            end
        end
    end

    initial begin
        #30; reset_request = 1;
        wait (w_recv >= 4 && r_recv >= 4 && w_sent > w_recv);
        @(negedge cpu_clk);
        reset_request = 0;
        epoch = 1;
        #60; reset_request = 1;
        wait (ar_sent == 4 && aw_sent == 4 && w_sent == 32 &&
              ar_recv == 4 && aw_recv == 4 && w_recv == 32 &&
              r_sent == 32 && r_recv == 32 && b_sent == 4 && b_recv == 4);
        repeat (8) @(posedge cpu_clk);
        if (s_rvalid || s_bvalid || m_arvalid || m_awvalid || m_wvalid)
            $fatal(1,"ghost transaction after completion");
        $display("AXI_CPU_SYS_CDC_PASS cpu_half=%0d sys_half=%0d phase=%0d seed=%0d",
                 cpu_half,sys_half,sys_phase,seed);
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"CDC test timeout epoch=%0d AR=%0d/%0d AW=%0d/%0d W=%0d/%0d R=%0d/%0d B=%0d/%0d",
               epoch,ar_sent,ar_recv,aw_sent,aw_recv,w_sent,w_recv,r_sent,r_recv,b_sent,b_recv);
    end
endmodule
