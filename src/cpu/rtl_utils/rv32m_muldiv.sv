module rv32m_muldiv #(
    parameter MUL_LAT = 2,  // Multiply latency cycles
    parameter DIV_LAT = 32  // Divide latency cycles
) (
    input logic clk,
    input logic rst_n,

    // Control interface
    input logic        valid_i,     // Start operation
    input logic [ 2:0] funct3_i,    // Operation select
    input logic [31:0] rs1_data_i,  // Operand 1
    input logic [31:0] rs2_data_i,  // Operand 2

    // Result interface (ready/valid handshake)
    output logic        ready_o,  // Ready to accept new op
    output logic        valid_o,  // Result valid
    output logic [31:0] result_o, // Operation result

    // Pipeline control
    input logic flush_i,  // Flush/abort operation
    input logic stall_i   // Stall pipeline
);

  // Operation encoding (funct3)
  localparam logic [2:0] F3_MUL = 3'b000;
  localparam logic [2:0] F3_MULH = 3'b001;
  localparam logic [2:0] F3_MULHSU = 3'b010;
  localparam logic [2:0] F3_MULHU = 3'b011;
  localparam logic [2:0] F3_DIV = 3'b100;
  localparam logic [2:0] F3_DIVU = 3'b101;
  localparam logic [2:0] F3_REM = 3'b110;
  localparam logic [2:0] F3_REMU = 3'b111;

  // FSM states
  typedef enum logic [1:0] {
    IDLE  = 2'b00,
    EXEC  = 2'b01,
    DONE  = 2'b10,
    FLUSH = 2'b11
  } state_t;

  state_t state, next_state;

  // Internal registers
  logic [2:0] op_reg;
  logic [31:0] op_a, op_b;
  logic [31:0] result_reg;
  logic [ 5:0] cycle_cnt;  // Up to 63 cycles
  logic        is_div_op;

  // Intermediate calculation signals
  logic signed [31:0] op_a_signed, op_b_signed;
  logic signed [63:0] mul_result_signed;
  logic        [63:0] mul_result_unsigned;
  logic signed [63:0] mul_result_su;

  assign op_a_signed = $signed(op_a);
  assign op_b_signed = $signed(op_b);

  // State machine
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state <= IDLE;
    end else begin
      state <= next_state;
    end
  end

  always_comb begin
    next_state = state;

    case (state)
      IDLE: begin
        if (valid_i && !stall_i) begin
          next_state = EXEC;
        end
      end

      EXEC: begin
        if (flush_i) begin
          next_state = FLUSH;
        end else if (cycle_cnt == 0 && !stall_i) begin
          next_state = DONE;
        end
      end

      DONE: begin
        if (!stall_i) begin
          next_state = IDLE;
        end
      end

      FLUSH: begin
        next_state = IDLE;
      end

      default: next_state = IDLE;  // incase it breaks
    endcase
  end

  // Operation execution
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      op_reg     <= '0;
      op_a       <= '0;
      op_b       <= '0;
      result_reg <= '0;
      cycle_cnt  <= '0;
      is_div_op  <= '0;
    end else begin
      case (state)
        IDLE: begin
          if (valid_i && !stall_i) begin
            op_reg    <= funct3_i;
            op_a      <= rs1_data_i;
            op_b      <= rs2_data_i;
            is_div_op <= (funct3_i[2] == 1'b1);  // DIV/REM ops

            // Set cycle counter based on operation
            if (funct3_i[2] == 1'b0) begin
              cycle_cnt <= MUL_LAT - 1;
            end else begin
              cycle_cnt <= DIV_LAT - 1;
            end
          end
        end

        EXEC: begin
          if (!stall_i && cycle_cnt > 0) begin
            cycle_cnt <= cycle_cnt - 1;
          end

          // Calculate results (combinational, but registered at end)
          if (cycle_cnt == 0) begin
            case (op_reg)
              F3_MUL: begin
                mul_result_signed = op_a_signed * op_b_signed;
                result_reg <= mul_result_signed[31:0];
              end

              F3_MULH: begin
                mul_result_signed = op_a_signed * op_b_signed;
                result_reg <= mul_result_signed[63:32];
              end

              F3_MULHSU: begin
                mul_result_su = op_a_signed * $signed({1'b0, op_b});
                result_reg <= mul_result_su[63:32];
              end

              F3_MULHU: begin
                mul_result_unsigned = {32'b0, op_a} * {32'b0, op_b};
                result_reg <= mul_result_unsigned[63:32];
              end

              F3_DIV: begin
                if (op_b == 32'h0) begin
                  result_reg <= 32'hFFFFFFFF;  // -1
                end else if (op_a == 32'h80000000 && op_b == 32'hFFFFFFFF) begin
                  result_reg <= 32'h80000000;  // INT_MIN
                end else begin
                  result_reg <= $signed(op_a_signed) / $signed(op_b_signed);
                end
              end

              F3_DIVU: begin
                if (op_b == 32'h0) begin
                  result_reg <= 32'hFFFFFFFF;
                end else begin
                  result_reg <= op_a / op_b;
                end
              end

              F3_REM: begin
                if (op_b == 32'h0) begin
                  result_reg <= op_a;  // Dividend
                end else if (op_a == 32'h80000000 && op_b == 32'hFFFFFFFF) begin
                  result_reg <= 32'h0;
                end else begin
                  result_reg <= $signed(op_a_signed) % $signed(op_b_signed);
                end
              end

              F3_REMU: begin
                if (op_b == 32'h0) begin
                  result_reg <= op_a;
                end else begin
                  result_reg <= op_a % op_b;
                end
              end
            endcase
          end
        end

        FLUSH: begin
          cycle_cnt <= '0;
        end

        default: ;
      endcase
    end
  end

  // Output assignments
  assign ready_o  = (state == IDLE);
  assign valid_o  = (state == DONE) && !stall_i;
  assign result_o = result_reg;

endmodule

