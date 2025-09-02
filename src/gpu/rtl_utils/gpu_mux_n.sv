module mux_n #(
    parameter int NUM_INPUTS = 4,
    parameter int DATA_WIDTH = 32
) (
    input logic [NUM_INPUTS-1:0][DATA_WIDTH-1:0] i_data_in,
    input logic [$clog2(NUM_INPUTS)-1:0] i_sel,
    output logic [DATA_WIDTH-1:0] o_data_out
);
    initial begin
      if ((NUM_INPUTS & (NUM_INPUTS - 1)) != 0 && NUM_INPUTS != 0) begin
          $fatal(1, "NUM_INPUTS must be a power of two");
      end
    end
    
    assign o_data_out = i_data_in[i_sel];

endmodule