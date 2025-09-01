module fragment_shader #(
    parameter int DATA_WIDTH = 32,
    parameter int VEC_SIZE   = 4,
    parameter int CORD_WIDTH = 10
) (
    input logic clk,
    input logic rst_n,

    // from rasterizer/interpolator stage
    input logic                                         i_frag_valid,
    input logic signed [CORD_WIDTH-1:0]                 i_frag_x,
    input logic signed [CORD_WIDTH-1:0]                 i_frag_y,
    input logic        [  VEC_SIZE-1:0][DATA_WIDTH-1:0] i_frag_color,
    input logic        [           1:0][DATA_WIDTH-1:0] i_frag_tex_coord,

    // -- texture unit interface (request/response) --
    // to texture unit
    output logic                                  o_tex_req_valid,
    output logic [DATA_WIDTH-1:0]                 o_tex_u_coord,
    output logic [DATA_WIDTH-1:0]                 o_tex_v_coord,
    // from texture unit
    input  logic                                  i_texel_valid,
    input  logic [  VEC_SIZE-1:0][DATA_WIDTH-1:0] i_texel_color,

    // to framebuffer
    output logic                                         o_pixel_valid,
    output logic signed [CORD_WIDTH-1:0]                 o_pixel_x,
    output logic signed [CORD_WIDTH-1:0]                 o_pixel_y,
    output logic        [  VEC_SIZE-1:0][DATA_WIDTH-1:0] o_pixel_color
);

  logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] modulated_color;
  logic tex_request_sent;

  // a shader requests a texture lookup when it receives a valid fragment
  assign o_tex_req_valid = i_frag_valid;
  assign o_tex_u_coord   = i_frag_tex_coord[0];
  assign o_tex_v_coord   = i_frag_tex_coord[1];

  // im using the alu to multiply the colors (opcode 5'b00011)
  alu #(
      .DATA_WIDTH (DATA_WIDTH),
      .VECTOR_SIZE(VEC_SIZE)
  ) alu_inst (
      .i_operand_a(i_frag_color),
      .i_operand_b(i_texel_color),
      .i_opcode(5'b00011),
      .o_result(modulated_color)
  );

  // register the output to add a pipeline stage
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      o_pixel_valid <= 1'b0;
      o_pixel_x     <= '0;
      o_pixel_y     <= '0;
      o_pixel_color <= '0;
    end else begin
      // the final pixel is valid only after the texture unit returns data
      o_pixel_valid <= i_texel_valid;

      if (i_texel_valid) begin
        o_pixel_x     <= i_frag_x;
        o_pixel_y     <= i_frag_y;
        o_pixel_color <= modulated_color;
      end
    end
  end

endmodule

