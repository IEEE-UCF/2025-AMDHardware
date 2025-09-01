module reset_sync (
    input logic clk,
    input logic arst_n,
    output logic srst_n
);
    // double flip-flop to clean up reset release
    logic rst_s1;
    logic rst_s2;

    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) begin
            rst_s1 <= 1'b0;
            rst_s2 <= 1'b0;
        end else begin
            rst_s1 <= 1'b1;
            rst_s2 <= rst_s1;
        end
    end

    assign srst_n = rst_s2;

endmodule