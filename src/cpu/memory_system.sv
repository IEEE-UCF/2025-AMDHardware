module memory_system #(
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter INST_WIDTH = 32,
    parameter IMEM_SIZE  = 32768,  // 32KB instruction memory (8 BRAM blocks)
    parameter DMEM_SIZE  = 32768,  // 32KB data memory (8 BRAM blocks)
    parameter BURST_SIZE = 4
) (
    input logic clk,
    input logic rst_n,

    // Instruction Port
    input  logic [ADDR_WIDTH-1:0] imem_addr,
    output logic [INST_WIDTH-1:0] imem_read_data,
    input  logic                  imem_read,
    output logic                  imem_ready,

    // Data Port
    input  logic [ADDR_WIDTH-1:0] dmem_addr,
    input  logic [DATA_WIDTH-1:0] dmem_write_data,
    input  logic                  dmem_read,
    input  logic                  dmem_write,
    input  logic [           3:0] dmem_byte_enable,  // 4 bytes for 32-bit
    output logic [DATA_WIDTH-1:0] dmem_read_data,
    output logic                  dmem_ready,

    // Simplified control (removed cache control as we're using direct BRAM)
    
    // Debug outputs for testbench
    output logic [31:0] imem_access_count,
    output logic [31:0] dmem_access_count
);

  // Calculate the actual address width needed for memory arrays
  localparam IMEM_ADDR_WIDTH = $clog2(IMEM_SIZE / 4);  // 13 bits for 8192 words
  localparam DMEM_ADDR_WIDTH = $clog2(DMEM_SIZE / 4);  // 13 bits for 8192 words

  // Use Xilinx Block RAM for dedicated BRAM slices on Red Pitaya
  (* ram_style = "block" *) logic [INST_WIDTH-1:0] inst_mem[0:IMEM_SIZE/4-1];
  (* ram_style = "block" *) logic [DATA_WIDTH-1:0] data_mem[0:DMEM_SIZE/4-1];

  // Removed cache logic - using direct BRAM access for simplicity and efficiency

  // Initialize memory arrays
  initial begin
    // Initialize instruction memory with NOPs
    for (int i = 0; i < IMEM_SIZE / 4; i++) begin
      inst_mem[i] = 32'h00000013;  // NOP instruction
    end

    // Initialize first few instructions for testing
    inst_mem[0] = 32'h00000013;  // NOP
    inst_mem[1] = 32'h00100093;  // ADDI x1, x0, 1
    inst_mem[2] = 32'h00200113;  // ADDI x2, x0, 2

    // Initialize data memory to zero
    for (int i = 0; i < DMEM_SIZE / 4; i++) begin
      data_mem[i] = 32'h00000000;
    end

    // Initialize first data location for testing
    data_mem[0] = 32'h89ABCDEF;
  end

  // Instruction fetch logic - simplified for direct BRAM access
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      imem_read_data <= 32'h00000013;  // NOP
      imem_access_count <= '0;
    end else begin
      // Handle read request - BRAM is always ready in 1 cycle
      if (imem_read) begin
        imem_access_count <= imem_access_count + 1;

        // Check if address is in range (word-aligned addresses only)
        if (imem_addr[31:15] == 17'h0 && imem_addr[1:0] == 2'b00) begin
          logic [IMEM_ADDR_WIDTH-1:0] word_addr = imem_addr[IMEM_ADDR_WIDTH+1:2];

          if (32'(word_addr) < (IMEM_SIZE / 4)) begin
            // Direct BRAM access - single cycle
            imem_read_data <= inst_mem[word_addr];
          end else begin
            // Out of range
            imem_read_data <= 32'h00000013;  // NOP for out of range
          end
        end else begin
          // Out of range or misaligned
          imem_read_data <= 32'h00000013;  // NOP for out of range
        end
      end
    end
  end

  // BRAM is always ready for instruction access
  assign imem_ready = 1'b1;

  // Data memory access logic - simplified for direct BRAM access
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      dmem_read_data <= '0;
      dmem_access_count <= '0;
    end else begin
      // Handle memory operations
      if (dmem_write || dmem_read) begin
        dmem_access_count <= dmem_access_count + 1;

        // Check if address is in data memory range (word-aligned addresses only)
        if (dmem_addr[31:15] == 17'h0 && dmem_addr[1:0] == 2'b00) begin
          logic [DMEM_ADDR_WIDTH-1:0] word_addr = dmem_addr[DMEM_ADDR_WIDTH+1:2];

          if (32'(word_addr) < (DMEM_SIZE / 4)) begin
            if (dmem_write) begin
              // Handle byte enables for write
              logic [31:0] current_data = data_mem[word_addr];
              logic [31:0] new_data = current_data;

              if (dmem_byte_enable[0]) new_data[7:0] = dmem_write_data[7:0];
              if (dmem_byte_enable[1]) new_data[15:8] = dmem_write_data[15:8];
              if (dmem_byte_enable[2]) new_data[23:16] = dmem_write_data[23:16];
              if (dmem_byte_enable[3]) new_data[31:24] = dmem_write_data[31:24];

              data_mem[word_addr] <= new_data;
              dmem_read_data <= '0;
            end else begin // dmem_read
              // Direct BRAM access - single cycle
              dmem_read_data <= data_mem[word_addr];
            end
          end else begin
            // Out of range access
            dmem_read_data <= '0;
          end
        end else begin
          // Out of range or misaligned
          dmem_read_data <= '0;
        end
      end
    end
  end

  // BRAM is always ready for data access
  assign dmem_ready = 1'b1;

endmodule