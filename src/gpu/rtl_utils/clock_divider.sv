module clock_divider #(
    parameter int DIVISOR = 4
) (
    input logic clk_in,
    input logic rst_n,
    output logic clk_out
);

    localparam int COUNTER_WIDTH = $clog2(DIVISOR);
    logic [COUNTER_WIDTH-1:0] count_reg;
    logic clk_out_reg;

    initial begin
        if ((DIVISOR < 2) || (DIVISOR % 2 != 0)) begin
            $fatal(1, "DIVISOR must be an even integer greater than or equal to 2");
        end
    end

    always_ff @(posedge clk_in or negedge rst_n) begin
        if (!rst_n) begin
            count_reg   <= '0;
            clk_out_reg <= 1'b0;
        end else begin
            if (count_reg == DIVISOR - 1) begin
                count_reg <= '0;
            end else begin
                count_reg <= count_reg + 1;
            end
            
            // toggle at half period and full period to get a 50% duty cycle
            if (count_reg == (DIVISOR / 2) - 1) begin
                clk_out_reg <= ~clk_out_reg;
            end else if (count_reg == DIVISOR - 1) begin
                clk_out_reg <= ~clk_out_reg;
            end
        end
    end

    assign clk_out = clk_out_reg;

endmodule