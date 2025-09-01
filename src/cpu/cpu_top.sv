module cpu_top #(
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter INST_WIDTH = 32,
    parameter REG_NUM = 32
) (
    input logic clk,
    input logic rst_n,
    input logic interr, // Interrupt

    // Instruction Memory Interface
    output logic [ADDR_WIDTH-1:0] imem_addr,
    input  logic [INST_WIDTH-1:0] imem_read_data,
    output logic                  imem_read,
    input  logic                  imem_ready,

    // Data Memory Interface
    output logic [ADDR_WIDTH-1:0] dmem_addr,
    output logic [DATA_WIDTH-1:0] dmem_write_data,
    output logic                  dmem_read,
    output logic                  dmem_write,
    output logic [           3:0] dmem_byte_enable,
    input  logic [DATA_WIDTH-1:0] dmem_read_data,
    input  logic                  dmem_ready,

    // Coprocessor Interface
    output logic                  cp_instruction_detected,
    output logic [INST_WIDTH-1:0] cp_instruction_out,
    input  logic                  cp_stall_external,

    // Debug Interface
    output logic [ADDR_WIDTH-1:0] debug_pc,
    output logic                  debug_stall,
    output logic [           3:0] debug_state
);

  // Internal signals
  logic [ADDR_WIDTH-1:0] pc;
  logic [ADDR_WIDTH-1:0] pc_next;
  logic [3:0] reset_counter;  // Counter to stabilize after reset (increased size)
  logic [INST_WIDTH-1:0] instruction;
  logic                  inst_valid;
  logic                  pipeline_stall;
  logic                  branch_taken;
  logic [ADDR_WIDTH-1:0] branch_target;

  // Pipeline registers
  logic [ADDR_WIDTH-1:0] if_pc;
  logic [INST_WIDTH-1:0] if_inst;
  logic                  if_valid;

  logic [ADDR_WIDTH-1:0] id_pc;
  logic [INST_WIDTH-1:0] id_inst;
  logic                  id_valid;
  logic [DATA_WIDTH-1:0] id_rs1_data;
  logic [DATA_WIDTH-1:0] id_rs2_data;
  logic [           4:0] id_rd;
  logic [           4:0] id_rs1;
  logic [           4:0] id_rs2;

  logic [ADDR_WIDTH-1:0] ex_pc;
  logic [DATA_WIDTH-1:0] ex_result;
  logic [           4:0] ex_rd;
  logic                  ex_reg_write;
  logic                  ex_mem_read;
  logic                  ex_mem_write;
  logic [DATA_WIDTH-1:0] ex_mem_data;
  logic                  ex_valid;

  logic [ADDR_WIDTH-1:0] mem_pc;
  logic [DATA_WIDTH-1:0] mem_result;
  logic [           4:0] mem_rd;
  logic                  mem_reg_write;
  logic                  mem_valid;

  logic [DATA_WIDTH-1:0] wb_result;
  logic [           4:0] wb_rd;
  logic                  wb_reg_write;
  logic                  wb_valid;

  // Control signals
  logic                  reg_write;
  logic                  mem_read;
  logic                  mem_write;
  logic [           4:0] alu_op;
  logic                  alu_src;
  logic [           1:0] imm_type;
  logic                  branch;
  logic                  jump;
  logic                  jalr;
  logic                  lui;
  logic                  auipc;
  logic                  system;
  logic [           6:0] opcode;
  logic [           2:0] funct3;
  logic [           6:0] funct7;
  logic [           4:0] rd;
  logic [           4:0] rs1;
  logic [           4:0] rs2;

  // ========================================
  // M Extension Signals
  // ========================================
  logic                  is_m_op;
  logic                  m_valid;
  logic                  m_ready;
  logic                  m_result_valid;
  logic [DATA_WIDTH-1:0] m_result;
  logic                  m_stall;
  logic                  ex_is_m_op;
  logic [           4:0] ex_m_rd;
  logic                  ex_m_valid;

  // ========================================
  // A Extension Signals
  // ========================================
  logic                  is_a_op;
  logic                  a_valid;
  logic                  a_ready;
  logic                  a_result_valid;
  logic [DATA_WIDTH-1:0] a_result;
  logic                  a_mem_req;
  logic [ADDR_WIDTH-1:0] a_mem_addr;
  logic [DATA_WIDTH-1:0] a_mem_wdata;
  logic                  a_mem_we;
  logic                  a_mem_lock;
  logic                  a_stall_req;
  logic                  ex_is_a_op;
  logic [           4:0] ex_a_rd;
  logic                  ex_a_valid;

  // Decode M and A instructions
  assign is_m_op = (opcode == 7'b0110011) && (funct7 == 7'b0000001);
  assign is_a_op = (opcode == 7'b0101111) && (funct3 == 3'b010);

  // Register file signals
  logic [DATA_WIDTH-1:0] reg_rs1_data;
  logic [DATA_WIDTH-1:0] reg_rs2_data;

  // ALU signals
  logic [DATA_WIDTH-1:0] alu_result;
  logic                  alu_zero;

  // Immediate value
  logic [DATA_WIDTH-1:0] immediate;

  // Branch calculation signals
  logic [ADDR_WIDTH-1:0] bra_addr;
  logic [ADDR_WIDTH-1:0] jal_addr;
  logic [ADDR_WIDTH-1:0] jalr_addr;
  logic                  is_equal;

  // Hazard detection
  logic                  load_use_hazard;
  logic                  data_hazard;

  // Pipeline flush signal for atomics
  logic                  pipeline_flush;
  assign pipeline_flush = branch_taken || jump || jalr;

  // ========================================
  // M Extension Unit (Multiply/Divide)
  // ========================================
  rv32m_muldiv #(
      .MUL_LAT(2),
      .DIV_LAT(32)
  ) u_muldiv (
      .clk       (clk),
      .rst_n     (rst_n),
      .valid_i   (is_m_op && id_valid && !load_use_hazard && !cp_stall_external),
      .funct3_i  (funct3),
      .rs1_data_i(id_rs1_data),
      .rs2_data_i(id_rs2_data),
      .ready_o   (m_ready),
      .valid_o   (m_result_valid),
      .result_o  (m_result),
      .flush_i   (pipeline_flush),
      .stall_i   (load_use_hazard || cp_stall_external)
  );

  assign m_stall = ex_is_m_op && ex_m_valid && !m_result_valid;

  // ========================================
  // A Extension Unit (Atomics)
  // ========================================
  rv32a_atomic #(
      .ADDR_WIDTH(ADDR_WIDTH),
      .DATA_WIDTH(DATA_WIDTH)
  ) u_atomic (
      .clk(clk),
      .rst_n(rst_n),
      .valid_i(is_a_op && id_valid && !load_use_hazard && !cp_stall_external),
      .funct5_i(id_inst[31:27]),
      .aq_i(id_inst[26]),
      .rl_i(id_inst[25]),
      .addr_i(id_rs1_data),
      .rs1_data_i(id_rs1_data),
      .rs2_data_i(id_rs2_data),
      .ready_o(a_ready),
      .valid_o(a_result_valid),
      .result_o(a_result),
      .mem_req_o(a_mem_req),
      .mem_addr_o(a_mem_addr),
      .mem_wdata_o(a_mem_wdata),
      .mem_we_o(a_mem_we),
      .mem_lock_o(a_mem_lock),
      .mem_rdata_i(dmem_read_data),
      .mem_ready_i(dmem_ready),
      .flush_i(pipeline_flush),
      .exception_i(1'b0),  // Connect to exception logic if available
      .stall_req_o(a_stall_req),
      .snoop_valid_i(1'b0),
      .snoop_addr_i(32'h0)
  );

  // ========================================
  // Instruction Fetch Stage
  // ========================================
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      pc <= 32'h0000004c;
      if_pc <= 32'h0000004c;
      if_valid <= 1'b0;
      reset_counter <= 4'b0;
    end else if (reset_counter < 4'd10) begin
      // Hold PC stable for first 10 cycles after reset
      reset_counter <= reset_counter + 1;
      pc <= 32'h0000004c;  // Keep PC at reset value
      if_pc <= 32'h0000004c;
      if_valid <= 1'b0;
    end else if (!pipeline_stall) begin
      if (branch_taken) begin
        pc <= branch_target;
      end else if (jump) begin
        pc <= jal_addr;
      end else if (jalr) begin
        pc <= jalr_addr;
      end else begin
        pc <= pc + 4;
      end
      if_pc <= pc;
      if_valid <= 1'b1;
    end
  end

  // Instruction memory interface
  assign imem_addr = pc;
  assign imem_read = 1'b1;  // Always reading since BRAM is always ready
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        if_inst <= 32'h00000013; // NOP Signal
    end else if (!pipeline_stall) begin
        if_inst <= imem_read_data;
    end
  end

  // ========================================
  // Control Unit (Modified for M/A)
  // ========================================
  control_unit #(
      .INST_WIDTH(INST_WIDTH)
  ) ctrl_unit (
      .instruction(id_inst),
      .inst_valid(id_valid),
      .reg_write(reg_write),
      .mem_read(mem_read),
      .mem_write(mem_write),
      .alu_op(alu_op),
      .alu_src(alu_src),
      .imm_type(imm_type),
      .branch(branch),
      .jump(jump),
      .jalr(jalr),
      .lui(lui),
      .auipc(auipc),
      .system(system),
      .opcode(opcode),
      .funct3(funct3),
      .funct7(funct7),
      .rd(rd),
      .rs1(rs1),
      .rs2(rs2)
  );

  // Debug: Print instruction decode
  always_ff @(posedge clk) begin
    if (id_valid && !pipeline_stall) begin
      $display("Time %t: Decode - inst=%h, opcode=%b, rd=%d, rs1=%d, rs2=%d, imm_type=%b", 
               $time, id_inst, opcode, rd, rs1, rs2, imm_type);
      if (mem_read || mem_write) begin
        $display("  Memory op: mem_read=%b, mem_write=%b", mem_read, mem_write);
      end
    end
  end

  // ========================================
  // Register File
  // ========================================
  register_bank_cpu #(
      .REG_NUM(REG_NUM),
      .DATA_WIDTH(DATA_WIDTH)
  ) reg_file (
      .clk(clk),
      .reset(~rst_n),
      .write_addr(wb_rd),
      .data_in(wb_result),
      .write_en(wb_reg_write),
      .read_addr_a(id_inst[19:15]),
      .read_addr_b(id_inst[24:20]),
      .data_out_a(reg_rs1_data),
      .data_out_b(reg_rs2_data)
  );

  // something
  // Add forwarding logic for ALU inputs (NEW CODE - insert at line ~280)
  logic [DATA_WIDTH-1:0] forwarded_rs1_data;
  logic [DATA_WIDTH-1:0] forwarded_rs2_data;

always_comb begin
// Forward from EX stage
if (ex_reg_write && ex_valid && (ex_rd == rs1) && (rs1 != 0)) begin
    forwarded_rs1_data = ex_result;
end
// Forward from MEM stage  
else if (mem_reg_write && mem_valid && (mem_rd == rs1) && (rs1 != 0)) begin
    forwarded_rs1_data = mem_result;
end
// Forward from WB stage
else if (wb_reg_write && wb_valid && (wb_rd == rs1) && (rs1 != 0)) begin
    forwarded_rs1_data = wb_result;
end
// Use register file output
else begin
    forwarded_rs1_data = reg_rs1_data;
end

// Same for rs2
if (ex_reg_write && ex_valid && (ex_rd == rs2) && (rs2 != 0)) begin
    forwarded_rs2_data = ex_result;
end
else if (mem_reg_write && mem_valid && (mem_rd == rs2) && (rs2 != 0)) begin
    forwarded_rs2_data = mem_result;
end
else if (wb_reg_write && wb_valid && (wb_rd == rs2) && (rs2 != 0)) begin
    forwarded_rs2_data = wb_result;
end
else begin
    forwarded_rs2_data = reg_rs2_data;
end
end

  // ========================================
  // Immediate Generator
  // ========================================
  imme #(
      .DATA_WIDTH  (DATA_WIDTH),
      .INST_WIDTH  (INST_WIDTH),
      .IMM_TYPE_NUM(4)
  ) imm_gen (
      .inst(id_inst),
      .imm_type(imm_type),
      .imm(immediate)
  );

  // ========================================
  // Branch Calculation
  // ========================================
  branch_calc #(
      .ADDR_WIDTH(ADDR_WIDTH),
      .INST_WIDTH(INST_WIDTH)
  ) branch_calc_inst (
      .pc(id_pc),
      .inst(id_inst),
      .data_a(reg_rs1_data),
      .bra_addr(bra_addr),
      .jal_addr(jal_addr),
      .jalr_addr(jalr_addr)
  );

  equ #(
      .DATA_WIDTH(DATA_WIDTH)
  ) comparator (
      .data_a  (reg_rs1_data),
      .data_b  (reg_rs2_data),
      .is_equal(is_equal)
  );

