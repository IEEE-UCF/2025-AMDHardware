module stage_if #(
    parameter ADDR_WIDTH = 32,
    parameter INST_WIDTH = 32, 
    parameter PC_TYPE_NUM = 4
)(
    input  logic                           clk,
    input  logic                           reset,
    input  logic                           stall,
    input  logic                           inst_w_en,
    input  logic [INST_WIDTH-1:0]          inst_w_in,
    input  logic [$clog2(PC_TYPE_NUM)-1:0] pc_sel,
    input  logic [ADDR_WIDTH-1:0]          bra_addr,
    input  logic [ADDR_WIDTH-1:0]          jal_addr,
    input  logic [ADDR_WIDTH-1:0]          jar_addr,
    output logic [ADDR_WIDTH-1:0]          pc,
    output logic [ADDR_WIDTH-1:0]          pc4,
    output logic [INST_WIDTH-1:0]          inst_word,
    output logic                           inst_valid,
    output logic                           inst_buffer_empty,
    output logic                           inst_buffer_full
);

    logic [ADDR_WIDTH-1:0] pc_next;
    logic [ADDR_WIDTH-1:0] pc_curr;
    logic [ADDR_WIDTH-1:0] pc_next_options [0:PC_TYPE_NUM-1];

    assign pc_next_options[0] = pc_curr + 4;
    assign pc_next_options[1] = bra_addr;
    assign pc_next_options[2] = jal_addr;
    assign pc_next_options[3] = jar_addr;

    mux_n #(
        .INPUT_WIDTH(ADDR_WIDTH),
        .INPUT_NUM(PC_TYPE_NUM)
    ) pc_mux (
        .data_in(pc_next_options), 
        .sel(pc_sel),
        .data_out(pc_next)
    );

    reg_if #(
        .ADDR_WIDTH(ADDR_WIDTH)
    ) pc_reg (
        .clk(clk),
        .reset(reset),
        .stall(stall),
        .pc_next(pc_next),
        .pc_reg(pc_curr)
    );

    memory_instruction #(
        .INST_WIDTH(INST_WIDTH),
        .X_WIDTH(4),
        .Y_WIDTH(4)
    ) instruction_memory (
        .Clock(clk),
        .WriteEnable(inst_w_en),
        .X_addr(pc_curr[5:2]),
        .Y_addr(pc_curr[9:6]),
        .Data_in(inst_w_in),
        .Data_out(inst_word)
    );

    assign inst_valid = (pc_sel == 2'b00);
    assign pc = pc_curr;
    assign pc4 = pc_next_options[0];
    assign inst_buffer_empty = 1'b0;
    assign inst_buffer_full = 1'b0;

endmodule

module stage_id #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter INST_WIDTH = 32, 
    parameter REG_NUM = 32
)(
    input  logic                           clk,
    input  logic                           reset,
    input  logic                           interrupt,
    input  logic                           stall,
    input  logic                           w_en,
    input  logic                           w_en_gpu,
    input  logic                           has_imm,
    input  logic                           has_rs1,
    input  logic                           has_rs2,
    input  logic                           has_rs3,
    input  logic [1:0]                     imm_type,
    input  logic [ADDR_WIDTH-1:0]          pc4,
    input  logic [ADDR_WIDTH-1:0]          pc,
    input  logic [ADDR_WIDTH-1:0]          w_result,
    input  logic [ADDR_WIDTH-1:0]          w_result_gpu,
    input  logic [ADDR_WIDTH-1:0]          ex_pro,
    input  logic [ADDR_WIDTH-1:0]          mm_pro,
    input  logic [ADDR_WIDTH-1:0]          mm_mem,
    input  logic [INST_WIDTH-1:0]          inst_word,
    input  logic [$clog2(REG_NUM)-1:0]     load_rd,
    input  logic                           is_load,
    input  logic [$clog2(REG_NUM)-1:0]     w_rd,
    input  logic                           ex_wr_reg_en,
    input  logic                           mm_wr_reg_en,
    input  logic                           mm_is_load,
    input  logic [$clog2(REG_NUM)-1:0]     ex_rd,
    input  logic [$clog2(REG_NUM)-1:0]     mm_rd,
    input  logic [$clog2(REG_NUM)-1:0]     w_rd_gpu,
    input  logic [$clog2(REG_NUM)-1:0]     rs_gpu,
    output logic                           is_equal,
    output logic [ADDR_WIDTH-1:0]          read_out_gpu,
    output logic [ADDR_WIDTH-1:0]          read_out_a,
    output logic [ADDR_WIDTH-1:0]          read_out_b,
    output logic [ADDR_WIDTH-1:0]          bra_addr,
    output logic [ADDR_WIDTH-1:0]          jal_addr,
    output logic [ADDR_WIDTH-1:0]          jar_addr
);

    logic                  inst_buffer_empty;
    logic                  inst_buffer_full;
    logic                  load_stall;
    logic                  reg_stall;
    logic [ADDR_WIDTH-1:0] d_pc;
    logic [ADDR_WIDTH-1:0] d_pc4;
    logic [ADDR_WIDTH-1:0] a_out;
    logic [ADDR_WIDTH-1:0] b_out_options [0:1];
    logic [ADDR_WIDTH-1:0] a_file_out;
    logic [ADDR_WIDTH-1:0] b_file_out;
    logic [INST_WIDTH-1:0] d_inst;

    equ #(
        .DATA_WIDTH(ADDR_WIDTH)
    ) rs_equality (
        .data_a(a_out),
        .data_b(b_out_options[0]),
        .is_equal(is_equal)
    );
    
    branch_calc #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .INST_WIDTH(INST_WIDTH)
    ) branch_addrs (
        .pc(pc),
        .inst(d_inst),
        .data_a(a_out),
        .bra_addr(bra_addr),
        .jal_addr(jal_addr),
        .jalr_addr(jar_addr)
    );

    stage_id_stall #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .REG_NUM(REG_NUM)
    ) load_stall_check (
        .load_rd(load_rd),
        .is_load(is_load),
        .rs1_addr(d_inst[19:15]),
        .rs2_addr(d_inst[24:20]),
        .rs3_addr(d_inst[31:27]),
        .has_rs1(has_rs1),
        .has_rs2(has_rs2),
        .has_rs3(has_rs3),
        .stall(load_stall)
    );

    assign reg_stall = stall | load_stall;

    reg_if_to_id #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .INST_WIDTH(INST_WIDTH)
    ) stage2 (
        .clk(clk),
        .reset(reset),
        .stall(reg_stall),
        .pc4(pc4),
        .pc(pc),
        .inst(inst_word),
        .inst_buffer_empty(inst_buffer_empty),
        .inst_buffer_full(inst_buffer_full),
        .d_pc(d_pc),
        .d_pc4(d_pc4),
        .d_inst(d_inst)
    );

    register_bank_list #(
        .REG_NUM(REG_NUM),
        .DATA_WIDTH(ADDR_WIDTH)
    ) register_file (
        .clk(clk),
        .reset(reset),
        .interrupt(interrupt),
        .write_addr_cpu(w_rd),
        .write_addr_gpu(w_rd_gpu),
        .data_in_cpu(w_result),
        .data_in_gpu(w_result_gpu),
        .write_en_cpu(w_en),
        .write_en_gpu(w_en_gpu),
        .read_addr_a(d_inst[19:15]),
        .read_addr_b(d_inst[24:20]),
        .read_addr_gpu(rs_gpu),
        .data_out_a(a_file_out),
        .data_out_b(b_file_out),
        .data_out_gpu(read_out_gpu)
    );
    
    bypass_mux #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .REG_NUM(REG_NUM)
    ) a_bypass (
        .ex_wr_reg_en(ex_wr_reg_en),
        .mm_wr_reg_en(mm_wr_reg_en),
        .mm_is_load(mm_is_load),
        .file_out(a_file_out),
        .ex_pro(ex_pro),
        .mm_pro(mm_pro),
        .mm_mem(mm_mem),
        .file_out_rs(d_inst[19:15]),
        .ex_rd(ex_rd),
        .mm_rd(mm_rd),
        .bypass_out(a_out)
    );
    
    bypass_mux #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .REG_NUM(REG_NUM)
    ) b_bypass (
        .ex_wr_reg_en(ex_wr_reg_en),
        .mm_wr_reg_en(mm_wr_reg_en),
        .mm_is_load(mm_is_load),
        .file_out(b_file_out),
        .ex_pro(ex_pro),
        .mm_pro(mm_pro),
        .mm_mem(mm_mem),
        .file_out_rs(d_inst[24:20]),
        .ex_rd(ex_rd),
        .mm_rd(mm_rd),
        .bypass_out(b_out_options[0])
    );

    imme #(
        .DATA_WIDTH(ADDR_WIDTH),
        .INST_WIDTH(INST_WIDTH),
        .IMM_TYPE_NUM(4)
    ) gen_imme (
        .inst(d_inst),
        .imm_type(imm_type),
        .imm(b_out_options[1])
    );
    
    mux_n #(
        .INPUT_WIDTH(ADDR_WIDTH),
        .INPUT_NUM(2)
    ) b_mux (
        .data_in(b_out_options),
        .sel(has_imm),
        .data_out(read_out_b)
    );

    assign read_out_a = a_out;

