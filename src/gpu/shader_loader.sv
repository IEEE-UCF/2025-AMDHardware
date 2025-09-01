module shader_loader #(
    parameter int INSTR_WIDTH = 32,
    parameter int INSTR_DEPTH = 256
) (
    input logic clk,
    input logic rst_n,

    // from cpu/host, for writing the shader
    input  logic                            i_host_we,
    input  logic [$clog2(INSTR_DEPTH)-1:0]  i_host_addr,
    input  logic [INSTR_WIDTH-1:0]          i_host_wdata,
    output logic [INSTR_WIDTH-1:0]          o_host_rdata,

    // to gpu fetch stage, for reading instructions
    input  logic [$clog2(INSTR_DEPTH)-1:0]  i_gpu_addr,
    output logic [INSTR_WIDTH-1:0]          o_gpu_instr
);

  // this internal memory holds the shader program (becomes a bram on the fpga)
  logic [INSTR_WIDTH-1:0] instruction_mem[INSTR_DEPTH-1:0];

  always_ff @(posedge clk) begin
    if (i_host_we) begin
      instruction_mem[i_host_addr] <= i_host_wdata;
    end
  end

  // gpu host and reads instructions combinationally
  assign o_gpu_instr   = instruction_mem[i_gpu_addr];
  assign o_host_rdata  = instruction_mem[i_host_addr];

endmodule

