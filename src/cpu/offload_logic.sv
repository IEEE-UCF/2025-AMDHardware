module offload_manager #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter DATA_WIDTH = 32,  // Changed from 64 to 32
    parameter INST_WIDTH = 32,
    parameter REG_ADDR_WIDTH = 5,
    parameter CP_NUM = 4,
    parameter TABLE_ENTRIES = 16,
    parameter TAG_WIDTH = 4,
    parameter STALL_TIMEOUT = 1024
)(
    input  logic                              clk,
    input  logic                              rst_n,
    
    // CPU Pipeline Interface
    input  logic                              if_valid,
    input  logic [ADDR_WIDTH-1:0]             if_pc,
    input  logic                              id_valid,
    input  logic [INST_WIDTH-1:0]             id_instruction,
    input  logic [REG_ADDR_WIDTH-1:0]         id_rs1,
    input  logic [REG_ADDR_WIDTH-1:0]         id_rs2,
    input  logic [REG_ADDR_WIDTH-1:0]         id_rd,
    input  logic [DATA_WIDTH-1:0]             rs1_data,
    input  logic [DATA_WIDTH-1:0]             rs2_data,
    input  logic                              ex_valid,
    input  logic [REG_ADDR_WIDTH-1:0]         ex_rd,
    input  logic                              ex_reg_write,
    input  logic                              mm_valid,
    input  logic [REG_ADDR_WIDTH-1:0]         mm_rd,
    input  logic                              mm_reg_write,
    input  logic                              wb_valid,
    input  logic [REG_ADDR_WIDTH-1:0]         wb_rd,
    input  logic                              wb_reg_write,
    
    // Coprocessor Interface
    output logic                              cp_valid,
    output logic [INST_WIDTH-1:0]             cp_instruction,
    output logic [DATA_WIDTH-1:0]             cp_data_in,
    output logic [1:0]                        cp_select,
    input  logic [DATA_WIDTH-1:0]             cp_data_out,
    input  logic                              cp_ready,
    input  logic                              cp_exception,
    input  logic [CP_NUM-1:0]                 cp_busy,
    input  logic [CP_NUM-1:0]                 cp_available,
    input  logic [CP_NUM-1:0]                 cp_stall_request,
    input  logic [CP_NUM-1:0]                 cp_result_valid,
    input  logic [REG_ADDR_WIDTH-1:0]         cp_reg_addr [CP_NUM-1:0],
    input  logic [CP_NUM-1:0]                 cp_reg_write,
    
    // Memory Interface
    input  logic                              mem_busy,
    input  logic                              mem_conflict,
    
    // Pipeline Control Outputs
    output logic                              if_stall,
    output logic                              id_stall,
    output logic                              ex_stall,
    output logic                              mm_stall,
    output logic                              wb_stall,
    output logic                              global_stall,
    
    // Result Interface
    output logic                              result_valid,
    output logic [REG_ADDR_WIDTH-1:0]         result_reg_addr,
    output logic [DATA_WIDTH-1:0]             result_data,
    output logic                              result_exception,
    output logic [3:0]                        result_exception_code,
    
    // Control Interface
    input  logic                              flush_all,
    input  logic                              flush_cp,
    input  logic [1:0]                        flush_cp_select,
    
    // Status/Debug Interface
    output logic                              offload_detected,
    output logic                              offload_ready,
    output logic                              offload_timeout,
    output logic [3:0]                        stall_reason,
    output logic [$clog2(TABLE_ENTRIES):0]    pending_operations,
    output logic [31:0]                       total_offloads,
    output logic [31:0]                       completed_offloads,
    output logic [31:0]                       exception_count
);

    // Internal signals
    logic                              classify_valid;
    logic [1:0]                        classify_cp_select;
    logic                              classify_offloadable;
    logic                              classify_ready;
    logic                              alloc_request;
    logic [$clog2(TABLE_ENTRIES)-1:0]  alloc_entry_id;
    logic                              alloc_success;
    logic                              alloc_full;
    logic                              complete_valid;
    logic [$clog2(TABLE_ENTRIES)-1:0]  complete_entry_id;
    logic [DATA_WIDTH-1:0]             complete_result;
    logic                              complete_exception;
    logic [3:0]                        complete_exception_code;
    logic                              offload_request;
    logic                              offload_stall;
    logic [TAG_WIDTH-1:0]              instruction_tag;
    logic dispatcher_detected;
    logic [1:0] dispatcher_cp_select;
    logic dispatcher_stall_request;
    logic [TAG_WIDTH-1:0] tag_counter;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tag_counter <= '0;
        end else if (alloc_success) begin
            tag_counter <= tag_counter + 1;
        end
    end
    
    logic [6:0] opcode;
    logic [2:0] funct3;
    
    assign opcode = id_instruction[6:0];
    assign funct3 = id_instruction[14:12];
    
    always_comb begin
        classify_valid = id_valid && !global_stall;
        dispatcher_detected = 1'b0;
        dispatcher_cp_select = 2'b00;
        
        if (classify_valid) begin
            case (opcode)
                7'b1110011: begin
                    dispatcher_detected = 1'b1;
                    dispatcher_cp_select = 2'b00;
                end
                7'b1010011: begin
                    dispatcher_detected = 1'b1;
                    dispatcher_cp_select = 2'b01;
                end
                7'b0001011: begin
                    dispatcher_detected = 1'b1;
                    dispatcher_cp_select = 2'b10;
                end
                7'b0101011: begin
                    if (CP_NUM > 3) begin
                        dispatcher_detected = 1'b1;
                        dispatcher_cp_select = 2'b11;
                    end
                end
                default: begin
                    dispatcher_detected = 1'b0;
                    dispatcher_cp_select = 2'b00;
                end
            endcase
        end
    end
    
    assign offload_request = dispatcher_detected && classify_offloadable && classify_ready && !alloc_full;
    assign alloc_request = offload_request && !offload_stall;
    assign cp_valid = alloc_success;
    assign cp_instruction = id_instruction;
    assign cp_data_in = rs1_data;
    assign cp_select = classify_cp_select;
    assign dispatcher_stall_request = dispatcher_detected && (!classify_ready || alloc_full || offload_stall);
    
    logic [$clog2(TABLE_ENTRIES)-1:0] completion_entry_counter;
    logic [CP_NUM-1:0] cp_result_valid_prev;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            completion_entry_counter <= '0;
            cp_result_valid_prev <= '0;
        end else begin
            cp_result_valid_prev <= cp_result_valid;
            for (int i = 0; i < CP_NUM; i++) begin
                if (cp_result_valid[i] && !cp_result_valid_prev[i]) begin
                    completion_entry_counter <= completion_entry_counter + 1;
                end
            end
        end
    end
    
    assign complete_valid = |cp_result_valid;
    assign complete_entry_id = completion_entry_counter;
    assign complete_result = cp_data_out;
    assign complete_exception = cp_exception;
    assign complete_exception_code = 4'h0;
    assign result_valid = complete_valid;
    assign result_reg_addr = id_rd;
    assign result_data = complete_result;
    assign result_exception = complete_exception;
    assign result_exception_code = complete_exception_code;
    assign offload_detected = dispatcher_detected;
    assign offload_ready = classify_ready && !alloc_full && !offload_stall;
    
    // Instantiate destination table
    offload_destination_table #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .INST_WIDTH(INST_WIDTH),
        .TABLE_ENTRIES(TABLE_ENTRIES),
        .CP_NUM(CP_NUM),
        .TAG_WIDTH(TAG_WIDTH)
    ) dest_table (
        .clk(clk),
        .rst_n(rst_n),
        .classify_valid(classify_valid),
        .classify_instruction(id_instruction),
        .classify_pc(if_pc),
        .classify_tag(instruction_tag),
        .classify_cp_select(classify_cp_select),
        .classify_offloadable(classify_offloadable),
        .classify_ready(classify_ready),
        .alloc_request(alloc_request),
        .alloc_instruction(id_instruction),
        .alloc_pc(if_pc),
        .alloc_cp_select(classify_cp_select),
        .alloc_tag(instruction_tag),
        .alloc_rd(id_rd),
        .alloc_entry_id(alloc_entry_id),
        .alloc_success(alloc_success),
        .alloc_full(alloc_full),
        .complete_valid(complete_valid),
        .complete_entry_id(complete_entry_id),
        .complete_result(complete_result),
        .complete_exception(complete_exception),
        .complete_exception_code(complete_exception_code),
        .query_entry_id('0),
        .query_valid(),
        .query_completed(),
        .query_exception(),
        .query_pc(),
        .query_instruction(),
        .query_cp_select(),
        .query_result(),
        .cp_busy(cp_busy),
        .cp_available(cp_available),
        .cp_exception(cp_exception),
        .entries_used(),
        .entries_pending(pending_operations),
        .total_offloads(total_offloads),
        .completed_offloads(completed_offloads),
        .exception_count(exception_count),
        .flush_all(flush_all),
        .flush_cp(flush_cp),
        .flush_cp_select(flush_cp_select)
    );
    
    // Instantiate stall handler
    offload_stall_handler #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .INST_WIDTH(INST_WIDTH),
        .REG_ADDR_WIDTH(REG_ADDR_WIDTH),
        .CP_NUM(CP_NUM),
        .STALL_TIMEOUT(STALL_TIMEOUT)
    ) stall_handler (
        .clk(clk),
        .rst_n(rst_n),
        .if_valid(if_valid),
        .if_pc(if_pc),
        .id_valid(id_valid),
        .id_instruction(id_instruction),
        .id_rs1(id_rs1),
        .id_rs2(id_rs2),
        .id_rd(id_rd),
        .ex_valid(ex_valid),
        .ex_rd(ex_rd),
        .ex_reg_write(ex_reg_write),
        .mm_valid(mm_valid),
        .mm_rd(mm_rd),
        .mm_reg_write(mm_reg_write),
        .wb_valid(wb_valid),
        .wb_rd(wb_rd),
        .wb_reg_write(wb_reg_write),
        .cp_busy(cp_busy),
        .cp_ready(cp_available),
        .cp_exception(cp_exception),
        .cp_stall_request(cp_stall_request),
        .cp_result_valid(cp_result_valid),
        .cp_reg_addr(cp_reg_addr),
        .cp_reg_write(cp_reg_write),
        .offload_request(offload_request),
        .offload_cp_select(classify_cp_select),
        .offload_instruction(id_instruction),
        .offload_rs1(id_rs1),
        .offload_rs2(id_rs2),
        .offload_rd(id_rd),
        .mem_busy(mem_busy),
        .mem_conflict(mem_conflict),
        .if_stall(if_stall),
        .id_stall(id_stall),
        .ex_stall(ex_stall),
        .mm_stall(mm_stall),
        .wb_stall(wb_stall),
        .global_stall(global_stall),
        .offload_stall(offload_stall),
        .offload_ready(),
        .offload_timeout(offload_timeout),
        .stall_reason(stall_reason),
        .stall_counter(),
        .cp_dependency_stall()
    );