endmodule

module stage_id_stall #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter REG_NUM = 32
)(
    input  logic                       is_load,
    input  logic                       has_rs1,
    input  logic                       has_rs2,
    input  logic                       has_rs3,    
    input  logic [$clog2(REG_NUM)-1:0] rs1_addr,
    input  logic [$clog2(REG_NUM)-1:0] rs2_addr,
    input  logic [$clog2(REG_NUM)-1:0] rs3_addr,
    input  logic [$clog2(REG_NUM)-1:0] load_rd,
    output logic                       stall 
);
    assign stall = is_load && ((has_rs1 && (rs1_addr == load_rd)) 
                            || (has_rs2 && (rs2_addr == load_rd)) 
                            || (has_rs3 && (rs3_addr == load_rd)));
endmodule

module pl_stage_exe #(
    parameter DATA_WIDTH = 32  // Changed from 64 to 32
)(
    input  logic [DATA_WIDTH-1:0] ea,
    input  logic [DATA_WIDTH-1:0] eb,
    input  logic [DATA_WIDTH-1:0] epc4,
    input  logic [4:0]            ealuc,
    input  logic                  ecall,
    output logic [DATA_WIDTH-1:0] eal
);
    logic [DATA_WIDTH-1:0] ealu;
    
    always_comb begin
        case (ealuc)
            5'b00000: ealu = ea + eb;
            5'b00001: ealu = ea - eb;
            5'b00010: ealu = ea & eb;
            5'b00011: ealu = ea | eb;
            5'b00100: ealu = ea ^ eb;
            5'b00101: ealu = ~(ea | eb);
            5'b00110: ealu = ~(ea & eb);
            5'b00111: ealu = ea << eb[4:0];  // Changed from eb[5:0] to eb[4:0] for 32-bit
            5'b01000: ealu = ea >> eb[4:0];  // Changed from eb[5:0] to eb[4:0]
            5'b01001: ealu = $signed(ea) >>> eb[4:0];  // Changed from eb[5:0] to eb[4:0]
            5'b01010: ealu = ($signed(ea) < $signed(eb)) ? {{(DATA_WIDTH-1){1'b0}}, 1'b1} : {DATA_WIDTH{1'b0}};
            5'b01011: ealu = (ea < eb) ? {{(DATA_WIDTH-1){1'b0}}, 1'b1} : {DATA_WIDTH{1'b0}};
            5'b01100: ealu = ea;
            5'b01101: ealu = eb;
            5'b01110: ealu = ~ea;
            5'b01111: ealu = (ea == eb) ? {{(DATA_WIDTH-1){1'b0}}, 1'b1} : {DATA_WIDTH{1'b0}};
            5'b10000: ealu = (ea != eb) ? {{(DATA_WIDTH-1){1'b0}}, 1'b1} : {DATA_WIDTH{1'b0}};
            5'b10001: ealu = ea + {{(DATA_WIDTH-1){1'b0}}, 1'b1};
            5'b10010: ealu = ea - {{(DATA_WIDTH-1){1'b0}}, 1'b1};
            default:  ealu = {DATA_WIDTH{1'b0}};
        endcase
    end

    assign eal = ecall ? epc4 : ealu;

endmodule

module mm_stage #(
    parameter DATA_WIDTH = 32,  // Changed from 64 to 32
    parameter ADDR_WIDTH = 32   // Changed from 64 to 32
)(
    input  logic                        clk,
    input  logic                        rst_n,
    input  logic [DATA_WIDTH-1:0]       ex_mem_alu_result,
    input  logic [DATA_WIDTH-1:0]       ex_mem_write_data,
    input  logic [4:0]                  ex_mem_rd,
    input  logic                        ex_mem_mem_read,
    input  logic                        ex_mem_mem_write,
    input  logic                        ex_mem_reg_write,
    output logic [ADDR_WIDTH-1:0]       mem_addr,
    output logic [DATA_WIDTH-1:0]       mem_write_data,
    output logic                        mem_read,
    output logic                        mem_write,
    input  logic [DATA_WIDTH-1:0]       mem_read_data,
    output logic [DATA_WIDTH-1:0]       mem_wb_mem_data,
    output logic [DATA_WIDTH-1:0]       mem_wb_alu_result,
    output logic [4:0]                  mem_wb_rd,
    output logic                        mem_wb_reg_write
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mem_addr         <= '0;
            mem_write_data   <= '0;
            mem_read         <= '0;
            mem_write        <= '0;
            mem_wb_mem_data  <= '0;
            mem_wb_alu_result<= '0;
            mem_wb_rd        <= '0;
            mem_wb_reg_write <= '0;
        end else begin
            mem_addr       <= ex_mem_alu_result;
            mem_write_data <= ex_mem_write_data;
            mem_read       <= ex_mem_mem_read;
            mem_write      <= ex_mem_mem_write;
            mem_wb_alu_result <= ex_mem_alu_result;
            mem_wb_rd         <= ex_mem_rd;
            mem_wb_reg_write  <= ex_mem_reg_write;
            if (ex_mem_mem_read)
                mem_wb_mem_data <= mem_read_data;
            else
                mem_wb_mem_data <= '0;
        end
    end

endmodule

module pl_stage_wb #(
    parameter DATA_WIDTH = 32  // Changed from 64 to 32
)(
    input  logic [DATA_WIDTH-1:0] walu,
    input  logic [DATA_WIDTH-1:0] wmem,
    input  logic                  wmem2reg,
    output logic [DATA_WIDTH-1:0] wdata
);
    assign wdata = wmem2reg ? wmem : walu;
endmodule

module reg_if #(
    parameter ADDR_WIDTH = 32  // Changed from 64 to 32
)(
    input  logic                     clk,
    input  logic                     reset,
    input  logic                     stall,
    input  logic [ADDR_WIDTH-1:0]    pc_next,
    output logic [ADDR_WIDTH-1:0]    pc_reg
);
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            pc_reg <= '0;
        end else if (!stall) begin
            pc_reg <= pc_next;
        end
    end
