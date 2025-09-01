module register_file_system #(
    parameter DATA_WIDTH  = 32,  // Fixed to 32-bit for Red Pitaya
    parameter INT_REG_NUM = 32,  // Integer registers (x0-x31)
    parameter FP_REG_NUM  = 32,  // Floating point registers (f0-f31)
    parameter VEC_REG_NUM = 32,  // Vector registers (v0-v31) for future use
    parameter CSR_NUM     = 32   // CSR registers (simplified set)
) (
    input logic clk,
    input logic rst_n,

    // Read ports (2 read ports for rs1, rs2)
    input  logic [           4:0] int_rs1_addr,
    input  logic [           4:0] int_rs2_addr,
    output logic [DATA_WIDTH-1:0] int_rs1_data,
    output logic [DATA_WIDTH-1:0] int_rs2_data,

    // Write port
    input logic [           4:0] int_rd_addr,
    input logic [DATA_WIDTH-1:0] int_rd_data,
    input logic                  int_rd_write,

    // Read ports (3 read ports for FMA operations)
    input  logic [           4:0] fp_rs1_addr,
    input  logic [           4:0] fp_rs2_addr,
    input  logic [           4:0] fp_rs3_addr,
    output logic [DATA_WIDTH-1:0] fp_rs1_data,
    output logic [DATA_WIDTH-1:0] fp_rs2_data,
    output logic [DATA_WIDTH-1:0] fp_rs3_data,

    // Write port
    input logic [           4:0] fp_rd_addr,
    input logic [DATA_WIDTH-1:0] fp_rd_data,
    input logic                  fp_rd_write,

    input  logic [          11:0] csr_addr,
    input  logic [DATA_WIDTH-1:0] csr_wdata,
    input  logic                  csr_write,
    input  logic [           2:0] csr_op,     // 001=RW, 010=RS, 011=RC
    output logic [DATA_WIDTH-1:0] csr_rdata,

    // Program counter for exceptions
    input logic [DATA_WIDTH-1:0] pc,

    // Exception/Interrupt handling
    input logic       exception,
    input logic [3:0] exception_code,
    input logic       interrupt,
    input logic       mret,            // Return from M-mode
    input logic       sret,            // Return from S-mode

    // Privilege mode
    output logic [1:0] priv_mode,  // 00=U, 01=S, 11=M

    // Shadow register control (for fast interrupt handling)
    input logic shadow_swap,

    // Debug interface
    input  logic                  debug_mode,
    input  logic [           4:0] debug_reg_addr,
    output logic [DATA_WIDTH-1:0] debug_reg_data
);

  logic [DATA_WIDTH-1:0] int_regs[INT_REG_NUM-1:0];
  logic [DATA_WIDTH-1:0] int_shadow_regs[INT_REG_NUM-1:0];  // Shadow for interrupts
  logic shadow_active;

  // Integer register read
  always_comb begin
    if (shadow_active) begin
      int_rs1_data = (int_rs1_addr == 0) ? '0 : int_shadow_regs[int_rs1_addr];
      int_rs2_data = (int_rs2_addr == 0) ? '0 : int_shadow_regs[int_rs2_addr];
    end else begin
      int_rs1_data = (int_rs1_addr == 0) ? '0 : int_regs[int_rs1_addr];
      int_rs2_data = (int_rs2_addr == 0) ? '0 : int_regs[int_rs2_addr];
    end
  end

  // Integer register write
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < INT_REG_NUM; i++) begin
        int_regs[i] <= '0;
        int_shadow_regs[i] <= '0;
      end
      shadow_active <= 1'b0;
    end else begin
      // Shadow register control
      if (shadow_swap) begin
        shadow_active <= ~shadow_active;
      end

      // Write to active register set
      if (int_rd_write && int_rd_addr != 0) begin
        if (shadow_active) begin
          int_shadow_regs[int_rd_addr] <= int_rd_data;
        end else begin
          int_regs[int_rd_addr] <= int_rd_data;
        end
      end
    end
  end


  logic [DATA_WIDTH-1:0] fp_regs[FP_REG_NUM-1:0];

  // FP register read (3 ports for FMA)
  assign fp_rs1_data = fp_regs[fp_rs1_addr];
  assign fp_rs2_data = fp_regs[fp_rs2_addr];
  assign fp_rs3_data = fp_regs[fp_rs3_addr];

  // FP register write
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < FP_REG_NUM; i++) begin
        fp_regs[i] <= '0;
      end
    end else begin
      if (fp_rd_write) begin
        fp_regs[fp_rd_addr] <= fp_rd_data;
      end
    end
  end

  // Machine-level CSRs for RV32
  logic [DATA_WIDTH-1:0] mstatus;  // Machine status
  logic [DATA_WIDTH-1:0] misa;  // ISA and extensions
  logic [DATA_WIDTH-1:0] mie;  // Machine interrupt enable
  logic [DATA_WIDTH-1:0] mtvec;  // Machine trap vector
  logic [DATA_WIDTH-1:0] mscratch;  // Machine scratch
  logic [DATA_WIDTH-1:0] mepc;  // Machine exception PC
  logic [DATA_WIDTH-1:0] mcause;  // Machine trap cause
  logic [DATA_WIDTH-1:0] mtval;  // Machine trap value
  logic [DATA_WIDTH-1:0] mip;  // Machine interrupt pending

  // Supervisor-level CSRs
  logic [DATA_WIDTH-1:0] sstatus;  // Supervisor status
  logic [DATA_WIDTH-1:0] sie;  // Supervisor interrupt enable
  logic [DATA_WIDTH-1:0] stvec;  // Supervisor trap vector
  logic [DATA_WIDTH-1:0] sscratch;  // Supervisor scratch
  logic [DATA_WIDTH-1:0] sepc;  // Supervisor exception PC
  logic [DATA_WIDTH-1:0] scause;  // Supervisor trap cause
  logic [DATA_WIDTH-1:0] stval;  // Supervisor trap value
  logic [DATA_WIDTH-1:0] sip;  // Supervisor interrupt pending
  logic [DATA_WIDTH-1:0] satp;  // Supervisor address translation

  // Performance counters (64-bit even in RV32)
  logic [          63:0] cycle_counter;
  logic [          63:0] instret_counter;
  logic [          63:0] time_counter;

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

  localparam CSR_SSTATUS = 12'h100;
  localparam CSR_SIE = 12'h104;
  localparam CSR_STVEC = 12'h105;
  localparam CSR_SSCRATCH = 12'h140;
  localparam CSR_SEPC = 12'h141;
  localparam CSR_SCAUSE = 12'h142;
  localparam CSR_STVAL = 12'h143;
  localparam CSR_SIP = 12'h144;
  localparam CSR_SATP = 12'h180;

  localparam CSR_CYCLE = 12'hC00;
  localparam CSR_TIME = 12'hC01;
  localparam CSR_INSTRET = 12'hC02;
  localparam CSR_CYCLEH = 12'hC80;
  localparam CSR_TIMEH = 12'hC81;
  localparam CSR_INSTRETH = 12'hC82;

  // CSR read logic
  always_comb begin
    case (csr_addr)
      CSR_MSTATUS:  csr_rdata = mstatus;
      CSR_MISA:     csr_rdata = misa;
      CSR_MIE:      csr_rdata = mie;
      CSR_MTVEC:    csr_rdata = mtvec;
      CSR_MSCRATCH: csr_rdata = mscratch;
      CSR_MEPC:     csr_rdata = mepc;
      CSR_MCAUSE:   csr_rdata = mcause;
      CSR_MTVAL:    csr_rdata = mtval;
      CSR_MIP:      csr_rdata = mip;

      CSR_SSTATUS:  csr_rdata = sstatus;
      CSR_SIE:      csr_rdata = sie;
      CSR_STVEC:    csr_rdata = stvec;
      CSR_SSCRATCH: csr_rdata = sscratch;
      CSR_SEPC:     csr_rdata = sepc;
      CSR_SCAUSE:   csr_rdata = scause;
      CSR_STVAL:    csr_rdata = stval;
      CSR_SIP:      csr_rdata = sip;
      CSR_SATP:     csr_rdata = satp;

      CSR_CYCLE:    csr_rdata = cycle_counter[31:0];
      CSR_TIME:     csr_rdata = time_counter[31:0];
      CSR_INSTRET:  csr_rdata = instret_counter[31:0];
      CSR_CYCLEH:   csr_rdata = cycle_counter[63:32];
      CSR_TIMEH:    csr_rdata = time_counter[63:32];
      CSR_INSTRETH: csr_rdata = instret_counter[63:32];

      default: csr_rdata = '0;
    endcase
  end

  // CSR write logic
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mstatus <= '0;
      misa <= 32'h40141101;  // RV32IMAC
      mie <= '0;
      mtvec <= '0;
      mscratch <= '0;
      mepc <= '0;
      mcause <= '0;
      mtval <= '0;
      mip <= '0;

      sstatus <= '0;
      sie <= '0;
      stvec <= '0;
      sscratch <= '0;
      sepc <= '0;
      scause <= '0;
      stval <= '0;
      sip <= '0;
      satp <= '0;

      cycle_counter <= '0;
      instret_counter <= '0;
      time_counter <= '0;

      priv_mode <= 2'b11;  // Start in M-mode
    end else begin
      // Increment counters
      cycle_counter <= cycle_counter + 1;
      time_counter  <= time_counter + 1;
      if (int_rd_write || fp_rd_write) begin
        instret_counter <= instret_counter + 1;
      end

      // CSR write operations
      if (csr_write) begin
        logic [DATA_WIDTH-1:0] new_value;

        // Compute new value based on operation
        case (csr_op)
          3'b001:  new_value = csr_wdata;  // CSRRW
          3'b010:  new_value = csr_rdata | csr_wdata;  // CSRRS
          3'b011:  new_value = csr_rdata & ~csr_wdata;  // CSRRC
          default: new_value = csr_rdata;
        endcase

        // Write to appropriate CSR
        case (csr_addr)
          CSR_MSTATUS:  mstatus <= new_value;
          CSR_MIE:      mie <= new_value;
          CSR_MTVEC:    mtvec <= new_value;
          CSR_MSCRATCH: mscratch <= new_value;
          CSR_MEPC:     mepc <= new_value;
          CSR_MCAUSE:   mcause <= new_value;
          CSR_MTVAL:    mtval <= new_value;

          CSR_SSTATUS:  sstatus <= new_value;
          CSR_SIE:      sie <= new_value;
          CSR_STVEC:    stvec <= new_value;
          CSR_SSCRATCH: sscratch <= new_value;
          CSR_SEPC:     sepc <= new_value;
          CSR_SCAUSE:   scause <= new_value;
          CSR_STVAL:    stval <= new_value;
          CSR_SATP:     satp <= new_value;
          default: ;
        endcase
      end

      // Exception handling
      if (exception) begin
        if (priv_mode == 2'b11 || (priv_mode < 2'b11 && !mstatus[3])) begin
          // Trap to M-mode
          mepc           <= pc;
          mcause         <= {28'b0, exception_code};
          mstatus[7]     <= mstatus[3];  // MPIE = MIE
          mstatus[3]     <= 1'b0;  // MIE = 0
          mstatus[12:11] <= priv_mode;  // MPP = current mode
          priv_mode      <= 2'b11;  // Enter M-mode
        end else begin
          // Trap to S-mode
          sepc       <= pc;
          scause     <= {28'b0, exception_code};
          sstatus[5] <= sstatus[1];  // SPIE = SIE
          sstatus[1] <= 1'b0;  // SIE = 0
          sstatus[8] <= priv_mode[0];  // SPP = current mode
          priv_mode  <= 2'b01;  // Enter S-mode
        end
      end

      // Interrupt handling
      if (interrupt) begin
        mip[7] <= 1'b1;  // Set machine timer interrupt pending
      end

      // Return from trap
      if (mret) begin
        mstatus[3]     <= mstatus[7];  // MIE = MPIE
        mstatus[7]     <= 1'b1;  // MPIE = 1
        priv_mode      <= mstatus[12:11];  // Restore previous mode
        mstatus[12:11] <= 2'b00;  // MPP = U
      end else if (sret) begin
        sstatus[1] <= sstatus[5];  // SIE = SPIE
        sstatus[5] <= 1'b1;  // SPIE = 1
        priv_mode  <= {1'b0, sstatus[8]};  // Restore previous mode
        sstatus[8] <= 1'b0;  // SPP = U
      end
    end
  end


  logic [DATA_WIDTH-1:0] vec_regs[VEC_REG_NUM-1:0];

  // Vector registers for future SIMD/Vector extensions
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < VEC_REG_NUM; i++) begin
        vec_regs[i] <= '0;
      end
    end
  end


  always_comb begin
    if (debug_mode) begin
      debug_reg_data = shadow_active ? int_shadow_regs[debug_reg_addr] : int_regs[debug_reg_addr];
    end else begin
      debug_reg_data = '0;
    end
  end


`ifdef FORMAL
  // x0 should always be zero
  always @(posedge clk) begin
    assert (int_regs[0] == '0);
    assert (int_shadow_regs[0] == '0);
  end

  // Privilege mode should be valid
  always @(posedge clk) begin
    assert (priv_mode != 2'b10);  // Invalid mode
  end
`endif

endmodule

module register_bank_cpu #(
    parameter REG_NUM = 32,
    parameter DATA_WIDTH = 32  // Fixed to 32-bit
) (
    input  logic                       clk,
    input  logic                       reset,
    input  logic [$clog2(REG_NUM)-1:0] write_addr,
    input  logic [     DATA_WIDTH-1:0] data_in,
    input  logic                       write_en,
    input  logic [$clog2(REG_NUM)-1:0] read_addr_a,
    input  logic [$clog2(REG_NUM)-1:0] read_addr_b,
    output logic [     DATA_WIDTH-1:0] data_out_a,
    output logic [     DATA_WIDTH-1:0] data_out_b
);

  // Instance of unified register file
  register_file_system #(
      .DATA_WIDTH (DATA_WIDTH),
      .INT_REG_NUM(REG_NUM)
  ) regfile (
      .clk  (clk),
      .rst_n(~reset),

      // Integer register interface
      .int_rs1_addr(read_addr_a),
      .int_rs2_addr(read_addr_b),
      .int_rs1_data(data_out_a),
      .int_rs2_data(data_out_b),
      .int_rd_addr (write_addr),
      .int_rd_data (data_in),
      .int_rd_write(write_en),

      // Unused ports
      .fp_rs1_addr('0),
      .fp_rs2_addr('0),
      .fp_rs3_addr('0),
      .fp_rs1_data(),
      .fp_rs2_data(),
      .fp_rs3_data(),
      .fp_rd_addr('0),
      .fp_rd_data('0),
      .fp_rd_write('0),
      .csr_addr('0),
      .csr_wdata('0),
      .csr_write('0),
      .csr_op('0),
      .csr_rdata(),
      .pc('0),
      .exception('0),
      .exception_code('0),
      .interrupt('0),
      .mret('0),
      .sret('0),
      .priv_mode(),
      .shadow_swap('0),
      .debug_mode('0),
      .debug_reg_addr('0),
      .debug_reg_data()
  );

endmodule

