module shader_core #(
    parameter int DATA_WIDTH = 32,
    parameter int VEC_SIZE   = 4,
    parameter int NUM_REGS   = 16
) (
    input logic clk,
    input logic rst_n,

    // from main controller
    input logic i_exec_en,
    input logic [4:0] i_opcode,
    input logic [3:0] i_rd_addr,
    input logic [3:0] i_rs1_addr,
    input logic [3:0] i_rs2_addr,

    // to data memory (for loads/stores)
    output logic o_mem_req,
    input  logic i_mem_ready
);

  logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] rs1_data, rs2_data;
  logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] alu_result;
  logic reg_write_en;

  // the core contains its own private register file and alu
  gpu_register_file #(
      .DATA_WIDTH(DATA_WIDTH * VEC_SIZE),  // pack vector into a single wide word
      .NUM_REGS  (NUM_REGS)
  ) reg_file_inst (
      .clk(clk),
      .rst_n(rst_n),
      .i_wr_en(reg_write_en),
      .i_wr_addr(i_rd_addr),
      .i_wr_data(alu_result),
      .i_rd_addr_a(i_rs1_addr),
      .o_rd_data_a(rs1_data),
      .i_rd_addr_b(i_rs2_addr),
      .o_rd_data_b(rs2_data)
  );

  alu #(
      .DATA_WIDTH (DATA_WIDTH),
      .VECTOR_SIZE(VEC_SIZE)
  ) alu_inst (
      .i_operand_a(rs1_data),
      .i_operand_b(rs2_data),
      .i_opcode(i_opcode),
      .o_result(alu_result)
  );

  // this write enable is just a delayed version of the execute enable,
  // creating a simple two-stage pipeline (execute -> writeback).
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg_write_en <= 1'b0;
    end else begin
      reg_write_en <= i_exec_en;
    end
  end

endmodule

