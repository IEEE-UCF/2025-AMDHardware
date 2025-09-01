module branch_calc #(
    parameter ADDR_WIDTH = 32,
    parameter INST_WIDTH = 32
)(
    input  wire [ADDR_WIDTH-1:0] pc,
    input  wire [INST_WIDTH-1:0] inst,
    input  wire [ADDR_WIDTH-1:0] data_a,
    output wire [ADDR_WIDTH-1:0] bra_addr,
    output wire [ADDR_WIDTH-1:0] jal_addr,
    output wire [ADDR_WIDTH-1:0] jalr_addr
);
    // Branch Address Calculation (B-type)
    wire [ADDR_WIDTH-1:0] bra_offset = {{ADDR_WIDTH-12{inst[31]}}, inst[7], inst[30:25], inst[11:8], 1'b0};
    assign bra_addr = pc + bra_offset;

    // Jump and Link Address Calculation (J-type)
    wire [ADDR_WIDTH-1:0] jal_offset = {{ADDR_WIDTH-20{inst[31]}}, inst[19:12], inst[20], inst[30:21], 1'b0};
    assign jal_addr = pc + jal_offset;

    // Jump and Link Register Calculation (I-type)
    wire [ADDR_WIDTH-1:0] jalr_offset = {{ADDR_WIDTH-11{inst[31]}}, inst[30:20]};
    wire [ADDR_WIDTH-1:0] dest = data_a + jalr_offset;
    assign jalr_addr = {dest[ADDR_WIDTH-1:1], 1'b0};
endmodule
