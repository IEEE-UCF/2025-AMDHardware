module instruction_decoder (
    input logic [31:0] i_instruction_word,

    output logic [ 4:0] o_opcode,
    output logic [ 3:0] o_rd_addr,
    output logic [ 3:0] o_rs1_addr,
    output logic [ 3:0] o_rs2_addr,
    output logic [11:0] o_imm
);
  // this is all a little ugly to read so ill make a format
  // our simple instruction format:
  // [31:27] opcode | [26:23] rd | [22:19] rs1 | [18:15] rs2 | [14:0] imm/unused
  assign o_opcode = i_instruction_word[31:27];
  assign o_rd_addr = i_instruction_word[26:23];
  assign o_rs1_addr = i_instruction_word[22:19];
  assign o_rs2_addr = i_instruction_word[18:15];
  assign o_imm = i_instruction_word[11:0];

endmodule

