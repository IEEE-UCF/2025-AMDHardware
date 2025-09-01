module texture_unit #(
    parameter int TEX_WIDTH  = 256,
    parameter int TEX_HEIGHT = 256,
    parameter int CORD_WIDTH = 16,   // for fixed-point uv coordinates
    parameter int DATA_WIDTH = 32    // for rgba color
) (
    input logic clk,
    input logic rst_n,

    // request from a shader
    input logic                  i_req_valid,
    input logic [CORD_WIDTH-1:0] i_u_coord,    // u coordinate (0.0 to 1.0)
    input logic [CORD_WIDTH-1:0] i_v_coord,    // v coordinate (0.0 to 1.0)

    // response to the shader
    output logic                  o_data_valid,
    output logic [DATA_WIDTH-1:0] o_texel_color
);

  // internal memory for the texture itself
  localparam int TEX_DEPTH = TEX_WIDTH * TEX_HEIGHT;
  logic [DATA_WIDTH-1:0] texture_mem[TEX_DEPTH-1:0];

  logic signed [$clog2(TEX_WIDTH)-1:0] tex_x;
  logic signed [$clog2(TEX_HEIGHT)-1:0] tex_y;
  logic [$clog2(TEX_DEPTH)-1:0] tex_addr;

  // take UV coords (0.0–1.0) and turn them into pixel indices
  // ok let me give a little example. 0.5 -> 128 if the texture is 256 wide
  // the coordinates are fixed point with the point after the sign bit
  assign tex_x = i_u_coord * TEX_WIDTH;
  assign tex_y = i_v_coord * TEX_HEIGHT;

  // turn the 2d texture coordinates into a 1d memory address
  assign tex_addr = tex_y * TEX_WIDTH + tex_x;

  // register the output to pipeline this stage
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      o_data_valid <= 1'b0;
    end else begin
      o_data_valid <= i_req_valid;
    end
  end

  // the read is combinational (nearest-neighbor sampling)
  assign o_texel_color = texture_mem[tex_addr];

endmodule

