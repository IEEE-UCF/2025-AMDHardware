module rasterizer #(
    parameter int CORD_WIDTH = 10
) (
    input logic clk,
    input logic rst_n,

    // this is going to have alot of inline comments cause this is super duper complex LOL!!!
    // triangle vertices
    input logic i_start,
    input logic signed [CORD_WIDTH-1:0] i_v0_x,
    i_v0_y,
    input logic signed [CORD_WIDTH-1:0] i_v1_x,
    i_v1_y,
    input logic signed [CORD_WIDTH-1:0] i_v2_x,
    i_v2_y,

    // stream of pixels that fall inside the triangle
    output logic o_fragment_valid,
    output logic signed [CORD_WIDTH-1:0] o_fragment_x,
    output logic signed [CORD_WIDTH-1:0] o_fragment_y,
    // barycentric weights for the interpolator
    output logic signed [(CORD_WIDTH*2):0] o_lambda0,
    output logic signed [(CORD_WIDTH*2):0] o_lambda1,
    output logic signed [(CORD_WIDTH*2):0] o_lambda2,
    output logic o_done
);

  // hold state while scanning
  logic is_running;
  logic signed [CORD_WIDTH-1:0] v0_x_reg, v0_y_reg, v1_x_reg, v1_y_reg, v2_x_reg, v2_y_reg;
  logic signed [CORD_WIDTH-1:0] x_reg, y_reg;
  logic signed [CORD_WIDTH-1:0] bbox_min_x_reg, bbox_min_y_reg, bbox_max_x_reg, bbox_max_y_reg;

  // dumb half space logic
  // edge checks (decide if a pixel is inside the triangle)
  logic signed [(CORD_WIDTH*2):0] edge0, edge1, edge2;
  logic is_inside;

  // edge function E(x, y) = (x - vx1)*(vy2 - vy1) - (y - vy1)*(vx2 - vx1)
  // simple 2d cross product to see which side of an edge (x,y) is on
  assign edge0 = (x_reg - v1_x_reg) * (v2_y_reg - v1_y_reg) - (y_reg - v1_y_reg) * (v2_x_reg - v1_x_reg);
  assign edge1 = (x_reg - v2_x_reg) * (v0_y_reg - v2_y_reg) - (y_reg - v2_y_reg) * (v0_x_reg - v2_x_reg);
  assign edge2 = (x_reg - v0_x_reg) * (v1_y_reg - v0_y_reg) - (y_reg - v0_y_reg) * (v1_x_reg - v0_x_reg);

  // for a counter clockwise triangle, the pixel is inside if it's on the positive
  // (or zero) side of all three edges
  assign is_inside = (edge0 >= 0) && (edge1 >= 0) && (edge2 >= 0);

  // the edge function results are also proportional to the barycentric weights
  assign o_lambda0 = edge0;
  assign o_lambda1 = edge1;
  assign o_lambda2 = edge2;

  // scanning fsm (scanning round the bounding box!!!)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      is_running <= 1'b0;
      x_reg <= '0;
      y_reg <= '0;
      v0_x_reg <= '0;
      v0_y_reg <= '0;
      v1_x_reg <= '0;
      v1_y_reg <= '0;
      v2_x_reg <= '0;
      v2_y_reg <= '0;
      bbox_min_x_reg <= '0;
      bbox_min_y_reg <= '0;
      bbox_max_x_reg <= '0;
      bbox_max_y_reg <= '0;
    end else begin
      if (i_start) begin
        is_running <= 1'b1;

        // latch the vertices when we start
        v0_x_reg <= i_v0_x;
        v0_y_reg <= i_v0_y;
        v1_x_reg <= i_v1_x;
        v1_y_reg <= i_v1_y;
        v2_x_reg <= i_v2_x;
        v2_y_reg <= i_v2_y;

        // figure out the bounding box of the triangle
        bbox_min_x_reg <= (i_v0_x < i_v1_x) ? ((i_v0_x < i_v2_x) ? i_v0_x : i_v2_x) : ((i_v1_x < i_v2_x) ? i_v1_x : i_v2_x);
        bbox_max_x_reg <= (i_v0_x > i_v1_x) ? ((i_v0_x > i_v2_x) ? i_v0_x : i_v2_x) : ((i_v1_x > i_v2_x) ? i_v1_x : i_v2_x);
        bbox_min_y_reg <= (i_v0_y < i_v1_y) ? ((i_v0_y < i_v2_y) ? i_v0_y : i_v2_y) : ((i_v1_y < i_v2_y) ? i_v1_y : i_v2_y);
        bbox_max_y_reg <= (i_v0_y > i_v1_y) ? ((i_v0_y > i_v2_y) ? i_v0_y : i_v2_y) : ((i_v1_y > i_v2_y) ? i_v1_y : i_v2_y);

        // start scanning at the top left of the box
        x_reg <= (i_v0_x < i_v1_x) ? ((i_v0_x < i_v2_x) ? i_v0_x : i_v2_x) : ((i_v1_x < i_v2_x) ? i_v1_x : i_v2_x);
        y_reg <= (i_v0_y < i_v1_y) ? ((i_v0_y < i_v2_y) ? i_v0_y : i_v2_y) : ((i_v1_y < i_v2_y) ? i_v1_y : i_v2_y);

        // scan every pixel inside the bounding box
      end else if (is_running) begin
        if (x_reg == bbox_max_x_reg) begin
          x_reg <= bbox_min_x_reg;  // wrap x to the left
          if (y_reg == bbox_max_y_reg) begin
            is_running <= 1'b0;  // finished the last pixel
          end else begin
            y_reg <= y_reg + 1;  // move to the next row
          end
        end else begin
          x_reg <= x_reg + 1;  // move to the next pixel
        end
      end
    end
  end

  // do i even have to inline comment this
  // only flag valid pixels while running and inside triangle
  assign o_fragment_valid = is_running && is_inside;
  assign o_fragment_x = x_reg;
  assign o_fragment_y = y_reg;
  assign o_done = !is_running;

endmodule

