module mmu #(
    parameter int ADDR_WIDTH = 32
) (
    input logic clk,
    input logic rst_n,

    input logic [ADDR_WIDTH-1:0] i_base_addr,
    input logic [ADDR_WIDTH-1:0] i_bound_addr,

    input logic i_valid,
    input logic [ADDR_WIDTH-1:0] i_virtual_addr,

    output logic o_valid,
    output logic [ADDR_WIDTH-1:0] o_physical_addr,
    output logic o_error
);

  logic [ADDR_WIDTH-1:0] base_reg, bound_reg;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      base_reg  <= '0;
      bound_reg <= '0;
    end else begin
      base_reg  <= i_base_addr;
      bound_reg <= i_bound_addr;
    end
  end

  // check if the shader's address is within its allowed memory space
  assign o_physical_addr = base_reg + i_virtual_addr;
  assign o_error = (i_virtual_addr >= bound_reg);
  assign o_valid = i_valid & !o_error;

endmodule