endmodule

module memory_instruction #(
    parameter INST_WIDTH = 32,
    parameter X_WIDTH = 4,
    parameter Y_WIDTH = 4
)(
    input  logic                    Clock,
    input  logic                    WriteEnable,
    input  logic [X_WIDTH-1:0]      X_addr,
    input  logic [Y_WIDTH-1:0]      Y_addr,
    input  logic [INST_WIDTH-1:0]   Data_in,
    output logic [INST_WIDTH-1:0]   Data_out
);
    localparam DEPTH = 1 << (X_WIDTH + Y_WIDTH);
    logic [INST_WIDTH-1:0] mem [0:DEPTH-1];
    logic [X_WIDTH+Y_WIDTH-1:0] addr = {Y_addr, X_addr};

    initial begin
        for (int i = 0; i < DEPTH; i++) begin
            mem[i] = 32'h00000013; // NOP only
        end
    end

    always_ff @(posedge Clock) begin
        if (WriteEnable) begin
            mem[addr] <= Data_in;
        end
    end

    assign Data_out = mem[addr];
endmodule

module reg_if_to_id #(
    parameter ADDR_WIDTH = 32,  // Changed from 64 to 32
    parameter INST_WIDTH = 32
)(
    input  logic                     clk,
    input  logic                     reset,
    input  logic                     stall,
    input  logic [ADDR_WIDTH-1:0]    pc4,
    input  logic [ADDR_WIDTH-1:0]    pc,
    input  logic [INST_WIDTH-1:0]    inst,
    output logic                     inst_buffer_empty,
    output logic                     inst_buffer_full,
    output logic [ADDR_WIDTH-1:0]    d_pc,
    output logic [ADDR_WIDTH-1:0]    d_pc4,
    output logic [INST_WIDTH-1:0]    d_inst
);
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            d_pc  <= '0;
            d_pc4 <= '0;
            d_inst <= '0;
            inst_buffer_empty <= 1'b1;
            inst_buffer_full  <= 1'b0;
        end else if (!stall) begin
            d_pc  <= pc;
            d_pc4 <= pc4;
            d_inst <= inst;
            inst_buffer_empty <= 1'b0;
            inst_buffer_full  <= 1'b0;
        end
    end
