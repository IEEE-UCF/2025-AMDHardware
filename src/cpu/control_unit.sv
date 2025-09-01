module control_unit #(
    parameter INST_WIDTH = 32
)(
    input  logic [INST_WIDTH-1:0]  instruction,
    input  logic                   inst_valid,
    
    // Control outputs
    output logic                   reg_write,
    output logic                   mem_read,
    output logic                   mem_write,
    output logic [4:0]             alu_op,
    output logic                   alu_src,      // 0=reg, 1=imm
    output logic [1:0]             imm_type,     // Immediate type
    output logic                   branch,
    output logic                   jump,
    output logic                   jalr,
    output logic                   lui,
    output logic                   auipc,
    output logic                   system,       // System instruction
    
    // Decoded fields
    output logic [6:0]             opcode,
    output logic [2:0]             funct3,
    output logic [6:0]             funct7,
    output logic [4:0]             rd,
    output logic [4:0]             rs1,
    output logic [4:0]             rs2
);

    // Extract instruction fields
    assign opcode = instruction[6:0];
    assign rd     = instruction[11:7];
    assign funct3 = instruction[14:12];
    assign rs1    = instruction[19:15];
    assign rs2    = instruction[24:20];
    assign funct7 = instruction[31:25];
    
    // RISC-V Opcodes
    localparam OP_LUI     = 7'b0110111;
    localparam OP_AUIPC   = 7'b0010111;
    localparam OP_JAL     = 7'b1101111;
    localparam OP_JALR    = 7'b1100111;
    localparam OP_BRANCH  = 7'b1100011;
    localparam OP_LOAD    = 7'b0000011;
    localparam OP_STORE   = 7'b0100011;
    localparam OP_OP_IMM  = 7'b0010011;
    localparam OP_OP      = 7'b0110011;
    localparam OP_SYSTEM  = 7'b1110011;
    localparam OP_FENCE   = 7'b0001111;
    
    // Immediate types
    localparam IMM_I = 2'b00;
    localparam IMM_S = 2'b01;
    localparam IMM_B = 2'b10;
    localparam IMM_U = 2'b11;
    
    // ALU Operations
    localparam ALU_ADD  = 5'b00000;
    localparam ALU_SUB  = 5'b00001;
    localparam ALU_SLL  = 5'b00010;
    localparam ALU_SLT  = 5'b00011;
    localparam ALU_SLTU = 5'b00100;
    localparam ALU_XOR  = 5'b00101;
    localparam ALU_SRL  = 5'b00110;
    localparam ALU_SRA  = 5'b00111;
    localparam ALU_OR   = 5'b01000;
    localparam ALU_AND  = 5'b01001;
    localparam ALU_LUI  = 5'b01010;
    localparam ALU_AUIPC = 5'b01011;
    localparam ALU_EQ   = 5'b01100;
    localparam ALU_NE   = 5'b01101;
    localparam ALU_LT   = 5'b01110;
    localparam ALU_GE   = 5'b01111;
    localparam ALU_LTU  = 5'b10000;
    localparam ALU_GEU  = 5'b10001;
    
    // Control signal generation
    always_comb begin
        // Default values
        reg_write = 1'b0;
        mem_read  = 1'b0;
        mem_write = 1'b0;
        alu_op    = ALU_ADD;
        alu_src   = 1'b0;
        imm_type  = IMM_I;
        branch    = 1'b0;
        jump      = 1'b0;
        jalr      = 1'b0;
        lui       = 1'b0;
        auipc     = 1'b0;
        system    = 1'b0;
        
        if (inst_valid) begin
            case (opcode)
                OP_LUI: begin
                    reg_write = 1'b1;
                    alu_src   = 1'b1;
                    imm_type  = IMM_U;
                    alu_op    = ALU_LUI;
                    lui       = 1'b1;
                end
                
                OP_AUIPC: begin
                    reg_write = 1'b1;
                    alu_src   = 1'b1;
                    imm_type  = IMM_U;
                    alu_op    = ALU_AUIPC;
                    auipc     = 1'b1;
                end
                
                OP_JAL: begin
                    reg_write = 1'b1;
                    jump      = 1'b1;
                    imm_type  = IMM_U; // J-type uses U-type format
                end
                
                OP_JALR: begin
                    reg_write = 1'b1;
                    jalr      = 1'b1;
                    alu_src   = 1'b1;
                    imm_type  = IMM_I;
                    alu_op    = ALU_ADD;
                end
                
                OP_BRANCH: begin
                    branch   = 1'b1;
                    imm_type = IMM_B;
                    case (funct3)
                        3'b000: alu_op = ALU_EQ;  // BEQ
                        3'b001: alu_op = ALU_NE;  // BNE
                        3'b100: alu_op = ALU_LT;  // BLT
                        3'b101: alu_op = ALU_GE;  // BGE
                        3'b110: alu_op = ALU_LTU; // BLTU
                        3'b111: alu_op = ALU_GEU; // BGEU
                        default: alu_op = ALU_EQ;
                    endcase
                end
                
                OP_LOAD: begin
                    reg_write = 1'b1;
                    mem_read  = 1'b1;
                    alu_src   = 1'b1;
                    imm_type  = IMM_I;
                    alu_op    = ALU_ADD;
                end
                
                OP_STORE: begin
                    mem_write = 1'b1;
                    alu_src   = 1'b1;
                    imm_type  = IMM_S;
                    alu_op    = ALU_ADD;
                end
                
                OP_OP_IMM: begin
                    reg_write = 1'b1;
                    alu_src   = 1'b1;
                    imm_type  = IMM_I;
                    case (funct3)
                        3'b000: alu_op = ALU_ADD;  // ADDI
                        3'b010: alu_op = ALU_SLT;  // SLTI
                        3'b011: alu_op = ALU_SLTU; // SLTIU
                        3'b100: alu_op = ALU_XOR;  // XORI
                        3'b110: alu_op = ALU_OR;   // ORI
                        3'b111: alu_op = ALU_AND;  // ANDI
                        3'b001: alu_op = ALU_SLL;  // SLLI
                        3'b101: alu_op = (funct7[5]) ? ALU_SRA : ALU_SRL; // SRLI/SRAI
                    endcase
                end
                
                OP_OP: begin
                    reg_write = 1'b1;
                    case (funct3)
                        3'b000: alu_op = (funct7[5]) ? ALU_SUB : ALU_ADD; // ADD/SUB
                        3'b001: alu_op = ALU_SLL;  // SLL
                        3'b010: alu_op = ALU_SLT;  // SLT
                        3'b011: alu_op = ALU_SLTU; // SLTU
                        3'b100: alu_op = ALU_XOR;  // XOR
                        3'b101: alu_op = (funct7[5]) ? ALU_SRA : ALU_SRL; // SRL/SRA
                        3'b110: alu_op = ALU_OR;   // OR
                        3'b111: alu_op = ALU_AND;  // AND
                    endcase
                end
                
                OP_SYSTEM: begin
                    system = 1'b1;
                    if (funct3 != 3'b000) begin
                        reg_write = 1'b1; // CSR instructions write to rd
                    end
                end
                
                OP_FENCE: begin
                    // FENCE instructions - treated as NOP for now
                end
                
                default: begin
                    // Unknown instruction - NOP
                end
            endcase
        end
    end

endmodule