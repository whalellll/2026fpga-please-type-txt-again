`timescale 1ns/1ps

module tb_ch9350_hid;
    localparam integer BAUD_DIV=8;
    reg clk=0,resetn=0,ch9350_uart_rx=1,key_ready=1;
    wire ch9350_uart_tx,key_valid;wire[7:0]key_data;
    wire[10:0]mouse_x;wire[9:0]mouse_y;wire[2:0]mouse_buttons;
    wire[7:0]mouse_last_dx,mouse_last_dy,mouse_last_wheel;
    wire[7:0]keyboard_modifier,keyboard_last_usage,keyboard_last_ascii;
    wire caps_lock,keyboard_seen,mouse_seen;
    wire[31:0]keyboard_frame_count,mouse_frame_count,parse_error_count,dropped_key_count;
    wire[15:0]mouse_left_press_count,mouse_right_press_count;
    wire gui_help,gui_stats,gui_speed_2x,gui_cursor_alt,gui_term_focus,state_toggle;
    integer pop_count=0;reg[7:0]pop0=0,pop_last=0;
    reg [7:0] popped [0:31];
    always #5 clk=~clk;
    always@(posedge clk)if(key_valid&&key_ready)begin
        if(pop_count==0)pop0<=key_data;
        if(pop_count<32)popped[pop_count]<=key_data;
        pop_last<=key_data;pop_count<=pop_count+1;
    end

    ch9350_hid_core #(.UART_BAUD_DIV(BAUD_DIV),.GUI_PROFILE(1),
      .REPEAT_DELAY_CYCLES(10000),.REPEAT_PERIOD_CYCLES(1000)) dut(
      .clk(clk),.resetn(resetn),.ch9350_uart_rx(ch9350_uart_rx),.ch9350_uart_tx(ch9350_uart_tx),
      .key_valid(key_valid),.key_data(key_data),.key_ready(key_ready),
      .mouse_x(mouse_x),.mouse_y(mouse_y),.mouse_buttons(mouse_buttons),
      .mouse_last_dx(mouse_last_dx),.mouse_last_dy(mouse_last_dy),.mouse_last_wheel(mouse_last_wheel),
      .keyboard_modifier(keyboard_modifier),.keyboard_last_usage(keyboard_last_usage),
      .keyboard_last_ascii(keyboard_last_ascii),.caps_lock(caps_lock),
      .keyboard_seen(keyboard_seen),.mouse_seen(mouse_seen),
      .keyboard_frame_count(keyboard_frame_count),.mouse_frame_count(mouse_frame_count),
      .mouse_left_press_count(mouse_left_press_count),
      .mouse_right_press_count(mouse_right_press_count),
      .parse_error_count(parse_error_count),.dropped_key_count(dropped_key_count),
      .gui_help(gui_help),.gui_stats(gui_stats),.gui_speed_2x(gui_speed_2x),
      .gui_cursor_alt(gui_cursor_alt),.gui_term_focus(gui_term_focus),.state_toggle(state_toggle));

    task send_byte;input[7:0]v;integer n;begin
      @(negedge clk);ch9350_uart_rx=0;repeat(BAUD_DIV)@(posedge clk);
      for(n=0;n<8;n=n+1)begin@(negedge clk);ch9350_uart_rx=v[n];repeat(BAUD_DIV)@(posedge clk);end
      @(negedge clk);ch9350_uart_rx=1;repeat(BAUD_DIV)@(posedge clk);
    end endtask
    task send_keyboard;input[7:0]modifier;input[7:0]usage;begin
      send_byte(8'h57);send_byte(8'hab);send_byte(8'h01);send_byte(modifier);send_byte(0);
      send_byte(usage);send_byte(0);send_byte(0);send_byte(0);send_byte(0);send_byte(0);
    end endtask
    task send_mouse;input[7:0]buttons;input[7:0]dx;input[7:0]dy;input[7:0]wheel;begin
      send_byte(8'h57);send_byte(8'hab);send_byte(8'h02);send_byte(buttons);
      send_byte(dx);send_byte(dy);send_byte(wheel);
    end endtask

    initial begin
      repeat(8)@(posedge clk);resetn=1;repeat(8)@(posedge clk);
      if(ch9350_uart_tx!==1'b1)$fatal(1,"return UART not idle high");
      send_keyboard(0,8'h0b); // h
      repeat(20)@(posedge clk);
      if(pop_count!=1||pop0!=8'h68||!keyboard_seen)$fatal(1,"Linux key injection failed");
      send_keyboard(0,8'h3a); // F1 HELP
      repeat(20)@(posedge clk);
      if(!gui_help||pop_count!=1)$fatal(1,"Linux HELP failed");

      // Reach the former Linux CLEAR button and click. The removed blue
      // toolbar must not leave an invisible Ctrl-L injection target.
      send_mouse(0,-8'sd90,8'h80,0);
      send_mouse(0,0,8'h80,0);
      send_mouse(0,0,-8'sd77,0);
      send_mouse(1,0,0,0);
      repeat(40)@(posedge clk);
      if(mouse_x!=550||mouse_y!=27||mouse_buttons!=1||
         mouse_left_press_count!=1||mouse_right_press_count!=0||
         pop_count!=1||pop_last!=8'h68||
         gui_speed_2x||gui_cursor_alt||!gui_term_focus)
        $fatal(1,"Linux removed toolbar changed state x=%0d y=%0d count=%0d last=%02x speed=%0d cursor=%0d focus=%0d",
               mouse_x,mouse_y,pop_count,pop_last,gui_speed_2x,gui_cursor_alt,gui_term_focus);

      send_byte(8'h57);send_byte(8'h00);
      send_mouse(0,1,1,8'hff);
      repeat(20)@(posedge clk);
      if(parse_error_count==0||mouse_frame_count!=5||mouse_buttons!=0||
         mouse_left_press_count!=1||mouse_right_press_count!=0)
        $fatal(1,"resync/counters/button latch failed");

      // USB HID usage 0x2a is Backspace.  Linux terminals expect DEL.
      send_keyboard(0,8'h2a);
      repeat(20)@(posedge clk);
      if(pop_count!=2||pop_last!=8'h7f||keyboard_last_usage!=8'h2a||
         keyboard_last_ascii!=8'h7f)
        $fatal(1,"Linux Backspace mapping failed count=%0d data=%02x usage=%02x ascii=%02x",
               pop_count,pop_last,keyboard_last_usage,keyboard_last_ascii);
      $display("CH9350_BACKSPACE_MAPPING_PASS");

      // Compact-keyboard arrow usages must reach Linux as ANSI sequences.
      send_keyboard(0,8'h50); // left
      repeat(40)@(posedge clk);
      send_keyboard(0,8'h4f); // right
      repeat(40)@(posedge clk);
      send_keyboard(0,8'h52); // up
      repeat(40)@(posedge clk);
      send_keyboard(0,8'h51); // down
      repeat(40)@(posedge clk);
      if(pop_count!=14 ||
         popped[2]!=8'h1b || popped[3]!="[" || popped[4]!="D" ||
         popped[5]!=8'h1b || popped[6]!="[" || popped[7]!="C" ||
         popped[8]!=8'h1b || popped[9]!="[" || popped[10]!="A" ||
         popped[11]!=8'h1b || popped[12]!="[" || popped[13]!="B")
        $fatal(1,"COMPACT_KEYBOARD_ARROW_ANSI_FAIL count=%0d",pop_count);
      $display("CH9350_COMPACT_KEYBOARD_ARROW_PASS");

      // Camera uses the same console bytes as UART: two distinct Space
      // presses must survive release, and physical Esc maps to ASCII Esc.
      send_keyboard(0,0);
      send_keyboard(0,8'h2c);
      repeat(20)@(posedge clk);
      send_keyboard(0,0);
      send_keyboard(0,8'h2c);
      repeat(20)@(posedge clk);
      send_keyboard(0,0);
      send_keyboard(0,8'h29);
      repeat(20)@(posedge clk);
      if(pop_count!=17 || popped[14]!=8'h20 || popped[15]!=8'h20 ||
         popped[16]!=8'h1b || keyboard_last_ascii!=8'h1b)
        $fatal(1,"CAMERA_SPACE_ESC_INJECTION_FAIL count=%0d",pop_count);
      $display("CH9350_CAMERA_SPACE_ESC_PASS");

      $display("PASS tb_ch9350_hid");$finish;
    end
endmodule
