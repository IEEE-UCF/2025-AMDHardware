module _interconnect #(
    parameter ADDR_WIDTH = 32,  // Fixed to 32-bit for Red Pitaya
    parameter DATA_WIDTH = 32,  // Fixed to 32-bit for Red Pitaya
    parameter NUM_MASTERS = 2,  // CPU, GPU
    parameter NUM_SLAVES = 4    // Main Memory, GPU Memory, Peripherals, Config
)(
    input  logic                    clk,
    input  logic                    rst_n,
    
    // Master ports (CPU, GPU)
    input  logic [NUM_MASTERS-1:0]                master_req,
    input  logic [NUM_MASTERS-1:0][ADDR_WIDTH-1:0] master_addr,
    input  logic [NUM_MASTERS-1:0][DATA_WIDTH-1:0] master_wdata,
    input  logic [NUM_MASTERS-1:0]                master_we,
    input  logic [NUM_MASTERS-1:0][3:0]           master_be,     // Byte enable - 4 bytes for 32-bit
    output logic [NUM_MASTERS-1:0][DATA_WIDTH-1:0] master_rdata,
    output logic [NUM_MASTERS-1:0]                master_ready,
    
    // Slave ports (Memory regions)
    output logic [NUM_SLAVES-1:0]                 slave_req,
    output logic [NUM_SLAVES-1:0][ADDR_WIDTH-1:0] slave_addr,
    output logic [NUM_SLAVES-1:0][DATA_WIDTH-1:0] slave_wdata,
    output logic [NUM_SLAVES-1:0]                 slave_we,
    output logic [NUM_SLAVES-1:0][3:0]            slave_be,
    input  logic [NUM_SLAVES-1:0][DATA_WIDTH-1:0] slave_rdata,
    input  logic [NUM_SLAVES-1:0]                 slave_ready
);

    // Address map for 32-bit addressing
    localparam logic [ADDR_WIDTH-1:0] MAIN_MEM_BASE   = 32'h0000_0000;
    localparam logic [ADDR_WIDTH-1:0] MAIN_MEM_SIZE   = 32'h2000_0000; // 512MB (Red Pitaya DDR)
    localparam logic [ADDR_WIDTH-1:0] GPU_MEM_BASE    = 32'h1000_0000;
    localparam logic [ADDR_WIDTH-1:0] GPU_MEM_SIZE    = 32'h1000_0000; // 256MB for GPU

    localparam logic [ADDR_WIDTH-1:0] PERIPH_BASE     = 32'h0C00_0000;
    localparam logic [ADDR_WIDTH-1:0] PERIPH_SIZE     = 32'h0100_0000; // 16MB
    localparam logic [ADDR_WIDTH-1:0] CONFIG_BASE     = 32'h0F00_0000;
    localparam logic [ADDR_WIDTH-1:0] CONFIG_SIZE     = 32'h0100_0000; // 16MB
    
    // Arbitration logic
    logic [NUM_MASTERS-1:0] grant;
    logic [$clog2(NUM_MASTERS)-1:0] granted_master;
    logic arb_valid;
    
    // Slave selection
    logic [$clog2(NUM_SLAVES)-1:0] selected_slave;
    logic slave_valid;
    
    // Pipeline registers for timing
    logic [ADDR_WIDTH-1:0] addr_reg;
    logic [DATA_WIDTH-1:0] wdata_reg;
    logic we_reg;
    logic [3:0] be_reg;  // Fixed to 4 bytes
    logic [$clog2(NUM_MASTERS)-1:0] master_id_reg;
    logic req_valid_reg;
    
    
    logic [$clog2(NUM_MASTERS)-1:0] last_granted;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            last_granted <= '0;
            grant <= '0;
            arb_valid <= '0;
        end else begin
            grant <= '0;
            arb_valid <= '0;
            
            // Simple priority arbitration: CPU (0) has priority over GPU (1)
            if (master_req[0]) begin
                grant[0] <= 1'b1;
                granted_master <= 0;
                arb_valid <= 1'b1;
                last_granted <= 0;
            end else if (master_req[1]) begin
                grant[1] <= 1'b1;
                granted_master <= 1;
                arb_valid <= 1'b1;
                last_granted <= 1;
            end
        end
    end
    
    function automatic logic [$clog2(NUM_SLAVES)-1:0] decode_address(logic [ADDR_WIDTH-1:0] addr);
        if (addr >= MAIN_MEM_BASE && addr < MAIN_MEM_BASE + MAIN_MEM_SIZE)
            return 0; // Main memory
        else if (addr >= GPU_MEM_BASE && addr < GPU_MEM_BASE + GPU_MEM_SIZE)
            return 1; // GPU memory
        else if (addr >= PERIPH_BASE && addr < PERIPH_BASE + PERIPH_SIZE)
            return 2; // Peripherals
        else if (addr >= CONFIG_BASE && addr < CONFIG_BASE + CONFIG_SIZE)
            return 3; // Configuration
        else
            return 0; // Default to main memory
    endfunction
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            addr_reg <= '0;
            wdata_reg <= '0;
            we_reg <= '0;
            be_reg <= '0;
            master_id_reg <= '0;
            req_valid_reg <= '0;
            selected_slave <= '0;
            slave_valid <= '0;
        end else begin
            if (arb_valid) begin
                addr_reg <= master_addr[granted_master];
                wdata_reg <= master_wdata[granted_master];
                we_reg <= master_we[granted_master];
                be_reg <= master_be[granted_master];
                master_id_reg <= granted_master;
                req_valid_reg <= 1'b1;
                selected_slave <= decode_address(master_addr[granted_master]);
                slave_valid <= 1'b1;
            end else begin
                req_valid_reg <= 1'b0;
                slave_valid <= 1'b0;
            end
        end
    end
    
    
    genvar i;
    generate
        for (i = 0; i < NUM_SLAVES; i++) begin : slave_gen
            always_comb begin
                if (slave_valid && selected_slave == i) begin
                    slave_req[i] = req_valid_reg;
                    slave_addr[i] = addr_reg;
                    slave_wdata[i] = wdata_reg;
                    slave_we[i] = we_reg;
                    slave_be[i] = be_reg;
                end else begin
                    slave_req[i] = 1'b0;
                    slave_addr[i] = '0;
                    slave_wdata[i] = '0;
                    slave_we[i] = 1'b0;
                    slave_be[i] = '0;
                end
            end
        end
    endgenerate
    
    logic [DATA_WIDTH-1:0] selected_rdata;
    logic selected_ready;
    
    always_comb begin
        selected_rdata = slave_rdata[selected_slave];
        selected_ready = slave_ready[selected_slave];
    end
    
    // Route response back to requesting master
    generate
        for (i = 0; i < NUM_MASTERS; i++) begin : master_resp_gen
            always_comb begin
                if (req_valid_reg && master_id_reg == i) begin
                    master_rdata[i] = selected_rdata;
                    master_ready[i] = selected_ready;
                end else begin
                    master_rdata[i] = '0;
                    master_ready[i] = 1'b0;
                end
            end
        end
    endgenerate
    
    
    logic [31:0] total_requests;
    logic [31:0] cpu_requests;
    logic [31:0] gpu_requests;
    logic [31:0] conflict_count;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            total_requests <= '0;
            cpu_requests <= '0;
            gpu_requests <= '0;
            conflict_count <= '0;
        end else begin
            if (arb_valid) begin
                total_requests <= total_requests + 1;
                if (granted_master == 0)
                    cpu_requests <= cpu_requests + 1;
                else
                    gpu_requests <= gpu_requests + 1;
            end
            
            // Count conflicts (both masters requesting simultaneously)
            if (master_req[0] && master_req[1])
                conflict_count <= conflict_count + 1;
        end
    end

endmodule