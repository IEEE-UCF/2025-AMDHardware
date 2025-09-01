module imme #(
    parameter DATA_WIDTH = 32,
    parameter INST_WIDTH = 32, 
    parameter IMM_TYPE_NUM = 4
)(
    input  wire [INST_WIDTH-1:0]            inst,
    input  wire [$clog2(IMM_TYPE_NUM)-1:0]  imm_type,
    output reg [DATA_WIDTH-1:0]             imm
);
    localparam IMM_I_TYPE = 2'b00;
    localparam IMM_S_TYPE = 2'b01;
    localparam IMM_U_TYPE = 2'b10;
    localparam IMM_B_TYPE = 2'b11;
    
    always_comb begin
        case(imm_type)
            IMM_I_TYPE: 
                imm = {{(DATA_WIDTH-12){inst[31]}}, inst[31:20]};
            
            IMM_S_TYPE: 
                imm = {{(DATA_WIDTH-12){inst[31]}}, inst[31:25], inst[11:7]};
            
            IMM_U_TYPE: 
                imm = {{(DATA_WIDTH-32){inst[31]}}, inst[31:12], 12'b0};
            
            IMM_B_TYPE: 
                imm = {{(DATA_WIDTH-13){inst[31]}}, inst[31], inst[7], inst[30:25], inst[11:8], 1'b0};
            
            default: 
                imm = {DATA_WIDTH{1'b0}};
        endcase
    end
endmodule