endmodule

// offload_destination_table.sv - Fixed for 32-bit
module offload_destination_table #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter DATA_WIDTH = 32,  // Changed from 64 to 32
    parameter INST_WIDTH = 32,
    parameter TABLE_ENTRIES = 16,
    parameter CP_NUM = 4,
    parameter TAG_WIDTH = 4
)(
    input  logic                              clk,
    input  logic                              rst_n,
    input  logic                              classify_valid,
    input  logic [INST_WIDTH-1:0]             classify_instruction,
    input  logic [ADDR_WIDTH-1:0]             classify_pc,
    input  logic [TAG_WIDTH-1:0]              classify_tag,
    output logic [1:0]                        classify_cp_select,
    output logic                              classify_offloadable,
    output logic                              classify_ready,
    input  logic                              alloc_request,
    input  logic [INST_WIDTH-1:0]             alloc_instruction,
    input  logic [ADDR_WIDTH-1:0]             alloc_pc,
    input  logic [1:0]                        alloc_cp_select,
    input  logic [TAG_WIDTH-1:0]              alloc_tag,
    input  logic [4:0]                        alloc_rd,
    output logic [$clog2(TABLE_ENTRIES)-1:0]  alloc_entry_id,
    output logic                              alloc_success,
    output logic                              alloc_full,
    input  logic                              complete_valid,
    input  logic [$clog2(TABLE_ENTRIES)-1:0]  complete_entry_id,
    input  logic [DATA_WIDTH-1:0]             complete_result,
    input  logic                              complete_exception,
    input  logic [3:0]                        complete_exception_code,
    input  logic [$clog2(TABLE_ENTRIES)-1:0]  query_entry_id,
    output logic                              query_valid,
    output logic                              query_completed,
    output logic                              query_exception,
    output logic [ADDR_WIDTH-1:0]             query_pc,
    output logic [INST_WIDTH-1:0]             query_instruction,
    output logic [1:0]                        query_cp_select,
    output logic [DATA_WIDTH-1:0]             query_result,
    input  logic [CP_NUM-1:0]                 cp_busy,
    input  logic [CP_NUM-1:0]                 cp_available,
    input  logic [CP_NUM-1:0]                 cp_exception,
    output logic [$clog2(TABLE_ENTRIES):0]    entries_used,
    output logic [$clog2(TABLE_ENTRIES):0]    entries_pending,
    output logic [31:0]                       total_offloads,
    output logic [31:0]                       completed_offloads,
    output logic [31:0]                       exception_count,
    input  logic                              flush_all,
    input  logic                              flush_cp,
    input  logic [1:0]                        flush_cp_select
);

    // Table entry structure - all 32-bit
    typedef struct packed {
        logic                              valid;
        logic                              completed;
        logic                              exception_flag;
        logic [INST_WIDTH-1:0]             instruction;
        logic [ADDR_WIDTH-1:0]             pc;
        logic [1:0]                        cp_select;
        logic [TAG_WIDTH-1:0]              tag;
        logic [4:0]                        rd;
        logic [DATA_WIDTH-1:0]             result;
        logic [3:0]                        exception_code;
        logic [31:0]                       timestamp;
    } table_entry_t;
    
    table_entry_t dest_table [TABLE_ENTRIES-1:0];
    logic [TABLE_ENTRIES-1:0] entry_valid;
    logic [TABLE_ENTRIES-1:0] entry_completed;
    logic [$clog2(TABLE_ENTRIES)-1:0] next_free_entry;
    logic [$clog2(TABLE_ENTRIES)-1:0] alloc_ptr;
    logic table_full;
    logic [31:0] stat_total_offloads;
    logic [31:0] stat_completed_offloads;
    logic [31:0] stat_exception_count;
    logic [31:0] cycle_counter;
    logic [6:0] class_opcode;
    logic [2:0] class_funct3;
    logic [6:0] class_funct7;
    
    assign class_opcode = classify_instruction[6:0];
    assign class_funct3 = classify_instruction[14:12];
    assign class_funct7 = classify_instruction[31:25];

    always_comb begin
        classify_cp_select = 2'b00;
        classify_offloadable = 1'b0;
        classify_ready = 1'b1;
        
        if (classify_valid) begin
            case (class_opcode)
                7'b1110011: begin
                    classify_offloadable = 1'b1;
                    classify_cp_select = 2'b00;
                    classify_ready = cp_available[0];
                end
                7'b1010011: begin
                    classify_offloadable = 1'b1;
                    classify_cp_select = 2'b01;
                    classify_ready = cp_available[1];
                end
                7'b0001011: begin
                    classify_offloadable = 1'b1;
                    classify_cp_select = 2'b10;
                    classify_ready = cp_available[2];
                end
                7'b0101011: begin
                    if (CP_NUM > 3) begin
                        classify_offloadable = 1'b1;
                        classify_cp_select = 2'b11;
                        classify_ready = cp_available[3];
                    end
                end
                default: begin
                    classify_offloadable = 1'b0;
                    classify_cp_select = 2'b00;
                end
            endcase
        end
    end
    
    always_comb begin
        next_free_entry = '0;
        table_full = 1'b1;
        
        for (int i = 0; i < TABLE_ENTRIES; i++) begin
            if (!entry_valid[i] && table_full) begin
                next_free_entry = i[$clog2(TABLE_ENTRIES)-1:0];
                table_full = 1'b0;
            end
        end
    end
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < TABLE_ENTRIES; i++) begin
                dest_table[i].valid <= 1'b0;
                dest_table[i].completed <= 1'b0;
                dest_table[i].exception_flag <= 1'b0;
                dest_table[i].instruction <= '0;
                dest_table[i].pc <= '0;
                dest_table[i].cp_select <= '0;
                dest_table[i].tag <= '0;
                dest_table[i].rd <= '0;
                dest_table[i].result <= '0;
                dest_table[i].exception_code <= '0;
                dest_table[i].timestamp <= '0;
            end
            entry_valid <= '0;
            entry_completed <= '0;
            alloc_ptr <= '0;
            stat_total_offloads <= '0;
            stat_completed_offloads <= '0;
            stat_exception_count <= '0;
            cycle_counter <= '0;
        end else begin
            cycle_counter <= cycle_counter + 1;
            
            if (flush_all) begin
                entry_valid <= '0;
                entry_completed <= '0;
                for (int i = 0; i < TABLE_ENTRIES; i++) begin
                    dest_table[i].valid <= 1'b0;
                    dest_table[i].completed <= 1'b0;
                end
            end else if (flush_cp) begin
                for (int i = 0; i < TABLE_ENTRIES; i++) begin
                    if (dest_table[i].valid && dest_table[i].cp_select == flush_cp_select) begin
                        entry_valid[i] <= 1'b0;
                        entry_completed[i] <= 1'b0;
                        dest_table[i].valid <= 1'b0;
                        dest_table[i].completed <= 1'b0;
                    end
                end
            end
            
            if (alloc_request && !table_full) begin
                dest_table[next_free_entry].valid <= 1'b1;
                dest_table[next_free_entry].completed <= 1'b0;
                dest_table[next_free_entry].exception_flag <= 1'b0;
                dest_table[next_free_entry].instruction <= alloc_instruction;
                dest_table[next_free_entry].pc <= alloc_pc;
                dest_table[next_free_entry].cp_select <= alloc_cp_select;
                dest_table[next_free_entry].tag <= alloc_tag;
                dest_table[next_free_entry].rd <= alloc_rd;
                dest_table[next_free_entry].result <= '0;
                dest_table[next_free_entry].exception_code <= '0;
                dest_table[next_free_entry].timestamp <= cycle_counter;
                entry_valid[next_free_entry] <= 1'b1;
                entry_completed[next_free_entry] <= 1'b0;
                stat_total_offloads <= stat_total_offloads + 1;
            end
            
            if (complete_valid && complete_entry_id < TABLE_ENTRIES) begin
                if (entry_valid[complete_entry_id] && !entry_completed[complete_entry_id]) begin
                    dest_table[complete_entry_id].completed <= 1'b1;
                    dest_table[complete_entry_id].result <= complete_result;
                    dest_table[complete_entry_id].exception_flag <= complete_exception;
                    dest_table[complete_entry_id].exception_code <= complete_exception_code;
                    entry_completed[complete_entry_id] <= 1'b1;
                    stat_completed_offloads <= stat_completed_offloads + 1;
                    
                    if (complete_exception) begin
                        stat_exception_count <= stat_exception_count + 1;
                    end
                end
            end
        end
    end
    
    always_comb begin
        alloc_entry_id = next_free_entry;
        alloc_success = alloc_request && !table_full;
        alloc_full = table_full;
    end
    
    always_comb begin
        query_valid = 1'b0;
        query_completed = 1'b0;
        query_exception = 1'b0;
        query_pc = '0;
        query_instruction = '0;
        query_cp_select = '0;
        query_result = '0;
        
        if (query_entry_id < TABLE_ENTRIES && entry_valid[query_entry_id]) begin
            query_valid = 1'b1;
            query_completed = dest_table[query_entry_id].completed;
            query_exception = dest_table[query_entry_id].exception_flag;
            query_pc = dest_table[query_entry_id].pc;
            query_instruction = dest_table[query_entry_id].instruction;
            query_cp_select = dest_table[query_entry_id].cp_select;
            query_result = dest_table[query_entry_id].result;
        end
    end
    
    always_comb begin
        entries_used = '0;
        entries_pending = '0;
        
        for (int i = 0; i < TABLE_ENTRIES; i++) begin
            if (entry_valid[i]) begin
                entries_used = entries_used + 1;
                if (!entry_completed[i]) begin
                    entries_pending = entries_pending + 1;
                end
            end
        end
    end
    
    assign total_offloads = stat_total_offloads;
    assign completed_offloads = stat_completed_offloads;
    assign exception_count = stat_exception_count;
