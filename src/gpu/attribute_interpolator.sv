// attribute_interpolator.sv
// uses barycentric weights to blend vertex attributes for a fragment.

module attribute_interpolator #(
    parameter int ATTR_WIDTH   = 32,  // width of the attribute being blended
    parameter int WEIGHT_WIDTH = 21   // width of the barycentric weight
) (
    input logic signed [ATTR_WIDTH-1:0] i_attr0,  // attribute from vertex 0
    input logic signed [ATTR_WIDTH-1:0] i_attr1,  // attribute from vertex 1
    input logic signed [ATTR_WIDTH-1:0] i_attr2,  // attribute from vertex 2

    input logic signed [WEIGHT_WIDTH-1:0] i_lambda0,  // weight for vertex 0
    input logic signed [WEIGHT_WIDTH-1:0] i_lambda1,  // weight for vertex 1
    input logic signed [WEIGHT_WIDTH-1:0] i_lambda2,  // weight for vertex 2

    output logic signed [ATTR_WIDTH-1:0] o_interpolated_attr
);

  logic signed [ATTR_WIDTH+WEIGHT_WIDTH-1:0] term0, term1, term2;
  logic signed [ATTR_WIDTH+WEIGHT_WIDTH+1:0] sum_terms;

  // performs: (attr0 * w0) + (attr1 * w1) + (attr2 * w2)
  assign term0 = i_attr0 * i_lambda0;
  assign term1 = i_attr1 * i_lambda1;
  assign term2 = i_attr2 * i_lambda2;

  assign sum_terms = term0 + term1 + term2;

  // full barycentric needs a divide by triangle area, but we just use a right shift since divides are costly
  assign o_interpolated_attr = sum_terms >>> WEIGHT_WIDTH;

endmodule

