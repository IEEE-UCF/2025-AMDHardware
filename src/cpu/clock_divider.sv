module clock_divider #(
    parameter DIV_FACTOR = 2  // Default divide by 2 (125MHz -> 62.5MHz)
)(
    input  logic clk_in,       // 125MHz from Red Pitaya
    input  logic rst_n,
    output logic clk_out       // Divided clock output
);

    logic [$clog2(DIV_FACTOR)-1:0] counter;
    
    always_ff @(posedge clk_in or negedge rst_n) begin
        if (!rst_n) begin
            counter <= '0;
            clk_out <= '0;
        end else begin
            if (counter == (DIV_FACTOR/2 - 1)) begin
                counter <= '0;
                clk_out <= ~clk_out;
            end else begin
                counter <= counter + 1;
            end
        end
    end

endmodule