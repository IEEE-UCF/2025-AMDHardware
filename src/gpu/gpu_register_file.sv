module gpu_register_file #(
    parameter int DATA_WIDTH = 32,
    parameter int NUM_REGS   = 16,
    parameter int ADDR_WIDTH = $clog2(NUM_REGS)
) (
    input logic clk,
    input logic rst_n,

    input logic i_wr_en,
    input logic [ADDR_WIDTH-1:0] i_wr_addr,
    input logic [DATA_WIDTH-1:0] i_wr_data,

    input  logic [ADDR_WIDTH-1:0] i_rd_addr_a,
    output logic [DATA_WIDTH-1:0] o_rd_data_a,

    input  logic [ADDR_WIDTH-1:0] i_rd_addr_b,
    output logic [DATA_WIDTH-1:0] o_rd_data_b
);

  logic [DATA_WIDTH-1:0] registers[NUM_REGS-1:0];

  // Write on the clock edge, with synchronous reset to initialize registers
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      // On reset, clear all registers to a known state (0)
      for (int i = 0; i < NUM_REGS; i++) begin
        registers[i] <= '0;
      end
    end else begin
      if (i_wr_en) begin
        registers[i_wr_addr] <= i_wr_data;
      end
    end
  end

  // Reads are combinational for speed
  assign o_rd_data_a = registers[i_rd_addr_a];
  assign o_rd_data_b = registers[i_rd_addr_b];

endmodule

