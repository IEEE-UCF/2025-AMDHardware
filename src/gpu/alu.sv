module alu #(
    parameter int DATA_WIDTH  = 32,
    parameter int VECTOR_SIZE = 4
) (
    input logic [VECTOR_SIZE-1:0][DATA_WIDTH-1:0] i_operand_a,
    input logic [VECTOR_SIZE-1:0][DATA_WIDTH-1:0] i_operand_b,
    input logic [4:0] i_opcode,
    output logic [VECTOR_SIZE-1:0][DATA_WIDTH-1:0] o_result
);

    always_comb begin
        o_result = '0;

        for (int i = 0; i < VECTOR_SIZE; i++) begin
            case (i_opcode)
                5'b00001: o_result[i] = i_operand_a[i] + i_operand_b[i];
                5'b00010: o_result[i] = i_operand_a[i] - i_operand_b[i];
                5'b00011: o_result[i] = i_operand_a[i] * i_operand_b[i];
                5'b01001: o_result[i] = i_operand_a[i] & i_operand_b[i];
                5'b01010: o_result[i] = i_operand_a[i] | i_operand_b[i];
                5'b01011: o_result[i] = i_operand_a[i] ^ i_operand_b[i];
                5'b10001: o_result[i] = i_operand_a[i];
                5'b10010: o_result[i] = i_operand_b[i];
                default:  o_result[i] = '0;
            endcase
        end
    end

endmodule