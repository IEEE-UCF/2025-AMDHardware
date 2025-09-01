module gpu_result_buffer #(
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
    input  logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] i_result_data,
    input  logic [TAG_WIDTH-1:0]             i_result_tag,
    input  logic [3:0]                       i_dest_reg,
    input  logic                              i_is_vector,
    input  logic                              i_write_mem,
    input  logic [ADDR_WIDTH-1:0]            i_mem_addr,
    output logic                              o_buffer_full,
    
    // Output to writeback stage
    input  logic                              i_wb_req,
    output logic                              o_wb_valid,
    output logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] o_wb_data,
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

    // Result entry structure
    logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] buffer_data [BUFFER_DEPTH-1:0];
    logic [TAG_WIDTH-1:0]                buffer_tag [BUFFER_DEPTH-1:0];
    logic [3:0]                          buffer_dest_reg [BUFFER_DEPTH-1:0];
    logic                                 buffer_is_vector [BUFFER_DEPTH-1:0];
    logic                                 buffer_write_mem [BUFFER_DEPTH-1:0];
    logic [ADDR_WIDTH-1:0]               buffer_mem_addr [BUFFER_DEPTH-1:0];
    logic                                 buffer_valid [BUFFER_DEPTH-1:0];
    logic                                 buffer_ready [BUFFER_DEPTH-1:0];
    
    result_entry_t buffer[BUFFER_DEPTH];
    
    // Buffer pointers and control
    logic [$clog2(BUFFER_DEPTH)-1:0] wr_ptr, rd_ptr;
    logic [$clog2(BUFFER_DEPTH):0]   count;
    
    // Scoreboard for tracking in-flight operations
    logic [15:0] reg_scoreboard;  // Track which registers have pending writes
    logic [TAG_WIDTH-1:0] tag_scoreboard[16];  // Track tags for each register
    
    // Write logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            count <= '0;
            o_buffer_overflow <= 1'b0;
            reg_scoreboard <= '0;
            
            for (int i = 0; i < BUFFER_DEPTH; i++) begin
                buffer[i].valid <= 1'b0;
                buffer[i].ready <= 1'b0;
            end
            
            for (int i = 0; i < 16; i++) begin
                tag_scoreboard[i] <= '0;
            end
        end else begin
            // Handle incoming results
            if (i_result_valid && !o_buffer_full) begin
                buffer[wr_ptr].data      <= i_result_data;
                buffer[wr_ptr].tag       <= i_result_tag;
                buffer[wr_ptr].dest_reg  <= i_dest_reg;
                buffer[wr_ptr].is_vector <= i_is_vector;
                buffer[wr_ptr].write_mem <= i_write_mem;
                buffer[wr_ptr].mem_addr  <= i_mem_addr;
                buffer[wr_ptr].valid     <= 1'b1;
                buffer[wr_ptr].ready     <= 1'b1;
                
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
                buffer[rd_ptr].valid <= 1'b0;
                rd_ptr <= rd_ptr + 1'b1;
                
                // Clear scoreboard entry
                if (!buffer[rd_ptr].write_mem) begin
                    reg_scoreboard[buffer[rd_ptr].dest_reg] <= 1'b0;
                end
                
                if (!i_result_valid || o_buffer_full) begin
                    count <= count - 1'b1;
                end
            end else if (i_wb_req && o_buffer_empty) begin
                o_buffer_underflow <= 1'b1;
            end
        end
    end
    
    // Handle simultaneous read and write
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset handled above
        end else begin
            if (i_result_valid && !o_buffer_full && i_wb_req && !o_buffer_empty) begin
                // Count stays the same, both operations succeed
            end
        end
    end
    
    // Output assignments
    assign o_buffer_full  = (count == BUFFER_DEPTH);
    assign o_buffer_empty = (count == 0);
    assign o_buffer_count = count[3:0];
    
    // Writeback output
    always_comb begin
        if (!o_buffer_empty && buffer[rd_ptr].valid && buffer[rd_ptr].ready) begin
            o_wb_valid     = 1'b1;
            o_wb_data      = buffer[rd_ptr].data;
            o_wb_tag       = buffer[rd_ptr].tag;
            o_wb_dest_reg  = buffer[rd_ptr].dest_reg;
            o_wb_is_vector = buffer[rd_ptr].is_vector;
            o_wb_write_mem = buffer[rd_ptr].write_mem;
            o_wb_mem_addr  = buffer[rd_ptr].mem_addr;
        end else begin
            o_wb_valid     = 1'b0;
            o_wb_data      = '0;
            o_wb_tag       = '0;
            o_wb_dest_reg  = '0;
            o_wb_is_vector = 1'b0;
            o_wb_write_mem = 1'b0;
            o_wb_mem_addr  = '0;
        end
    end
    
    // Hazard detection for out-of-order completion
    logic hazard_detected;
    logic [3:0] hazard_reg;
    
    always_comb begin
        hazard_detected = 1'b0;
        hazard_reg = 4'b0;
        
        // Check if any result in buffer has a dependency
        for (int i = 0; i < BUFFER_DEPTH; i++) begin
            if (buffer[i].valid && !buffer[i].write_mem) begin
                // Check if this result depends on a pending write
                if (reg_scoreboard[buffer[i].dest_reg] && 
                    tag_scoreboard[buffer[i].dest_reg] != buffer[i].tag) begin
                    hazard_detected = 1'b1;
                    hazard_reg = buffer[i].dest_reg;
                end
            end
        end
    end
    
    // Priority encoder for result ordering
    logic [BUFFER_DEPTH-1:0] ready_mask;
    logic [$clog2(BUFFER_DEPTH)-1:0] next_ready_idx;
    
    always_comb begin
        ready_mask = '0;
        next_ready_idx = rd_ptr;
        
        // Mark entries as ready based on dependencies
        for (int i = 0; i < BUFFER_DEPTH; i++) begin
            if (buffer[i].valid) begin
                if (buffer[i].write_mem) begin
                    // Memory writes can proceed immediately
                    ready_mask[i] = 1'b1;
                end else if (!reg_scoreboard[buffer[i].dest_reg] || 
                           tag_scoreboard[buffer[i].dest_reg] == buffer[i].tag) begin
                    // Register writes can proceed if no dependency
                    ready_mask[i] = 1'b1;
                end
            end
        end
        
        // Find next ready entry
        for (int i = 0; i < BUFFER_DEPTH; i++) begin
            if (ready_mask[(rd_ptr + i) % BUFFER_DEPTH]) begin
                next_ready_idx = (rd_ptr + i) % BUFFER_DEPTH;
                break;
            end
        end
    end
    
    // Performance counters
    logic [31:0] total_cycles;
    logic [31:0] stall_cycles;
    logic [31:0] results_processed;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            total_cycles <= '0;
            stall_cycles <= '0;
            results_processed <= '0;
        end else begin
            total_cycles <= total_cycles + 1'b1;
            
            if (o_buffer_full && i_result_valid) begin
                stall_cycles <= stall_cycles + 1'b1;
            end
            
            if (i_wb_req && o_wb_valid) begin
                results_processed <= results_processed + 1'b1;
            end
        end
    end
    
    // Debug output
    `ifdef DEBUG
    always_ff @(posedge clk) begin
        if (i_result_valid && !o_buffer_full) begin
            $display("[RESULT_BUFFER] Store: tag=%02h, dest=r%d, vec=%b, mem=%b", 
                     i_result_tag, i_dest_reg, i_is_vector, i_write_mem);
        end
        if (i_wb_req && o_wb_valid) begin
            $display("[RESULT_BUFFER] Writeback: tag=%02h, dest=r%d, data[0]=%08h", 
                     o_wb_tag, o_wb_dest_reg, o_wb_data[0]);
        end
        if (hazard_detected) begin
            $display("[RESULT_BUFFER] Hazard detected on register r%d", hazard_reg);
        end
    end
    `endif

endmodule