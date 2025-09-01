module red_pitaya_cpu_wrapper #(
    parameter C_S_AXI_DATA_WIDTH = 32,
    parameter C_S_AXI_ADDR_WIDTH = 32,
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter INST_WIDTH = 32,
    parameter REG_NUM = 32
) (
    // AXI4-Lite Clock and Reset
    input logic s_axi_aclk,
    input logic s_axi_aresetn,

    // AXI4-Lite Control Interface
    // Write Address Channel
    input  logic [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input  logic [                   2:0] s_axi_awprot,
    input  logic                          s_axi_awvalid,
    output logic                          s_axi_awready,

    // Write Data Channel
    input  logic [    C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input  logic [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input  logic                              s_axi_wvalid,
    output logic                              s_axi_wready,

    // Write Response Channel
    output logic [1:0] s_axi_bresp,
    output logic       s_axi_bvalid,
    input  logic       s_axi_bready,

    // Read Address Channel
    input  logic [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input  logic [                   2:0] s_axi_arprot,
    input  logic                          s_axi_arvalid,
    output logic                          s_axi_arready,

    // Read Data Channel
    output logic [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output logic [                   1:0] s_axi_rresp,
    output logic                          s_axi_rvalid,
    input  logic                          s_axi_rready,

    // External signals
    input  logic       ext_interrupt,
    output logic [7:0] led_status,
    output logic       cpu_active
);

  // Internal signals
  logic                  cpu_clk;
  logic                  cpu_rst_n;
  logic [           3:0] reset_sync;

  // CPU control registers (accessible via AXI)
  logic                  cpu_enable;
  logic                  cpu_reset_req;
  logic                  single_step_mode;
  logic [          31:0] cpu_start_pc;
  logic [          31:0] cpu_status;
  logic [          31:0] cpu_cycles;
  logic [          31:0] cpu_instructions;

  // Memory interfaces
  logic [ADDR_WIDTH-1:0] imem_addr;
  logic [INST_WIDTH-1:0] imem_read_data;
  logic                  imem_read;
  logic                  imem_ready;

  logic [ADDR_WIDTH-1:0] dmem_addr;
  logic [DATA_WIDTH-1:0] dmem_write_data;
  logic                  dmem_read;
  logic                  dmem_write;
  logic [           3:0] dmem_byte_enable;
  logic [DATA_WIDTH-1:0] dmem_read_data;
  logic                  dmem_ready;

  // Debug signals
  logic [ADDR_WIDTH-1:0] debug_pc;
  logic                  debug_stall;
  logic [           3:0] debug_state;
  logic                  cp_instruction_detected;
  logic [INST_WIDTH-1:0] cp_instruction_out;

  // 125MHz clock for CPU
  assign cpu_clk = s_axi_aclk;


  // Reset synchronization
  always_ff @(posedge cpu_clk) begin
    if (!s_axi_aresetn || cpu_reset_req) begin
      reset_sync <= 4'h0;
    end else begin
      reset_sync <= {reset_sync[2:0], 1'b1};
    end
  end
  assign cpu_rst_n = reset_sync[3] && cpu_enable;

  // AXI4-Lite Interface State Machine
  typedef enum logic [2:0] {
    IDLE,
    WRITE_ADDR,
    WRITE_DATA,
    WRITE_RESP,
    READ_ADDR,
    READ_DATA
  } axi_state_t;

  axi_state_t axi_state, axi_next_state;
  logic [C_S_AXI_ADDR_WIDTH-1:0] axi_awaddr_reg, axi_araddr_reg;
  logic [C_S_AXI_DATA_WIDTH-1:0] axi_wdata_reg;
  logic [(C_S_AXI_DATA_WIDTH/8)-1:0] axi_wstrb_reg;

  // AXI state machine
  always_ff @(posedge s_axi_aclk) begin
    if (!s_axi_aresetn) begin
      axi_state <= IDLE;
    end else begin
      axi_state <= axi_next_state;
    end
  end

  // AXI next state logic
  always_comb begin
    axi_next_state = axi_state;

    case (axi_state)
      IDLE: begin
        if (s_axi_awvalid) axi_next_state = WRITE_ADDR;
        else if (s_axi_arvalid) axi_next_state = READ_ADDR;
      end

      WRITE_ADDR: begin
        if (s_axi_wvalid) axi_next_state = WRITE_DATA;
      end

      WRITE_DATA: begin
        axi_next_state = WRITE_RESP;
      end

      WRITE_RESP: begin
        if (s_axi_bready) axi_next_state = IDLE;
      end

      READ_ADDR: begin
        axi_next_state = READ_DATA;
      end

      READ_DATA: begin
        if (s_axi_rready) axi_next_state = IDLE;
      end

      default: axi_next_state = IDLE;
    endcase
  end

  // AXI write handling
  always_ff @(posedge s_axi_aclk) begin
    if (!s_axi_aresetn) begin
      axi_awaddr_reg <= '0;
      axi_wdata_reg <= '0;
      axi_wstrb_reg <= '0;
      cpu_enable <= 1'b0;
      cpu_reset_req <= 1'b0;
      single_step_mode <= 1'b0;
      cpu_start_pc <= 32'h0;
    end else begin
      cpu_reset_req <= 1'b0;  // Auto-clear

      if (s_axi_awvalid && s_axi_awready) begin
        axi_awaddr_reg <= s_axi_awaddr;
      end

      if (s_axi_wvalid && s_axi_wready) begin
        axi_wdata_reg <= s_axi_wdata;
        axi_wstrb_reg <= s_axi_wstrb;

        // Decode register writes based on address
        case (axi_awaddr_reg[11:2])
          10'h000: cpu_enable <= s_axi_wdata[0];
          10'h001: cpu_reset_req <= s_axi_wdata[0];
          10'h002: single_step_mode <= s_axi_wdata[0];
          10'h003: cpu_start_pc <= s_axi_wdata;
          default: ;  // do nothing
        endcase
      end
    end
  end

  // AXI read handling
  always_ff @(posedge s_axi_aclk) begin
    if (!s_axi_aresetn) begin
      axi_araddr_reg <= '0;
    end else begin
      if (s_axi_arvalid && s_axi_arready) begin
        axi_araddr_reg <= s_axi_araddr;
      end
    end
  end

  always_comb begin
    s_axi_rdata = 32'h0;
    if (axi_state == READ_DATA) begin
      // Decode register reads based on address
      case (axi_araddr_reg[11:2])
        10'h000: s_axi_rdata = {31'b0, cpu_enable};
        10'h001: s_axi_rdata = {31'b0, cpu_reset_req};
        10'h002: s_axi_rdata = {31'b0, single_step_mode};
        10'h003: s_axi_rdata = cpu_start_pc;
        10'h004: s_axi_rdata = cpu_status;
        10'h005: s_axi_rdata = debug_pc;
        10'h006: s_axi_rdata = cpu_cycles;
        10'h007: s_axi_rdata = cpu_instructions;
        10'h008: s_axi_rdata = {28'b0, debug_state};
        default: s_axi_rdata = 32'hDEADBEEF;
      endcase
    end
  end

  // AXI4-Lite handshake signals
  assign s_axi_awready = (axi_state == IDLE || axi_state == WRITE_ADDR);
  assign s_axi_wready  = (axi_state == WRITE_ADDR || axi_state == WRITE_DATA);
  assign s_axi_bvalid  = (axi_state == WRITE_RESP);
  assign s_axi_bresp   = 2'b00;  // OKAY
  assign s_axi_arready = (axi_state == IDLE);
  assign s_axi_rvalid  = (axi_state == READ_DATA);
  assign s_axi_rresp   = 2'b00;  // OKAY

  // CPU Instance
  cpu_top #(
      .ADDR_WIDTH(ADDR_WIDTH),
      .DATA_WIDTH(DATA_WIDTH),
      .INST_WIDTH(INST_WIDTH),
      .REG_NUM(REG_NUM)
  ) cpu_core (
      .clk(cpu_clk),
      .rst_n(cpu_rst_n),
      .interr(ext_interrupt),

      // Instruction Memory Interface
      .imem_addr(imem_addr),
      .imem_read_data(imem_read_data),
      .imem_read(imem_read),
      .imem_ready(imem_ready),

      // Data Memory Interface
      .dmem_addr(dmem_addr),
      .dmem_write_data(dmem_write_data),
      .dmem_read(dmem_read),
      .dmem_write(dmem_write),
      .dmem_byte_enable(dmem_byte_enable),
      .dmem_read_data(dmem_read_data),
      .dmem_ready(dmem_ready),

      // Coprocessor Interface
      .cp_instruction_detected(cp_instruction_detected),
      .cp_instruction_out(cp_instruction_out),
      .cp_stall_external(1'b0),  // No external coprocessor for now

      // Debug Interface
      .debug_pc(debug_pc),
      .debug_stall(debug_stall),
      .debug_state(debug_state)
  );

  // Memory System Instance
  memory_system #(
      .ADDR_WIDTH(ADDR_WIDTH),
      .DATA_WIDTH(DATA_WIDTH),
      .INST_WIDTH(INST_WIDTH),
      .IMEM_SIZE(8192),  // 8KB instruction memory
      .DMEM_SIZE(8192)  // 8KB data memory
  ) mem_sys (
      .clk  (cpu_clk),
      .rst_n(cpu_rst_n),

      // Instruction Port
      .imem_addr(imem_addr),
      .imem_read_data(imem_read_data),
      .imem_read(imem_read),
      .imem_ready(imem_ready),
      .imem_access_count(),

      // Data Port
      .dmem_addr(dmem_addr),
      .dmem_write_data(dmem_write_data),
      .dmem_read(dmem_read),
      .dmem_write(dmem_write),
      .dmem_byte_enable(dmem_byte_enable),
      .dmem_read_data(dmem_read_data),
      .dmem_ready(dmem_ready),
      .dmem_access_count()

      // Removed cache control signals - using direct BRAM access
  );

  // Performance counters
  always_ff @(posedge cpu_clk) begin
    if (!cpu_rst_n) begin
      cpu_cycles <= '0;
      cpu_instructions <= '0;
    end else begin
      cpu_cycles <= cpu_cycles + 1;
      if (imem_read && imem_ready && !debug_stall) cpu_instructions <= cpu_instructions + 1;
    end
  end

  // Status register
  always_comb begin
    cpu_status = {24'b0, cp_instruction_detected, debug_stall, 2'b0, debug_state};
  end

  // LED Status
  always_ff @(posedge cpu_clk) begin
    led_status <= {
      cpu_enable,
      cpu_rst_n,
      debug_stall,
      imem_read,
      dmem_read | dmem_write,
      cp_instruction_detected,
      ext_interrupt,
      cpu_cycles[23]  // Heartbeat
    };
  end

  assign cpu_active = cpu_enable && cpu_rst_n && !debug_stall;

endmodule
