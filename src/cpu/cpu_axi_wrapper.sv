module cpu_axi_wrapper #(
    parameter C_S_AXI_DATA_WIDTH = 32,
    parameter C_S_AXI_ADDR_WIDTH = 32,
    parameter ADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter INST_WIDTH = 32,
    parameter REG_NUM = 32
)(
    // AXI4-Lite Clock and Reset
    input  logic                                s_axi_aclk,
    input  logic                                s_axi_aresetn,
    
    // AXI4-Lite Control Interface (for CPU control/status)
    // Write Address Channel
    input  logic [C_S_AXI_ADDR_WIDTH-1:0]      s_axi_awaddr,
    input  logic [2:0]                         s_axi_awprot,
    input  logic                               s_axi_awvalid,
    output logic                               s_axi_awready,
    
    // Write Data Channel
    input  logic [C_S_AXI_DATA_WIDTH-1:0]      s_axi_wdata,
    input  logic [(C_S_AXI_DATA_WIDTH/8)-1:0]  s_axi_wstrb,
    input  logic                               s_axi_wvalid,
    output logic                               s_axi_wready,
    
    // Write Response Channel
    output logic [1:0]                         s_axi_bresp,
    output logic                               s_axi_bvalid,
    input  logic                               s_axi_bready,
    
    // Read Address Channel
    input  logic [C_S_AXI_ADDR_WIDTH-1:0]      s_axi_araddr,
    input  logic [2:0]                         s_axi_arprot,
    input  logic                               s_axi_arvalid,
    output logic                               s_axi_arready,
    
    // Read Data Channel
    output logic [C_S_AXI_DATA_WIDTH-1:0]      s_axi_rdata,
    output logic [1:0]                         s_axi_rresp,
    output logic                               s_axi_rvalid,
    input  logic                               s_axi_rready,
    
    // Memory interfaces (to external memory controller)
    output logic [ADDR_WIDTH-1:0]              imem_addr,
    input  logic [INST_WIDTH-1:0]              imem_read_data,
    output logic                               imem_read,
    input  logic                               imem_ready,
    
    output logic [ADDR_WIDTH-1:0]              dmem_addr,
    output logic [DATA_WIDTH-1:0]              dmem_write_data,
    output logic                               dmem_read,
    output logic                               dmem_write,
    output logic [3:0]                         dmem_byte_enable,  // Changed from 8 to 4 bytes for 32-bit
    input  logic [DATA_WIDTH-1:0]              dmem_read_data,
    input  logic                               dmem_ready,
    
    // External signals
    input  logic                               external_interrupt,
    output logic [7:0]                         debug_leds,
    output logic                               cpu_active
);

    // Control Registers
    logic cpu_enable;
    logic cpu_reset_req;
    logic single_step_mode;
    logic interrupt_enable;
    logic [31:0] breakpoint_addr;
    
    // Status signals from CPU
    logic [31:0] cpu_pc;
    logic cpu_stall;
    logic [3:0] cpu_state;
    logic [31:0] cycle_count_low;   // Changed to 32-bit counters
    logic [31:0] cycle_count_high;
    logic [31:0] instruction_count_low;
    logic [31:0] instruction_count_high;
    logic [31:0] gpr_data [0:31];
    
    // CPU control signals
    logic cpu_clk;
    logic cpu_rst_n;
    
    // Generate CPU clock
    assign cpu_clk = s_axi_aclk;
    
    // CPU reset logic
    logic [3:0] reset_counter;
    always_ff @(posedge cpu_clk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            cpu_rst_n <= 1'b0;
            reset_counter <= '0;
        end else if (cpu_reset_req) begin
            cpu_rst_n <= 1'b0;
            reset_counter <= 4'hF;
        end else if (reset_counter != 0) begin
            reset_counter <= reset_counter - 1;
            cpu_rst_n <= 1'b0;
        end else begin
            cpu_rst_n <= cpu_enable;
        end
    end
    
    // Interrupt synchronization
    logic [2:0] interrupt_sync;
    logic cpu_interrupt;
    always_ff @(posedge cpu_clk or negedge cpu_rst_n) begin
        if (!cpu_rst_n) begin
            interrupt_sync <= '0;
        end else begin
            interrupt_sync <= {interrupt_sync[1:0], external_interrupt & interrupt_enable};
        end
    end
    assign cpu_interrupt = interrupt_sync[2];
    
    // CPU instance
    cpu_top #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .INST_WIDTH(INST_WIDTH),
        .REG_NUM(REG_NUM)
    ) cpu_core (
        .clk(cpu_clk),
        .rst_n(cpu_rst_n),
        .interr(cpu_interrupt),
        
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
        
        // Debug outputs
        .debug_pc(cpu_pc),
        .debug_stall(cpu_stall),
        .debug_state(cpu_state),
        
        // Coprocessor interface
        .cp_instruction_detected(),
        .cp_instruction_out(),
        .cp_stall_external(1'b0)
    );
    
    // Performance counters (32-bit)
    logic [63:0] cycle_count;
    logic [63:0] instruction_count;
    
    always_ff @(posedge cpu_clk or negedge cpu_rst_n) begin
        if (!cpu_rst_n) begin
            cycle_count <= '0;
            instruction_count <= '0;
        end else if (cpu_enable) begin
            cycle_count <= cycle_count + 1;
            if (imem_read && imem_ready && !cpu_stall) begin
                instruction_count <= instruction_count + 1;
            end
        end
    end
    
    assign cycle_count_low = cycle_count[31:0];
    assign cycle_count_high = cycle_count[63:32];
    assign instruction_count_low = instruction_count[31:0];
    assign instruction_count_high = instruction_count[63:32];
    
    // AXI4-Lite Control Interface State Machine
    typedef enum logic [1:0] {
        AXI_IDLE,
        AXI_WRITE,
        AXI_READ
    } axi_state_t;
    
    axi_state_t axi_state;
    logic [C_S_AXI_ADDR_WIDTH-1:0] axi_awaddr_reg;
    logic [C_S_AXI_ADDR_WIDTH-1:0] axi_araddr_reg;
    logic axi_write_ready;
    logic axi_read_valid;
    logic [C_S_AXI_DATA_WIDTH-1:0] axi_read_data;
    
    // AXI Write Logic
    always_ff @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            cpu_enable <= 1'b0;
            cpu_reset_req <= 1'b0;
            single_step_mode <= 1'b0;
            interrupt_enable <= 1'b0;
            breakpoint_addr <= '0;
            axi_awaddr_reg <= '0;
            axi_write_ready <= 1'b0;
            s_axi_bvalid <= 1'b0;
        end else begin
            cpu_reset_req <= 1'b0;
            
            if (s_axi_awvalid && s_axi_awready) begin
                axi_awaddr_reg <= s_axi_awaddr;
            end
            
            if (s_axi_wvalid && s_axi_wready) begin
                case (axi_awaddr_reg[7:0])
                    8'h00: begin
                        cpu_enable <= s_axi_wdata[0];
                        cpu_reset_req <= s_axi_wdata[1];
                        single_step_mode <= s_axi_wdata[2];
                        interrupt_enable <= s_axi_wdata[3];
                    end
                    8'h1C: breakpoint_addr <= s_axi_wdata;
                    default: ;
                endcase
                s_axi_bvalid <= 1'b1;
            end
            
            if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end
        end
    end
    
    // AXI Read Logic
    always_ff @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            axi_araddr_reg <= '0;
            axi_read_valid <= 1'b0;
            axi_read_data <= '0;
        end else begin
            if (s_axi_arvalid && s_axi_arready) begin
                axi_araddr_reg <= s_axi_araddr;
                axi_read_valid <= 1'b1;
                
                case (s_axi_araddr[7:0])
                    8'h00: axi_read_data <= {28'b0, interrupt_enable, single_step_mode, cpu_reset_req, cpu_enable};
                    8'h04: axi_read_data <= {28'b0, interrupt_sync[2], cpu_stall, cpu_state[0], cpu_rst_n};
                    8'h08: axi_read_data <= cpu_pc;
                    8'h0C: axi_read_data <= instruction_count_low;
                    8'h10: axi_read_data <= instruction_count_high;
                    8'h14: axi_read_data <= cycle_count_low;
                    8'h18: axi_read_data <= cycle_count_high;
                    8'h1C: axi_read_data <= breakpoint_addr;
                    default: begin
                        if (s_axi_araddr[7:0] >= 8'h20 && s_axi_araddr[7:0] <= 8'h9C) begin
                            logic [4:0] reg_idx = (s_axi_araddr[7:0] - 8'h20) >> 2;
                            axi_read_data <= gpr_data[reg_idx];
                        end else begin
                            axi_read_data <= 32'hDEADBEEF;
                        end
                    end
                endcase
            end
            
            if (s_axi_rvalid && s_axi_rready) begin
                axi_read_valid <= 1'b0;
            end
        end
    end
    
    // AXI4-Lite Interface Assignments
    assign s_axi_awready = (axi_state == AXI_IDLE);
    assign s_axi_wready = (axi_state == AXI_IDLE) || (s_axi_awvalid && s_axi_awready);
    assign s_axi_bresp = 2'b00;
    
    assign s_axi_arready = (axi_state == AXI_IDLE) && !s_axi_awvalid;
    assign s_axi_rdata = axi_read_data;
    assign s_axi_rresp = 2'b00;
    assign s_axi_rvalid = axi_read_valid;
    
    // Debug outputs
    assign debug_leds = {
        cpu_enable,
        cpu_rst_n,
        cpu_stall,
        cpu_interrupt,
        imem_read,
        dmem_read | dmem_write,
        cpu_state[1:0]
    };
    
    assign cpu_active = cpu_enable && cpu_rst_n && !cpu_stall;

endmodule