// ========================================
// ALU (Modified to skip M/A ops and handle memory)
// ========================================
always_comb begin
  logic [DATA_WIDTH-1:0] alu_input_a;
  logic [DATA_WIDTH-1:0] alu_input_b;

  // Use latched values from ID stage for non-bypassed path
  // But still allow forwarding for current instruction
  if (pipeline_stall) begin
    alu_input_a = id_rs1_data;
    alu_input_b = alu_src ? immediate : id_rs2_data;
  end else begin
    alu_input_a = forwarded_rs1_data;
    alu_input_b = alu_src ? immediate : forwarded_rs2_data;
  end

  if (mem_read || mem_write) begin
    // Only log when we're actually in the right stage
    if (id_valid && !pipeline_stall) begin
      $display("Time %t: MemOp - rs1_data=%h, immediate=%h, addr=%h", 
               $time, alu_input_a, immediate, alu_input_a + immediate);
    end
  end

  // Special handling for memory operations
  if (mem_read || mem_write) begin
    // Load/Store always use rs1 + immediate for address
    alu_result = alu_input_a + immediate;  // Address calculation
  end
  else if (is_m_op || is_a_op) begin
    alu_result = 32'h0;
  end
  else begin
    case (alu_op)
      5'b00000: alu_result = alu_input_a + alu_input_b;  // ADD
      5'b00001: alu_result = alu_input_a - alu_input_b;  // SUB
      5'b00010: alu_result = alu_input_a << alu_input_b[4:0];  // SLL
      5'b00011:
      alu_result = ($signed(alu_input_a) < $signed(alu_input_b)) ? 32'h1 : 32'h0;  // SLT
      5'b00100: alu_result = (alu_input_a < alu_input_b) ? 32'h1 : 32'h0;  // SLTU
      5'b00101: alu_result = alu_input_a ^ alu_input_b;  // XOR
      5'b00110: alu_result = alu_input_a >> alu_input_b[4:0];  // SRL
      5'b00111: alu_result = $signed(alu_input_a) >>> alu_input_b[4:0];  // SRA
      5'b01000: alu_result = alu_input_a | alu_input_b;  // OR
      5'b01001: alu_result = alu_input_a & alu_input_b;  // AND
      5'b01010: alu_result = immediate;  // LUI
      5'b01011: alu_result = id_pc + immediate;  // AUIPC
      default: alu_result = 32'h0;
    endcase
  end

  alu_zero = (alu_result == 32'h0);
end

  // ========================================
  // Coprocessor Interface
  // ========================================
  dispatcher #(
      .ADDR_WIDTH(ADDR_WIDTH),
      .DATA_WIDTH(DATA_WIDTH),
      .INST_WIDTH(INST_WIDTH),
      .CP_NUM(3)
  ) cp_dispatcher (
      .clk(clk),
      .rst_n(rst_n),
      .instruction(id_inst),
      .inst_valid(id_valid && system),
      .rs1_data(reg_rs1_data),
      .rs2_data(reg_rs2_data),
      .pc(id_pc),
      .pipeline_stall(pipeline_stall),
      .cp_valid(),
      .cp_instruction(cp_instruction_out),
      .cp_data_in(),
      .cp_select(),
      .cp_data_out(32'h0),
      .cp_ready(~cp_stall_external),
      .cp_exception(1'b0),
      .cp_instruction_detected(cp_instruction_detected),
      .cp_stall_request(),
      .cp_exception_out(),
      .cp_result(),
      .cp_result_valid(),
      .cp_reg_write(),
      .cp_reg_addr(),
      .cp_reg_data()
  );

  // ========================================
  // Pipeline Stages (Modified for M/A)
  // ========================================

  // ID Stage
  always_ff @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    id_pc <= 32'h0000004c;
    id_inst <= 32'h00000013;  // NOP
    id_valid <= 1'b0;
    id_rs1_data <= 32'h0;
    id_rs2_data <= 32'h0;
    id_rd <= 5'h0;
    id_rs1 <= 5'h0;
    id_rs2 <= 5'h0;
  end else if (!pipeline_stall) begin
    id_pc <= if_pc;
    id_inst <= if_inst;
    id_valid <= if_valid && imem_ready;
    // Use forwarded data instead of raw register file output
    id_rs1_data <= forwarded_rs1_data;  // Changed from reg_rs1_data
    id_rs2_data <= forwarded_rs2_data;  // Changed from reg_rs2_data
    id_rd <= rd;      // From control unit
    id_rs1 <= rs1;    // From control unit
    id_rs2 <= rs2;    // From control unit
  end
end

  always_ff @(posedge clk) begin
  if (id_valid && reg_write && !pipeline_stall) begin
    $display("Time %t: ID will write to rd=%d", $time, rd);
  end
end

  // EX Stage (Modified for M/A)
  always_ff @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    ex_pc <= 32'h0000004c;
    ex_result <= 32'h0;
    ex_rd <= 5'h0;
    ex_reg_write <= 1'b0;
    ex_mem_read <= 1'b0;
    ex_mem_write <= 1'b0;
    ex_mem_data <= 32'h0;
    ex_valid <= 1'b0;
    ex_is_m_op <= 1'b0;
    ex_m_rd <= 5'h0;
    ex_m_valid <= 1'b0;
    ex_is_a_op <= 1'b0;
    ex_a_rd <= 5'h0;
    ex_a_valid <= 1'b0;
  end else if (load_use_hazard) begin
    // Insert bubble (NOP) in EX stage when load-use hazard detected
    ex_reg_write <= 1'b0;
    ex_mem_read <= 1'b0;
    ex_mem_write <= 1'b0;
    ex_valid <= 1'b0;
    ex_is_m_op <= 1'b0;
    ex_m_valid <= 1'b0;
    ex_is_a_op <= 1'b0;
    ex_a_valid <= 1'b0;
    end else if (!pipeline_stall) begin
      ex_pc <= id_pc;
      ex_result <= alu_result;
      ex_rd <= rd;
      ex_reg_write <= reg_write && id_valid && !is_m_op && !is_a_op;
      ex_mem_read <= mem_read && id_valid && !is_a_op;
      ex_mem_write <= mem_write && id_valid && !is_a_op;
      ex_mem_data <= forwarded_rs2_data;
      ex_valid <= id_valid;

      // Track M operations
      ex_is_m_op <= is_m_op && id_valid;
      ex_m_rd <= is_m_op ? rd : 5'h0;
      ex_m_valid <= is_m_op && id_valid;

      // Track A operations
      ex_is_a_op <= is_a_op && id_valid;
      ex_a_rd <= is_a_op ? rd : 5'h0;
      ex_a_valid <= is_a_op && id_valid;
    end
  end

  // MEM Stage (Modified for M/A)
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mem_pc <= 32'h0000004c;
      mem_result <= 32'h0;
      mem_rd <= 5'h0;
      mem_reg_write <= 1'b0;
      mem_valid <= 1'b0;
    end else if (!pipeline_stall) begin
      mem_pc <= ex_pc;

      // Select result based on operation type
      if (ex_is_m_op && m_result_valid) begin
        mem_result <= m_result;
        mem_rd <= ex_m_rd;
        mem_reg_write <= 1'b1;
      end else if (ex_is_a_op && a_result_valid) begin
        mem_result <= a_result;
        mem_rd <= ex_a_rd;
        mem_reg_write <= 1'b1;
      end else if (ex_mem_read) begin
        mem_result <= dmem_read_data;
        mem_rd <= ex_rd;
        mem_reg_write <= ex_reg_write || ex_mem_read;
      end else begin
        mem_result <= ex_result;
        mem_rd <= ex_rd;
        mem_reg_write <= ex_reg_write;
      end

      mem_valid <= ex_valid;
    end
  end

  // WB Stage
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wb_result <= 32'h0;
      wb_rd <= 5'h0;
      wb_reg_write <= 1'b0;
      wb_valid <= 1'b0;
    end else if (!pipeline_stall) begin
      wb_result <= mem_result;
      wb_rd <= mem_rd;
      wb_reg_write <= mem_reg_write;
      wb_valid <= mem_valid;
    end
  end

  // Debug: Check if write-back is working
always_ff @(posedge clk) begin
  if (wb_reg_write && wb_valid && !pipeline_stall) begin
    $display("Time %t: RegWrite - rd=%d, value=%h", $time, wb_rd, wb_result);
  end
  
  // Also check what's preventing writes
  if (mem_valid && !pipeline_stall) begin
    $display("Time %t: MEM stage - rd=%d, reg_write=%b, result=%h", 
             $time, mem_rd, mem_reg_write, mem_result);
  end
end

  // ========================================
  // Data Memory Interface (Modified for A)
  // ========================================
  always_comb begin
    if (a_mem_req) begin
      // Atomic operation takes priority
      dmem_addr = a_mem_addr;
      dmem_write_data = a_mem_wdata;
      dmem_read = !a_mem_we;
      dmem_write = a_mem_we;
      dmem_byte_enable = 4'b1111;  // Atomics are word-aligned
    end else begin
      // Normal memory operations
      dmem_addr = ex_result;
      dmem_write_data = ex_mem_data;
      dmem_read = ex_mem_read && ex_valid;
      dmem_write = ex_mem_write && ex_valid;
      dmem_byte_enable = 4'b1111;  // Full word access for now
    end
  end

  // ========================================
  // Branch Logic
  // ========================================
  always_comb begin
    branch_taken  = 1'b0;
    branch_target = 32'h0;

    if (branch && id_valid) begin
      case (funct3)
        3'b000:  branch_taken = is_equal;  // BEQ
        3'b001:  branch_taken = !is_equal;  // BNE
        3'b100:  branch_taken = reg_rs1_data < reg_rs2_data;  // BLT
        3'b101:  branch_taken = reg_rs1_data >= reg_rs2_data;  // BGE
        3'b110:  branch_taken = $unsigned(reg_rs1_data) < $unsigned(reg_rs2_data);  // BLTU
        3'b111:  branch_taken = $unsigned(reg_rs1_data) >= $unsigned(reg_rs2_data);  // BGEU
        default: branch_taken = 1'b0;
      endcase
      branch_target = bra_addr;
    end
  end

// ========================================
// Simplified Hazard Detection for Red Pitaya BRAM (Fixed circular logic)
// ========================================
always_comb begin
  load_use_hazard = 1'b0;
  data_hazard = 1'b0;

  // Simplified load-use hazard: only detect basic load-use case
  // Since BRAM is single-cycle, we only need to stall for one cycle
  if (ex_mem_read && ex_valid && id_valid) begin
    if ((ex_rd != 0) && ((ex_rd == rs1) || (ex_rd == rs2))) begin
      load_use_hazard = 1'b1;
    end
  end

  // Simplified RAW hazard for M/A extensions - avoid circular dependency
  if (id_valid) begin
    // M operations - check if M operation is in execute stage and not ready
    if (ex_is_m_op && ex_m_valid) begin
      if ((ex_m_rd != 0) && ((ex_m_rd == rs1) || (ex_m_rd == rs2))) begin
        // Only create hazard if M result is not yet available
        if (!m_result_valid) begin
          data_hazard = 1'b1;
        end
      end
    end
    
    // A operations - check if A operation is active and not ready
    if (ex_is_a_op) begin
      if ((ex_a_rd != 0) && ((ex_a_rd == rs1) || (ex_a_rd == rs2))) begin
        // Only create hazard if A result is not yet available
        if (!a_result_valid) begin
          data_hazard = 1'b1;
        end
      end
    end
  end
end

// Simplified stall logic for Red Pitaya - broken into stages to avoid circular logic
logic execution_stall;

// Since BRAM is always ready, remove memory ready checks
// Break circular dependency by not using pipeline_stall in M/A unit inputs
assign execution_stall = load_use_hazard    ||
                        data_hazard         ||
                        cp_stall_external   ||
                        a_stall_req;

assign pipeline_stall = execution_stall;  // Removed fetch_stall since BRAM is always ready

  // ========================================
  // Debug Outputs
  // ========================================
  assign debug_pc = pc;
  assign debug_stall = pipeline_stall;
  assign debug_state = {pipeline_stall, load_use_hazard, data_hazard, 1'b0};

endmodule
