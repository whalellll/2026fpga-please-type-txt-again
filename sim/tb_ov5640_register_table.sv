`timescale 1ns/1ps

module tb_ov5640_register_table;
    reg [8:0] register_index = 9'h1ff;
    wire [23:0] register_data;

    ov5640_register_table dut (
        .register_index(register_index),
        .register_data(register_data)
    );

    task check_entry;
        input [8:0] index_value;
        input [23:0] expected_value;
        begin
            register_index = index_value;
            #1;
            if (register_data !== expected_value)
                $fatal(1, "table[%0d]=%h expected %h",
                    index_value, register_data, expected_value);
        end
    endtask

    initial begin
        check_entry(9'd0,   24'h310311);
        check_entry(9'd1,   24'h300882);
        check_entry(9'd2,   24'hffffff);
        check_entry(9'd101, 24'hffffff);
        check_entry(9'd102, 24'h300842);
        check_entry(9'd308, 24'h303541);
        check_entry(9'd309, 24'h303669);
        check_entry(9'd323, 24'h380805);
        check_entry(9'd324, 24'h380900);
        check_entry(9'd325, 24'h380a02);
        check_entry(9'd326, 24'h380bd0);
        check_entry(9'd356, 24'h350300);
        check_entry(9'd357, 24'hffffff);
        check_entry(9'd511, 24'hffffff);
        $display("OV5640_REGISTER_TABLE_PASS");
        $finish;
    end
endmodule
