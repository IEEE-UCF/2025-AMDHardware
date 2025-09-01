// framebuffer.sv
// takes a final pixel and generates a memory write request to the interconnect
// to store it in the main dram.

module framebuffer #(
    parameter int SCREEN_WIDTH  = 640,
    parameter int SCREEN_HEIGHT = 480,
    parameter int COLOR_WIDTH   = 32
) (
    input logic clk,
    input logic rst_n,

    // input from the fragment shader stage
    input logic i_pixel_we,
    input logic [9:0] i_pixel_x,
    input logic [9:0] i_pixel_y,
    input logic [COLOR_WIDTH-1:0] i_pixel_color,

    // output to the memory interconnect (as a master)
    output logic o_mem_req,
    output logic [$clog2(SCREEN_WIDTH*SCREEN_HEIGHT)-1:0] o_mem_addr,
    output logic [COLOR_WIDTH-1:0] o_mem_wdata
);

  logic [$clog2(SCREEN_WIDTH*SCREEN_HEIGHT)-1:0] write_addr;

  // turning 2d screen coordinates into a 1d memory address
  assign write_addr  = i_pixel_y * SCREEN_WIDTH + i_pixel_x;

  // drives the memory request bus directly
  // asserts a one-cycle request whenever a valid pixel arrives from the fragment shader
  assign o_mem_req   = i_pixel_we;
  assign o_mem_addr  = write_addr;
  assign o_mem_wdata = i_pixel_color;

endmodule

