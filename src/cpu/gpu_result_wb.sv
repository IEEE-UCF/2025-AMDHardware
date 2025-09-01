// GPU Result Writeback Module
// Simplified version compatible with Icarus Verilog
module gpu_result_wb #(
    parameter int BUFFER_DEPTH = 16,
    parameter int DATA_WIDTH = 32,
    parameter int VEC_SIZE = 4,
    parameter int TAG_WIDTH = 8,
    parameter int ADDR_WIDTH = 32
) (
    input  logic                              clk,
    input  logic                              rst_n,
    
    // Input from GPU execution units
    input  logic                              i_result_valid,
    input  logic [DATA_WIDTH-1:0]            i_result_data [VEC_SIZE-1:0],
    input  logic [TAG_WIDTH-1:0]             i_result_tag,
    input  logic [3:0]                       i_dest_reg,
    input  logic                              i_is_vector,
    input  logic                              i_write_mem,
    input  logic [ADDR_WIDTH-1:0]            i_mem_addr,
    output logic                              o_buffer_full,
    
    // Output to writeback stage
    input  logic                              i_wb_req,
    output logic                              o_wb_valid,
    output logic [DATA_WIDTH-1:0]            o_wb_data [VEC_SIZE-1:0],
    output logic [TAG_WIDTH-1:0]             o_wb_tag,
    output logic [3:0]                       o_wb_dest_reg,
    output logic                              o_wb_is_vector,
    output logic                              o_wb_write_mem,
    output logic [ADDR_WIDTH-1:0]            o_wb_mem_addr,
    output logic                              o_buffer_empty,
    
    // Status and debug
    output logic [3:0]                       o_buffer_count,
    output logic                              o_buffer_overflow,
    output logic                              o_buffer_underflow
);

    // Simplified buffer entry structure for Icarus compatibility
    logic [DATA_WIDTH-1:0]                   buffer_data [BUFFER_DEPTH-1:0][VEC_SIZE-1:0];
    logic [TAG_WIDTH-1:0]                    buffer_tag [BUFFER_DEPTH-1:0];
    logic [3:0]                              buffer_dest_reg [BUFFER_DEPTH-1:0];
    logic                                    buffer_is_vector [BUFFER_DEPTH-1:0];
    logic                                    buffer_write_mem [BUFFER_DEPTH-1:0];
    logic [ADDR_WIDTH-1:0]                   buffer_mem_addr [BUFFER_DEPTH-1:0];
    logic                                    buffer_valid [BUFFER_DEPTH-1:0];
    logic                                    buffer_ready [BUFFER_DEPTH-1:0];
    
    // Buffer pointers and control
    logic [$clog2(BUFFER_DEPTH)-1:0] wr_ptr, rd_ptr;
    logic [$clog2(BUFFER_DEPTH):0]   count;
    
    // Scoreboard for tracking in-flight operations
    logic [15:0] reg_scoreboard;  // Track which registers have pending writes
    logic [TAG_WIDTH-1:0] tag_scoreboard [15:0];  // Track tags for each register
    
    integer i, j;
    
    // Write logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            count <= '0;
            o_buffer_overflow <= 1'b0;
            reg_scoreboard <= '0;
            
            for (i = 0; i < BUFFER_DEPTH; i = i + 1) begin
                buffer_valid[i] <= 1'b0;
                buffer_ready[i] <= 1'b0;
                for (j = 0; j < VEC_SIZE; j = j + 1) begin
                    buffer_data[i][j] <= '0;
                end
            end
            
            for (i = 0; i < 16; i = i + 1) begin
                tag_scoreboard[i] <= '0;
            end
        end else begin
            // Handle incoming results
            if (i_result_valid && !o_buffer_full) begin
                for (j = 0; j < VEC_SIZE; j = j + 1) begin
                    buffer_data[wr_ptr][j] <= i_result_data[j];
                end
                buffer_tag[wr_ptr]       <= i_result_tag;
                buffer_dest_reg[wr_ptr]  <= i_dest_reg;
                buffer_is_vector[wr_ptr] <= i_is_vector;
                buffer_write_mem[wr_ptr] <= i_write_mem;
                buffer_mem_addr[wr_ptr]  <= i_mem_addr;
                buffer_valid[wr_ptr]     <= 1'b1;
                buffer_ready[wr_ptr]     <= 1'b1;
                
                wr_ptr <= wr_ptr + 1'b1;
                
                // Update scoreboard
                if (!i_write_mem) begin
                    reg_scoreboard[i_dest_reg] <= 1'b1;
                    tag_scoreboard[i_dest_reg] <= i_result_tag;
                end
                
                if (!i_wb_req || o_buffer_empty) begin
                    count <= count + 1'b1;
                end
            end else if (i_result_valid && o_buffer_full) begin
                o_buffer_overflow <= 1'b1;
            end
        end
    end
    
    // Read logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_ptr <= '0;
            o_buffer_underflow <= 1'b0;
        end else begin
            if (i_wb_req && !o_buffer_empty) begin
                buffer_valid[rd_ptr] <= 1'b0;
                rd_ptr <= rd_ptr + 1'b1;
                
                // Clear scoreboard entry
                if (!buffer_write_mem[rd_ptr]) begin
                    reg_scoreboard[buffer_dest_reg[rd_ptr]] <= 1'b0;
                end
                
                if (!i_result_valid || o_buffer_full) begin
                    count <= count - 1'b1;
                end
            end else if (i_wb_req && o_buffer_empty) begin
                o_buffer_underflow <= 1'b1;
            end
        end
    end
    
    // Output assignments
    assign o_buffer_full  = (count == BUFFER_DEPTH);
    assign o_buffer_empty = (count == 0);
    assign o_buffer_count = count[3:0];
    
    // Writeback output
    always_comb begin
        if (!o_buffer_empty && buffer_valid[rd_ptr] && buffer_ready[rd_ptr]) begin
            o_wb_valid     = 1'b1;
            for (j = 0; j < VEC_SIZE; j = j + 1) begin
                o_wb_data[j] = buffer_data[rd_ptr][j];
            end
            o_wb_tag       = buffer_tag[rd_ptr];
            o_wb_dest_reg  = buffer_dest_reg[rd_ptr];
            o_wb_is_vector = buffer_is_vector[rd_ptr];
            o_wb_write_mem = buffer_write_mem[rd_ptr];
            o_wb_mem_addr  = buffer_mem_addr[rd_ptr];
        end else begin
            o_wb_valid     = 1'b0;
            for (j = 0; j < VEC_SIZE; j = j + 1) begin
                o_wb_data[j] = '0;
            end
            o_wb_tag       = '0;
            o_wb_dest_reg  = '0;
            o_wb_is_vector = 1'b0;
            o_wb_write_mem = 1'b0;
            o_wb_mem_addr  = '0;
        end
    end

endmodule
