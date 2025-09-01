module bypass_mux #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter REG_NUM = 32
)(
    input  logic                               ex_wr_reg_en,
    input  logic                               mm_wr_reg_en,
    input  logic                               mm_is_load,
    input  logic [ADDR_WIDTH-1:0]              file_out,
    input  logic [ADDR_WIDTH-1:0]              ex_pro,
    input  logic [ADDR_WIDTH-1:0]              mm_pro,
    input  logic [ADDR_WIDTH-1:0]              mm_mem,
    input  logic [$clog2(REG_NUM)-1:0]         file_out_rs,
    input  logic [$clog2(REG_NUM)-1:0]         ex_rd,
    input  logic [$clog2(REG_NUM)-1:0]         mm_rd,
    output logic [ADDR_WIDTH-1:0]              bypass_out
);

    logic [1:0] bypass_sel;
    logic [ADDR_WIDTH-1:0] bypass_options [0:3];
    
    always_comb begin
        bypass_sel = 2'b00;
        
        if (file_out_rs == ex_rd && ex_wr_reg_en && file_out_rs != '0) begin
            bypass_sel = 2'b01;
        end
        else if (file_out_rs == mm_rd && mm_wr_reg_en && file_out_rs != '0) begin
            if (mm_is_load) begin
                bypass_sel = 2'b11;
            end else begin
                bypass_sel = 2'b10;
            end
        end
        else begin
            bypass_sel = 2'b00;
        end
    end

    assign bypass_options[0] = file_out;
    assign bypass_options[1] = ex_pro;
    assign bypass_options[2] = mm_pro;
    assign bypass_options[3] = mm_mem;

    mux_n #(
        .INPUT_WIDTH(ADDR_WIDTH),
        .INPUT_NUM(4)
    ) bypass_selection (
        .data_in(bypass_options),
        .sel(bypass_sel),
        .data_out(bypass_out)
    );

endmodule
