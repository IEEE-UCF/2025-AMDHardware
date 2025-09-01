module mux_n #(
    parameter INPUT_WIDTH = 32,
    parameter INPUT_NUM = 4
)(
    input  logic [INPUT_NUM-1:0][INPUT_WIDTH-1:0] data_in,
    input  logic [$clog2(INPUT_NUM)-1:0]          sel,
    output logic [INPUT_WIDTH-1:0]                data_out
);

    always_comb begin
        if (sel < INPUT_NUM) begin
            data_out = data_in[sel];
        end else begin
            data_out = '0;
        end
    end

endmodule