module fifo #(
    parameter int DATA_WIDTH = 32,
    parameter int DEPTH = 16
) (
    input logic clk,
    input logic rst_n,

    input logic i_wr_en,
    input logic [DATA_WIDTH-1:0] i_w_data,

    input  logic i_rd_en,
    output logic [DATA_WIDTH-1:0] o_r_data,

    output logic o_full,
    output logic o_empty
);

    localparam int ADDR_WIDTH = $clog2(DEPTH);

    logic [DATA_WIDTH-1:0] mem_array [DEPTH];
    logic [ADDR_WIDTH-1:0] wr_ptr_reg, rd_ptr_reg;
    logic [ADDR_WIDTH-1:0] wr_ptr_next, rd_ptr_next;
    // using a counter is more robust for full/empty checks than pointer comparison lol
    logic [ADDR_WIDTH:0] count_reg;
    logic [ADDR_WIDTH:0] count_next;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr_reg <= '0;
            rd_ptr_reg <= '0;
            count_reg  <= '0;
        end else begin
            wr_ptr_reg <= wr_ptr_next;
            rd_ptr_reg <= rd_ptr_next;
            count_reg  <= count_next;
        end
    end

    always_comb begin
        wr_ptr_next = wr_ptr_reg;
        rd_ptr_next = rd_ptr_reg;
        count_next = count_reg;

        if (i_wr_en && !o_full && i_rd_en && !o_empty) begin // simultaneous read & write
            wr_ptr_next = wr_ptr_reg + 1;
            rd_ptr_next = rd_ptr_reg + 1;
            count_next = count_reg; // count stays the same
        end else if (i_wr_en && !o_full) begin // write only
            wr_ptr_next = wr_ptr_reg + 1;
            count_next = count_reg + 1;
        end else if (i_rd_en && !o_empty) begin // read only
            rd_ptr_next = rd_ptr_reg + 1;
            count_next = count_reg - 1;
        end
    end

    always_ff @(posedge clk) begin
        if (i_wr_en && !o_full) begin
            mem_array[wr_ptr_reg] <= i_w_data;
        end
    end

    // combinational read for lowest latency (show-ahead)
    assign o_r_data = mem_array[rd_ptr_reg];
    assign o_empty = (count_reg == 0);
    assign o_full = (count_reg == DEPTH);

endmodule
