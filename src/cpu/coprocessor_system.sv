// Fixed Coprocessor System for Red Pitaya (RV32I)
// Optimized for 32-bit CPU and limited FPGA resources

module coprocessor_system #(
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,  // Changed to 32-bit to match CPU
    parameter INST_WIDTH = 32
) (
    input logic clk,
    input logic rst_n,

    // CPU Interface
    input logic [INST_WIDTH-1:0] instruction,
    input logic [DATA_WIDTH-1:0] rs1_data,
    input logic [DATA_WIDTH-1:0] rs2_data,
    input logic [ADDR_WIDTH-1:0] pc,
    input logic irq_signal,  // Renamed from 'interrupt' to avoid C++ reserved word

    // Result Interface
    output logic [DATA_WIDTH-1:0] cp_result,
    output logic                  cp_result_valid,
    output logic                  cp_stall,
    output logic                  cp_detected
);

  // Instruction decode
  logic [6:0] opcode;
  logic [2:0] funct3;
  logic [6:0] funct7;
  logic [4:0] rd, rs1, rs2;
  logic [11:0] csr_addr;

  assign opcode = instruction[6:0];
  assign rd = instruction[11:7];
  assign funct3 = instruction[14:12];
  assign rs1 = instruction[19:15];
  assign rs2 = instruction[24:20];
  assign funct7 = instruction[31:25];
  assign csr_addr = instruction[31:20];

  // Coprocessor detection and routing
  typedef enum logic [1:0] {
    CP_NONE = 2'b00,
    CP_CSR = 2'b01,  // System/CSR operations
    CP_MUL = 2'b10,  // Multiply/Divide (simpler than full FPU)
    CP_CUSTOM = 2'b11  // Custom extensions
  } cp_select_t;

  cp_select_t cp_select;
  logic cp_valid;

  // Detect coprocessor instructions
  always_comb begin
    cp_detected = 1'b0;
    cp_select = CP_NONE;
    cp_valid = 1'b0;

    case (opcode)
      7'b1110011: begin  // SYSTEM (CSR, ECALL, EBREAK)
        cp_detected = 1'b1;
        cp_select = CP_CSR;
        cp_valid = 1'b1;
      end
      7'b0110011: begin  // R-type with MUL/DIV (RV32M extension)
        if (funct7 == 7'b0000001) begin  // MULDIV
          cp_detected = 1'b1;
          cp_select = CP_MUL;
          cp_valid = 1'b1;
        end
      end
      7'b0001011, 7'b0101011: begin  // Custom instructions
        cp_detected = 1'b1;
        cp_select = CP_CUSTOM;
        cp_valid = 1'b1;
      end
      default: begin
        cp_detected = 1'b0;
        cp_select = CP_NONE;
        cp_valid = 1'b0;
      end
    endcase
  end

  // ==========================================
  // CSR Coprocessor (CP0) - RV32 version
  // ==========================================
  logic [DATA_WIDTH-1:0] csr_result;
  logic                  csr_valid;
  logic                  csr_exception;

  // CSR Registers for RV32
  logic [          31:0] mstatus;  // Machine status
  logic [          31:0] misa;  // ISA and extensions  
  logic [          31:0] mie;  // Machine interrupt enable
  logic [          31:0] mtvec;  // Machine trap vector
  logic [          31:0] mscratch;  // Machine scratch
  logic [          31:0] mepc;  // Machine exception PC
  logic [          31:0] mcause;  // Machine trap cause
  logic [          31:0] mtval;  // Machine trap value
  logic [          31:0] mip;  // Machine interrupt pending

  // Performance counters (64-bit even in RV32)
  logic [          63:0] cycle_count;
  logic [          63:0] instret_count;

  // Privilege mode
  logic [           1:0] priv_mode;  // 00=U, 01=S, 11=M

  // CSR addresses
  localparam CSR_MSTATUS = 12'h300;
  localparam CSR_MISA = 12'h301;
  localparam CSR_MIE = 12'h304;
  localparam CSR_MTVEC = 12'h305;
  localparam CSR_MSCRATCH = 12'h340;
  localparam CSR_MEPC = 12'h341;
  localparam CSR_MCAUSE = 12'h342;
  localparam CSR_MTVAL = 12'h343;
  localparam CSR_MIP = 12'h344;
  localparam CSR_CYCLE = 12'hC00;
  localparam CSR_TIME = 12'hC01;
  localparam CSR_INSTRET = 12'hC02;
  localparam CSR_CYCLEH = 12'hC80;
  localparam CSR_TIMEH = 12'hC81;
  localparam CSR_INSTRETH = 12'hC82;

  // CSR operations
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mstatus <= 32'h00001800;  // Initial state with MPP=11 (M-mode)
      misa <= 32'h40001100;  // RV32IM (I=base, M=multiply)
      mie <= '0;
      mtvec <= '0;
      mscratch <= '0;
      mepc <= '0;
      mcause <= '0;
      mtval <= '0;
      mip <= '0;
      cycle_count <= '0;
      instret_count <= '0;
      csr_result <= '0;
      csr_valid <= '0;
      priv_mode <= 2'b11;  // Start in M-mode
      csr_exception <= '0;
    end else begin
      // Increment counters
      cycle_count <= cycle_count + 1;
      if (cp_valid && cp_select == CP_CSR) instret_count <= instret_count + 1;

      // CSR operations
      csr_valid <= 1'b0;
      csr_exception <= 1'b0;

      if (cp_valid && cp_select == CP_CSR) begin
        csr_valid <= 1'b1;

        // Read CSR - with default case to handle all addresses
        case (csr_addr)
          CSR_MSTATUS:  csr_result <= mstatus;
          CSR_MISA:     csr_result <= misa;
          CSR_MIE:      csr_result <= mie;
          CSR_MTVEC:    csr_result <= mtvec;
          CSR_MSCRATCH: csr_result <= mscratch;
          CSR_MEPC:     csr_result <= mepc;
          CSR_MCAUSE:   csr_result <= mcause;
          CSR_MTVAL:    csr_result <= mtval;
          CSR_MIP:      csr_result <= mip;
          CSR_CYCLE:    csr_result <= cycle_count[31:0];
          CSR_CYCLEH:   csr_result <= cycle_count[63:32];
          CSR_INSTRET:  csr_result <= instret_count[31:0];
          CSR_INSTRETH: csr_result <= instret_count[63:32];
          default:      csr_result <= '0;  // Return 0 for unimplemented CSRs
        endcase

        // Write CSR (for CSRRW, CSRRS, CSRRC)
        if (funct3 != 3'b000 && funct3 != 3'b100) begin  // Not read-only
          logic [31:0] new_value;
          logic [31:0] write_data;

          // Determine write data source
          write_data = (funct3[2]) ? {27'b0, rs1} : rs1_data;  // Immediate vs Register

          // Calculate new value based on operation
          case (funct3[1:0])
            2'b01:   new_value = write_data;  // CSRRW/CSRRWI
            2'b10:   new_value = csr_result | write_data;  // CSRRS/CSRRSI
            2'b11:   new_value = csr_result & ~write_data;  // CSRRC/CSRRCI
            default: new_value = csr_result;
          endcase

          // Write to appropriate CSR - with default case
          case (csr_addr)
            CSR_MSTATUS:  mstatus <= new_value;
            CSR_MIE:      mie <= new_value;
            CSR_MTVEC:    mtvec <= new_value;
            CSR_MSCRATCH: mscratch <= new_value;
            CSR_MEPC:     mepc <= new_value;
            CSR_MCAUSE:   mcause <= new_value;
            CSR_MTVAL:    mtval <= new_value;
            default:      ;  // Ignore writes to unimplemented or read-only CSRs
          endcase
        end

        // Handle ECALL and EBREAK
        if (funct3 == 3'b000 && rs1 == 5'b00000 && rd == 5'b00000) begin
          if (instruction[20] == 1'b0) begin  // ECALL
            mcause <= (priv_mode == 2'b00) ? 32'd8 :  // ECALL from U-mode
            (priv_mode == 2'b01) ? 32'd9 :  // ECALL from S-mode
            32'd11;  // ECALL from M-mode
            mepc <= pc;
            mstatus[7] <= mstatus[3];  // MPIE = MIE
            mstatus[3] <= 1'b0;  // MIE = 0
            csr_exception <= 1'b1;
          end else begin  // EBREAK
            mcause <= 32'd3;  // Breakpoint exception
            mepc <= pc;
            csr_exception <= 1'b1;
          end
        end
      end

      // Interrupt handling
      if (irq_signal && mie[7] && mstatus[3]) begin  // Machine timer interrupt
        mip[7]     <= 1'b1;
        mcause     <= 32'h80000007;  // Machine timer interrupt (bit 31 set)
        mepc       <= pc;
        mstatus[7] <= mstatus[3];  // MPIE = MIE
        mstatus[3] <= 1'b0;  // MIE = 0
      end
    end
  end

  // ==========================================
  // Multiply/Divide Unit (CP1) - RV32M
  // ==========================================
  logic [31:0] mul_result;
  logic mul_valid;
  logic mul_busy;
  logic [2:0] mul_cycle_count;

  typedef enum logic [1:0] {
    MUL_IDLE = 2'b00,
    MUL_EXECUTE = 2'b01,
    MUL_COMPLETE = 2'b10,
    MUL_RESERVED = 2'b11  // Added to cover all enum values
  } mul_state_t;

  mul_state_t mul_state;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mul_state <= MUL_IDLE;
      mul_result <= '0;
      mul_valid <= '0;
      mul_busy <= '0;
      mul_cycle_count <= '0;
    end else begin
      case (mul_state)
        MUL_IDLE: begin
          mul_valid <= 1'b0;
          if (cp_valid && cp_select == CP_MUL) begin
            mul_state <= MUL_EXECUTE;
            mul_busy  <= 1'b1;
            // Different cycle counts for different operations
            case (funct3)
              3'b000, 3'b001, 3'b010, 3'b011: mul_cycle_count <= 3'd2;  // MUL variants
              3'b100, 3'b101, 3'b110, 3'b111: mul_cycle_count <= 3'd4;  // DIV variants
            endcase
          end
        end

        MUL_EXECUTE: begin
          if (mul_cycle_count > 0) begin
            mul_cycle_count <= mul_cycle_count - 1;
          end else begin
            mul_state <= MUL_COMPLETE;
            // RV32M operations
            case (funct3)
              3'b000: begin  // MUL
                logic [63:0] full_product;
                full_product = $signed(rs1_data) * $signed(rs2_data);
                mul_result <= full_product[31:0];
              end
              3'b001: begin  // MULH
                logic signed [63:0] full_product;
                full_product = $signed(rs1_data) * $signed(rs2_data);
                mul_result <= full_product[63:32];
              end
              3'b010: begin  // MULHSU
                logic signed [63:0] full_product;
                full_product = $signed(rs1_data) * $unsigned(rs2_data);
                mul_result <= full_product[63:32];
              end
              3'b011: begin  // MULHU
                logic [63:0] full_product;
                full_product = $unsigned(rs1_data) * $unsigned(rs2_data);
                mul_result <= full_product[63:32];
              end
              3'b100: begin  // DIV
                if (rs2_data == 0) mul_result <= 32'hFFFFFFFF;  // Division by zero
                else mul_result <= $signed(rs1_data) / $signed(rs2_data);
              end
              3'b101: begin  // DIVU
                if (rs2_data == 0) mul_result <= 32'hFFFFFFFF;
                else mul_result <= rs1_data / rs2_data;
              end
              3'b110: begin  // REM
                if (rs2_data == 0) mul_result <= rs1_data;
                else mul_result <= $signed(rs1_data) % $signed(rs2_data);
              end
              3'b111: begin  // REMU
                if (rs2_data == 0) mul_result <= rs1_data;
                else mul_result <= rs1_data % rs2_data;
              end
            endcase
          end
        end

        MUL_COMPLETE: begin
          mul_valid <= 1'b1;
          mul_busy  <= 1'b0;
          mul_state <= MUL_IDLE;
        end

        default: begin  // MUL_RESERVED - should never reach here
          mul_state <= MUL_IDLE;
          mul_valid <= 1'b0;
          mul_busy  <= 1'b0;
        end
      endcase
    end
  end

  // ==========================================
  // Custom Coprocessor (CP2) - Application specific
  // ==========================================
  logic [31:0] custom_result;
  logic custom_valid;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      custom_result <= '0;
      custom_valid  <= '0;
    end else begin
      custom_valid <= 1'b0;
      if (cp_valid && cp_select == CP_CUSTOM) begin
        custom_valid <= 1'b1;
        // Custom operations for Red Pitaya specific functions
        case (funct3)
          3'b000:  custom_result <= rs1_data & rs2_data;  // Bitwise AND
          3'b001:  custom_result <= rs1_data | rs2_data;  // Bitwise OR
          3'b010:  custom_result <= rs1_data ^ rs2_data;  // Bitwise XOR
          3'b011:  custom_result <= ~rs1_data;  // Bitwise NOT
          3'b100: begin  // Count leading zeros
            int count = 0;
            int i = 31;
            while (i >= 0 && rs1_data[i] == 1'b0) begin
              count++;
              i--;
            end
            custom_result <= count;
          end
          3'b101: begin  // Count trailing zeros
            int unsigned count;
            int j;
            bit stop;
            count = 0;
            stop  = 0;
            for (j = 0; j < 32; j++) begin
              if (!stop && rs1_data[j] == 1'b0) begin
                count++;
              end else begin
                stop = 1'b1;
              end
            end
            custom_result <= count;
          end
          3'b110: begin  // Population count (count ones)
            int unsigned count;
            int j;
            count = 0;
            for (j = 0; j < 32; j++) begin
              count += 32'(rs1_data[j]);  // Fixed: Explicit width cast to 32 bits
            end
            custom_result <= count;
          end
          3'b111:  custom_result <= {rs1_data[15:0], rs2_data[15:0]};  // Pack two 16-bit values
          default: custom_result <= '0;
        endcase
      end
    end
  end

  // ==========================================
  // Output multiplexing
  // ==========================================
  always_comb begin
    cp_result = '0;
    cp_result_valid = 1'b0;
    cp_stall = 1'b0;

    case (cp_select)
      CP_CSR: begin
        cp_result = csr_result;
        cp_result_valid = csr_valid;
        cp_stall = csr_exception;  // Stall on exceptions
      end
      CP_MUL: begin
        cp_result = mul_result;
        cp_result_valid = mul_valid;
        cp_stall = mul_busy;
      end
      CP_CUSTOM: begin
        cp_result = custom_result;
        cp_result_valid = custom_valid;
        cp_stall = 1'b0;  // Custom ops complete in 1 cycle
      end
      default: begin
        cp_result = '0;
        cp_result_valid = 1'b0;
        cp_stall = 1'b0;
      end
    endcase
  end

  // Debug signals
`ifdef SIMULATION
  always_ff @(posedge clk) begin
    if (cp_detected && cp_valid) begin
      $display("[COPROC] Detected instruction: opcode=0x%02x, funct3=0x%01x, cp_select=%d", opcode,
               funct3, cp_select);
    end
    if (cp_result_valid) begin
      $display("[COPROC] Result ready: 0x%08x", cp_result);
    end
  end
`endif

endmodule