endmodule

// offload_stall_handler.sv - Fixed for 32-bit
module offload_stall_handler #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter DATA_WIDTH = 32,  // Changed from 64 to 32
    parameter INST_WIDTH = 32,
    parameter REG_ADDR_WIDTH = 5,
    parameter CP_NUM = 4,
    parameter STALL_TIMEOUT = 1024
)(
    input  logic                        clk,
    input  logic                        rst_n,
    input  logic                        if_valid,
    input  logic [ADDR_WIDTH-1:0]       if_pc,
    input  logic                        id_valid,
    input  logic [INST_WIDTH-1:0]       id_instruction,
    input  logic [REG_ADDR_WIDTH-1:0]   id_rs1,
    input  logic [REG_ADDR_WIDTH-1:0]   id_rs2,
    input  logic [REG_ADDR_WIDTH-1:0]   id_rd,
    input  logic                        ex_valid,
    input  logic [REG_ADDR_WIDTH-1:0]   ex_rd,
    input  logic                        ex_reg_write,
    input  logic                        mm_valid,
    input  logic [REG_ADDR_WIDTH-1:0]   mm_rd,
    input  logic                        mm_reg_write,
    input  logic                        wb_valid,
    input  logic [REG_ADDR_WIDTH-1:0]   wb_rd,
    input  logic                        wb_reg_write,
    input  logic [CP_NUM-1:0]           cp_busy,
    input  logic [CP_NUM-1:0]           cp_ready,
    input  logic [CP_NUM-1:0]           cp_exception,
    input  logic [CP_NUM-1:0]           cp_stall_request,
    input  logic [CP_NUM-1:0]           cp_result_valid,
    input  logic [REG_ADDR_WIDTH-1:0]   cp_reg_addr [CP_NUM-1:0],
    input  logic [CP_NUM-1:0]           cp_reg_write,
    input  logic                        offload_request,
    input  logic [1:0]                  offload_cp_select,
    input  logic [INST_WIDTH-1:0]       offload_instruction,
    input  logic [REG_ADDR_WIDTH-1:0]   offload_rs1,
    input  logic [REG_ADDR_WIDTH-1:0]   offload_rs2,
    input  logic [REG_ADDR_WIDTH-1:0]   offload_rd,
    input  logic                        mem_busy,
    input  logic                        mem_conflict,
    output logic                        if_stall,
    output logic                        id_stall,
    output logic                        ex_stall,
    output logic                        mm_stall,
    output logic                        wb_stall,
    output logic                        global_stall,
    output logic                        offload_stall,
    output logic                        offload_ready,
    output logic                        offload_timeout,
    output logic [3:0]                  stall_reason,
    output logic [$clog2(STALL_TIMEOUT)-1:0] stall_counter,
    output logic [CP_NUM-1:0]           cp_dependency_stall
);

    typedef enum logic [3:0] {
        STALL_NONE              = 4'h0,
        STALL_CP_BUSY           = 4'h1,
        STALL_DATA_HAZARD       = 4'h2,
        STALL_STRUCTURAL_HAZARD = 4'h3,
        STALL_CP_EXCEPTION      = 4'h4,
        STALL_MEM_CONFLICT      = 4'h5,
        STALL_CP_TIMEOUT        = 4'h6,
        STALL_RESOURCE_CONFLICT = 4'h7
    } stall_reason_t;

    logic [$clog2(STALL_TIMEOUT)-1:0] timeout_counter;
    logic stall_timeout_flag;
    stall_reason_t current_stall_reason;
    logic [CP_NUM-1:0] cp_pending_ops;
    logic [REG_ADDR_WIDTH-1:0] pending_rd [CP_NUM-1:0];
    logic [CP_NUM-1:0] pending_reg_write;
    logic raw_hazard_rs1, raw_hazard_rs2;
    logic war_hazard, waw_hazard;
    logic structural_hazard;
    logic cp_resource_conflict;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cp_pending_ops <= '0;
            for (int i = 0; i < CP_NUM; i++) begin
                pending_rd[i] <= '0;
            end
            pending_reg_write <= '0;
        end else begin
            if (offload_request && !offload_stall && offload_cp_select < CP_NUM) begin
                cp_pending_ops[offload_cp_select] <= 1'b1;
                pending_rd[offload_cp_select] <= offload_rd;
                pending_reg_write[offload_cp_select] <= (offload_rd != '0);
            end
            
            for (int i = 0; i < CP_NUM; i++) begin
                if (cp_result_valid[i] || cp_exception[i]) begin
                    cp_pending_ops[i] <= 1'b0;
                    pending_rd[i] <= '0;
                    pending_reg_write[i] <= 1'b0;
                end
            end
        end
    end
    
    always_comb begin
        raw_hazard_rs1 = 1'b0;
        raw_hazard_rs2 = 1'b0;
        
        if (id_valid && offload_request) begin
            for (int i = 0; i < CP_NUM; i++) begin
                if (cp_pending_ops[i] && pending_reg_write[i]) begin
                    if (offload_rs1 == pending_rd[i] && offload_rs1 != '0) begin
                        raw_hazard_rs1 = 1'b1;
                    end
                    if (offload_rs2 == pending_rd[i] && offload_rs2 != '0) begin
                        raw_hazard_rs2 = 1'b1;
                    end
                end
            end
            
            if (ex_valid && ex_reg_write && ex_rd != '0) begin
                if (offload_rs1 == ex_rd) raw_hazard_rs1 = 1'b1;
                if (offload_rs2 == ex_rd) raw_hazard_rs2 = 1'b1;
            end
            
            if (mm_valid && mm_reg_write && mm_rd != '0) begin
                if (offload_rs1 == mm_rd) raw_hazard_rs1 = 1'b1;
                if (offload_rs2 == mm_rd) raw_hazard_rs2 = 1'b1;
            end
        end
    end
    
    always_comb begin
        waw_hazard = 1'b0;
        
        if (id_valid && offload_request && offload_rd != '0) begin
            for (int i = 0; i < CP_NUM; i++) begin
                if (cp_pending_ops[i] && pending_reg_write[i] && !waw_hazard) begin
                    if (offload_rd == pending_rd[i]) begin
                        waw_hazard = 1'b1;
                    end
                end
            end
            
            if (ex_valid && ex_reg_write && offload_rd == ex_rd) begin
                waw_hazard = 1'b1;
            end
            if (mm_valid && mm_reg_write && offload_rd == mm_rd) begin
                waw_hazard = 1'b1;
            end
        end
    end
    
    assign war_hazard = 1'b0;
    
    always_comb begin
        structural_hazard = 1'b0;
        cp_resource_conflict = 1'b0;
        
        if (offload_request && offload_cp_select < CP_NUM) begin
            structural_hazard = cp_busy[offload_cp_select];
            
            if (mem_busy || mem_conflict) begin
                cp_resource_conflict = 1'b1;
            end
        end
    end
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            timeout_counter <= '0;
            stall_timeout_flag <= 1'b0;
        end else begin
            if (global_stall) begin
                if (timeout_counter < STALL_TIMEOUT - 1) begin
                    timeout_counter <= timeout_counter + 1;
                    stall_timeout_flag <= 1'b0;
                end else begin
                    stall_timeout_flag <= 1'b1;
                end
            end else begin
                timeout_counter <= '0;
                stall_timeout_flag <= 1'b0;
            end
        end
    end
    
    always_comb begin
        if_stall = 1'b0;
        id_stall = 1'b0;
        ex_stall = 1'b0;
        mm_stall = 1'b0;
        wb_stall = 1'b0;
        offload_stall = 1'b0;
        current_stall_reason = STALL_NONE;
        
        if (stall_timeout_flag) begin
            global_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_CP_TIMEOUT;
        end else if (|cp_exception) begin
            global_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_CP_EXCEPTION;
        end else if (raw_hazard_rs1 || raw_hazard_rs2) begin
            id_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_DATA_HAZARD;
        end else if (waw_hazard) begin
            id_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_DATA_HAZARD;
        end else if (structural_hazard) begin
            id_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_STRUCTURAL_HAZARD;
        end else if (cp_resource_conflict) begin
            id_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_RESOURCE_CONFLICT;
        end else if (|cp_stall_request) begin
            global_stall = 1'b1;
            offload_stall = 1'b1;
            current_stall_reason = STALL_CP_BUSY;
        end else begin
            global_stall = 1'b0;
        end
        
        if (id_stall) begin
            if_stall = 1'b1;
        end
        
        if (global_stall) begin
            if_stall = 1'b1;
            id_stall = 1'b1;
            ex_stall = 1'b1;
            mm_stall = 1'b1;
            wb_stall = 1'b1;
        end
    end
    
    always_comb begin
        for (int i = 0; i < CP_NUM; i++) begin
            cp_dependency_stall[i] = cp_pending_ops[i] && 
                                   ((raw_hazard_rs1 && pending_rd[i] == offload_rs1) ||
                                    (raw_hazard_rs2 && pending_rd[i] == offload_rs2) ||
                                    (waw_hazard && pending_rd[i] == offload_rd));
        end
    end
    
    assign offload_ready = !offload_stall && offload_request;
    assign offload_timeout = stall_timeout_flag;
    assign stall_reason = current_stall_reason;
    assign stall_counter = timeout_counter;
endmodule