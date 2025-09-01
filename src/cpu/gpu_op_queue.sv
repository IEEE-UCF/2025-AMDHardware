module gpu_op_queue #(
    parameter int QUEUE_DEPTH = 32,
    parameter int INSTR_WIDTH = 80,  // Based on instruction format from docs
    parameter int ADDR_WIDTH = 32,
    parameter int DATA_WIDTH = 32
) (
    input  logic                     clk,
    input  logic                     rst_n,
    
    // CPU interface for enqueuing operations
    input  logic                     i_enqueue_valid,
    input  logic [INSTR_WIDTH-1:0]  i_instruction,
    input  logic [ADDR_WIDTH-1:0]   i_src_addr,
    input  logic [ADDR_WIDTH-1:0]   i_dst_addr,
    output logic                     o_queue_full,
    output logic                     o_queue_empty,
    output logic [4:0]               o_queue_count,
    
    // GPU fetch interface
    input  logic                     i_dequeue_req,
    output logic                     o_dequeue_valid,
    output logic [INSTR_WIDTH-1:0]  o_instruction,
    output logic [ADDR_WIDTH-1:0]   o_src_addr,
    output logic [ADDR_WIDTH-1:0]   o_dst_addr,
    
    // Status signals
    output logic                     o_queue_nearly_full,
    output logic                     o_queue_underrun,
    output logic                     o_queue_overflow
);

    // Internal storage
    typedef struct packed {
        logic [INSTR_WIDTH-1:0] instruction;
        logic [ADDR_WIDTH-1:0]  src_addr;
        logic [ADDR_WIDTH-1:0]  dst_addr;
        logic                    valid;
    } queue_entry_t;
    
    queue_entry_t queue[QUEUE_DEPTH];
    
    // Queue pointers
    logic [$clog2(QUEUE_DEPTH)-1:0] wr_ptr, rd_ptr;
    logic [$clog2(QUEUE_DEPTH):0]   count;
    
    // Decode instruction fields based on GPU ISA
    logic       scalar_vector_mode;
    logic       write_mem;
    logic       read_mem;
    logic       multi_value;
    logic [7:0] opcode;
    logic [3:0] dest_reg;
    logic [63:0] data_field;
    
    // Extract fields from instruction for validation
    always_comb begin
        scalar_vector_mode = i_instruction[0];
        write_mem         = i_instruction[1];
        read_mem          = i_instruction[2];
        multi_value       = i_instruction[3];
        opcode            = i_instruction[11:4];
        dest_reg          = i_instruction[15:12];
        data_field        = i_instruction[79:16];
    end
    
    // Queue management
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count  <= '0;
            o_queue_underrun <= 1'b0;
            o_queue_overflow <= 1'b0;
            
            for (int i = 0; i < QUEUE_DEPTH; i++) begin
                queue[i].valid <= 1'b0;
            end
        end else begin
            // Enqueue operation
            if (i_enqueue_valid && !o_queue_full) begin
                queue[wr_ptr].instruction <= i_instruction;
                queue[wr_ptr].src_addr    <= i_src_addr;
                queue[wr_ptr].dst_addr    <= i_dst_addr;
                queue[wr_ptr].valid       <= 1'b1;
                
                wr_ptr <= wr_ptr + 1'b1;
                
                if (!i_dequeue_req || o_queue_empty) begin
                    count <= count + 1'b1;
                end
            end else if (i_enqueue_valid && o_queue_full) begin
                o_queue_overflow <= 1'b1;
            end
            
            // Dequeue operation
            if (i_dequeue_req && !o_queue_empty) begin
                queue[rd_ptr].valid <= 1'b0;
                rd_ptr <= rd_ptr + 1'b1;
                
                if (!i_enqueue_valid || o_queue_full) begin
                    count <= count - 1'b1;
                end
            end else if (i_dequeue_req && o_queue_empty) begin
                o_queue_underrun <= 1'b1;
            end
            
            // Handle simultaneous enqueue and dequeue
            if (i_enqueue_valid && !o_queue_full && i_dequeue_req && !o_queue_empty) begin
                // Count stays the same
            end
        end
    end
    
    // Output assignments
    assign o_queue_full  = (count == QUEUE_DEPTH);
    assign o_queue_empty = (count == 0);
    assign o_queue_count = count[4:0];
    assign o_queue_nearly_full = (count >= (QUEUE_DEPTH - 4));
    
    // Dequeue output
    always_comb begin
        if (!o_queue_empty && queue[rd_ptr].valid) begin
            o_dequeue_valid = 1'b1;
            o_instruction   = queue[rd_ptr].instruction;
            o_src_addr      = queue[rd_ptr].src_addr;
            o_dst_addr      = queue[rd_ptr].dst_addr;
        end else begin
            o_dequeue_valid = 1'b0;
            o_instruction   = '0;
            o_src_addr      = '0;
            o_dst_addr      = '0;
        end
    end
    
    // Priority handling for different operation types
    logic [2:0] priority_level;
    
    always_comb begin
        // Assign priority based on instruction type
        if (write_mem) begin
            priority_level = 3'b111; // Highest priority for memory writes
        end else if (read_mem) begin
            priority_level = 3'b110; // High priority for memory reads
        end else if (scalar_vector_mode) begin
            priority_level = 3'b100; // Medium priority for vector ops
        end else begin
            priority_level = 3'b010; // Lower priority for scalar ops
        end
    end
    
    // Debug signals
    `ifdef DEBUG
    always_ff @(posedge clk) begin
        if (i_enqueue_valid && !o_queue_full) begin
            $display("[GPU_OP_QUEUE] Enqueue: opcode=%02h, dest=%01h, src=%08h, dst=%08h", 
                     opcode, dest_reg, i_src_addr, i_dst_addr);
        end
        if (i_dequeue_req && !o_queue_empty) begin
            $display("[GPU_OP_QUEUE] Dequeue: opcode=%02h, count=%d", 
                     queue[rd_ptr].instruction[11:4], count);
        end
    end
    `endif

endmodule