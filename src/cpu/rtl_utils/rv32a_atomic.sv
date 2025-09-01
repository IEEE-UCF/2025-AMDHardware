module rv32a_atomic #(
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32
) (
    input logic clk,
    input logic rst_n,

    // Decode interface
    input logic                  valid_i,     // Start atomic op
    input logic [           4:0] funct5_i,    // AMO operation
    input logic                  aq_i,        // Acquire bit
    input logic                  rl_i,        // Release bit
    input logic [ADDR_WIDTH-1:0] addr_i,      // Memory address
    input logic [DATA_WIDTH-1:0] rs1_data_i,  // Address for LR/SC/AMO
    input logic [DATA_WIDTH-1:0] rs2_data_i,  // Store data for SC/AMO

    // Result interface
    output logic                  ready_o,  // Ready for new op
    output logic                  valid_o,  // Result valid
    output logic [DATA_WIDTH-1:0] result_o, // Result data

    // LSU/Memory interface (reuse existing)
    output logic                  mem_req_o,
    output logic [ADDR_WIDTH-1:0] mem_addr_o,
    output logic [DATA_WIDTH-1:0] mem_wdata_o,
    output logic                  mem_we_o,
    output logic                  mem_lock_o,   // Exclusive/lock signal
    input  logic [DATA_WIDTH-1:0] mem_rdata_i,
    input  logic                  mem_ready_i,

    // Pipeline control
    input  logic flush_i,      // Flush reservation
    input  logic exception_i,  // Exception occurred
    output logic stall_req_o,  // Request pipeline stall

    // Snoop interface for multicore (optional)
    input logic                  snoop_valid_i,
    input logic [ADDR_WIDTH-1:0] snoop_addr_i
);

  // AMO function encoding (funct5)
  localparam logic [4:0] F5_LR = 5'b00010;
  localparam logic [4:0] F5_SC = 5'b00011;
  localparam logic [4:0] F5_SWAP = 5'b00001;
  localparam logic [4:0] F5_ADD = 5'b00000;
  localparam logic [4:0] F5_XOR = 5'b00100;
  localparam logic [4:0] F5_AND = 5'b01100;
  localparam logic [4:0] F5_OR = 5'b01000;
  localparam logic [4:0] F5_MIN = 5'b10000;
  localparam logic [4:0] F5_MAX = 5'b10100;
  localparam logic [4:0] F5_MINU = 5'b11000;
  localparam logic [4:0] F5_MAXU = 5'b11100;

  // FSM states for atomic microsequence
  typedef enum logic [2:0] {
    IDLE     = 3'b000,
    LOAD     = 3'b001,
    COMPUTE  = 3'b010,
    STORE    = 3'b011,
    COMPLETE = 3'b100,
    SC_CHECK = 3'b101
  } state_t;

  state_t state, next_state;

  // Reservation set tracking
  logic                  reservation_valid;
  logic [ADDR_WIDTH-3:0] reservation_addr;  // Word-aligned

  // Internal registers
  logic [           4:0] op_reg;
  logic aq_reg, rl_reg;
  logic [ADDR_WIDTH-1:0] addr_reg;
  logic [DATA_WIDTH-1:0] rs2_reg;
  logic [DATA_WIDTH-1:0] load_data;
  logic [DATA_WIDTH-1:0] store_data;
  logic                  sc_success;

  // Address alignment (word boundary)
  wire  [ADDR_WIDTH-3:0] aligned_addr = addr_i[ADDR_WIDTH-1:2];

  // Reservation management
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reservation_valid <= 1'b0;
      reservation_addr  <= '0;
    end else begin
      // Clear reservation on various conditions
      if (flush_i || exception_i) begin
        reservation_valid <= 1'b0;
      end  // Set reservation on LR
      else if (state == LOAD && op_reg == F5_LR && mem_ready_i) begin
        reservation_valid <= 1'b1;
        reservation_addr  <= addr_reg[ADDR_WIDTH-1:2];
      end  // Clear on successful SC
      else if (state == SC_CHECK && sc_success) begin
        reservation_valid <= 1'b0;
      end  // Clear on snoop to same address
      else if (snoop_valid_i && reservation_valid && 
                     snoop_addr_i[ADDR_WIDTH-1:2] == reservation_addr) begin
        reservation_valid <= 1'b0;
      end
    end
  end

  // FSM
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
        if (valid_i) begin
          if (funct5_i == F5_SC) begin
            next_state = SC_CHECK;
          end else begin
            next_state = LOAD;
          end
        end
      end

      LOAD: begin
        if (mem_ready_i) begin
          if (op_reg == F5_LR) begin
            next_state = COMPLETE;
          end else begin
            next_state = COMPUTE;
          end
        end
      end

      COMPUTE: begin
        next_state = STORE;
      end

      STORE: begin
        if (mem_ready_i) begin
          next_state = COMPLETE;
        end
      end

      SC_CHECK: begin
        if (reservation_valid && reservation_addr == addr_reg[ADDR_WIDTH-1:2]) begin
          next_state = STORE;
        end else begin
          next_state = COMPLETE;
        end
      end

      COMPLETE: begin
        next_state = IDLE;
      end

      default: next_state = IDLE;  // default incase it breaks
    endcase

    // Handle flush
    if (flush_i || exception_i) begin
      next_state = IDLE;
    end
  end

  // Operation execution
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      op_reg     <= '0;
      aq_reg     <= '0;
      rl_reg     <= '0;
      addr_reg   <= '0;
      rs2_reg    <= '0;
      load_data  <= '0;
      store_data <= '0;
      sc_success <= '0;
    end else begin
      case (state)
        IDLE: begin
          if (valid_i) begin
            op_reg <= funct5_i;
            aq_reg <= aq_i;
            rl_reg <= rl_i;
            addr_reg <= rs1_data_i;  // Address comes from rs1
            rs2_reg <= rs2_data_i;
            sc_success <= 1'b0;
          end
        end

        LOAD: begin
          if (mem_ready_i) begin
            load_data <= mem_rdata_i;
          end
        end

        COMPUTE: begin
          // Compute AMO result
          case (op_reg)
            F5_SWAP: store_data <= rs2_reg;
            F5_ADD:  store_data <= load_data + rs2_reg;
            F5_XOR:  store_data <= load_data ^ rs2_reg;
            F5_AND:  store_data <= load_data & rs2_reg;
            F5_OR:   store_data <= load_data | rs2_reg;
            F5_MIN: begin
              if ($signed(load_data) < $signed(rs2_reg)) store_data <= load_data;
              else store_data <= rs2_reg;
            end
            F5_MAX: begin
              if ($signed(load_data) > $signed(rs2_reg)) store_data <= load_data;
              else store_data <= rs2_reg;
            end
            F5_MINU: begin
              if (load_data < rs2_reg) store_data <= load_data;
              else store_data <= rs2_reg;
            end
            F5_MAXU: begin
              if (load_data > rs2_reg) store_data <= load_data;
              else store_data <= rs2_reg;
            end
            default: store_data <= load_data;
          endcase
        end

        SC_CHECK: begin
          if (reservation_valid && reservation_addr == addr_reg[ADDR_WIDTH-1:2]) begin
            sc_success <= 1'b1;
            store_data <= rs2_reg;
          end else begin
            sc_success <= 1'b0;
          end
        end

        default: ;  // default incase it breaks
      endcase
    end
  end

  // Memory interface control
  always_comb begin
    mem_req_o   = 1'b0;
    mem_addr_o  = addr_reg;
    mem_wdata_o = store_data;
    mem_we_o    = 1'b0;
    mem_lock_o  = 1'b0;

    case (state)
      LOAD: begin
        mem_req_o  = 1'b1;
        mem_we_o   = 1'b0;
        mem_lock_o = (op_reg == F5_LR) || (op_reg != F5_LR && op_reg != F5_SC);
      end

      STORE: begin
        mem_req_o  = 1'b1;
        mem_we_o   = 1'b1;
        mem_lock_o = 1'b1;
      end

      default: begin
        mem_req_o = 1'b0;
        mem_addr_o = addr_reg;
        mem_wdata_o = store_data;
        mem_we_o = 1'b0;
        mem_lock_o = 1'b0;
      end
    endcase
  end

  // Result output
  always_comb begin
    result_o = '0;

    if (op_reg == F5_SC) begin
      // SC returns 0 on success, non-zero on failure
      result_o = sc_success ? 32'h0 : 32'h1;
    end else if (op_reg == F5_LR || (state == COMPLETE && op_reg != F5_SC)) begin
      // LR and AMOs return the loaded value
      result_o = load_data;
    end
  end

  // Control signals
  assign ready_o     = (state == IDLE);
  assign valid_o     = (state == COMPLETE);
  assign stall_req_o = (state != IDLE) && (state != COMPLETE);

endmodule