endmodule

module register_bank_list #(
    parameter REG_NUM = 32,
    parameter DATA_WIDTH = 32  // Changed from 64 to 32
)(
    input  logic                       clk,
    input  logic                       reset,
    input  logic                       interrupt,
    input  logic [$clog2(REG_NUM)-1:0] write_addr_cpu,
    input  logic [$clog2(REG_NUM)-1:0] write_addr_gpu,
    input  logic [DATA_WIDTH-1:0]      data_in_cpu,
    input  logic [DATA_WIDTH-1:0]      data_in_gpu,
    input  logic                       write_en_cpu,
    input  logic                       write_en_gpu,
    input  logic [$clog2(REG_NUM)-1:0] read_addr_a,
    input  logic [$clog2(REG_NUM)-1:0] read_addr_b,
    input  logic [$clog2(REG_NUM)-1:0] read_addr_gpu,
    output logic [DATA_WIDTH-1:0]      data_out_a,
    output logic [DATA_WIDTH-1:0]      data_out_b,
    output logic [DATA_WIDTH-1:0]      data_out_gpu
);
    logic [DATA_WIDTH-1:0] cpu_regs [0:REG_NUM-1];
    logic [DATA_WIDTH-1:0] gpu_regs [0:REG_NUM-1];
    
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            for (int i = 0; i < REG_NUM; i++) begin
                cpu_regs[i] <= '0;
                gpu_regs[i] <= '0;
            end
        end else begin
            if (write_en_cpu && write_addr_cpu != 0) begin
                cpu_regs[write_addr_cpu] <= data_in_cpu;
            end
            if (write_en_gpu && write_addr_gpu != 0) begin
                gpu_regs[write_addr_gpu] <= data_in_gpu;
            end
        end
    end

    assign data_out_a   = (read_addr_a   == 0) ? '0 : cpu_regs[read_addr_a];
    assign data_out_b   = (read_addr_b   == 0) ? '0 : cpu_regs[read_addr_b];
    assign data_out_gpu = (read_addr_gpu == 0) ? '0 : gpu_regs[read_addr_gpu];
endmodule