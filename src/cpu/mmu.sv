`ifndef DISABLE_MMU

module mmu #(
    parameter VADDR_WIDTH = 32,
    parameter PADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter TLB_ENTRIES = 16,
    parameter PAGE_SIZE = 4096
)(
    input  logic                    clk,
    input  logic                    rst_n,
    
    // CPU Interface
    input  logic [VADDR_WIDTH-1:0]  vaddr,
    input  logic                    req_valid,
    input  logic                    req_write,
    input  logic [1:0]              req_priv,
    output logic [PADDR_WIDTH-1:0] paddr,
    output logic                    trans_valid,
    output logic                    page_fault,
    output logic                    access_fault,
    
    // Page Table Base Register (from CSR)
    input  logic [PADDR_WIDTH-1:0] satp,
    input  logic                    vm_enable,
    
    // Memory Interface for page table walks
    output logic                    ptw_req,
    output logic [PADDR_WIDTH-1:0] ptw_addr,
    input  logic [DATA_WIDTH-1:0]  ptw_data,
    input  logic                    ptw_ready,
    
    // TLB Management
    input  logic                    tlb_flush,
    input  logic                    tlb_flush_vaddr,
    input  logic [VADDR_WIDTH-1:0] tlb_flush_addr
);

    localparam VPN_WIDTH = 10;
    localparam PPN_WIDTH = 20;
    localparam OFFSET_WIDTH = 12;
    
    // Page Table Entry (PTE) format for Sv32
    logic [11:0] pte_ppn1;
    logic [9:0]  pte_ppn0;
    logic [1:0]  pte_rsw;
    logic        pte_d;
    logic        pte_a;
    logic        pte_g;
    logic        pte_u;
    logic        pte_x;
    logic        pte_w;
    logic        pte_r;
    logic        pte_v;
    
    // TLB Entry - simplified structure for 32-bit
    logic              tlb_valid [TLB_ENTRIES-1:0];
    logic [19:0]       tlb_vpn [TLB_ENTRIES-1:0];
    logic [19:0]       tlb_ppn [TLB_ENTRIES-1:0];
    logic              tlb_g [TLB_ENTRIES-1:0];
    logic              tlb_u [TLB_ENTRIES-1:0];
    logic              tlb_x [TLB_ENTRIES-1:0];
    logic              tlb_w [TLB_ENTRIES-1:0];
    logic              tlb_r [TLB_ENTRIES-1:0];
    logic              tlb_d [TLB_ENTRIES-1:0];
    logic              tlb_a [TLB_ENTRIES-1:0];
    logic              tlb_level [TLB_ENTRIES-1:0];
    
    logic [$clog2(TLB_ENTRIES)-1:0] tlb_replace_idx;
    
    // Address breakdown for Sv32
    logic [9:0]  vpn1, vpn0;
    logic [11:0] page_offset;
    
    assign vpn1 = vaddr[31:22];
    assign vpn0 = vaddr[21:12];
    assign page_offset = vaddr[11:0];
    
    // TLB lookup
    logic tlb_hit;
    logic [$clog2(TLB_ENTRIES)-1:0] tlb_hit_idx;
    logic              tlb_hit_valid;
    logic [19:0]       tlb_hit_vpn;
    logic [19:0]       tlb_hit_ppn;
    logic              tlb_hit_g;
    logic              tlb_hit_u;
    logic              tlb_hit_x;
    logic              tlb_hit_w;
    logic              tlb_hit_r;
    logic              tlb_hit_d;
    logic              tlb_hit_a;
    logic              tlb_hit_level;
    
    // TLB lookup logic
    always_comb begin
        tlb_hit = 1'b0;
        tlb_hit_idx = '0;
        tlb_hit_valid = 1'b0;
        tlb_hit_vpn = '0;
        tlb_hit_ppn = '0;
        tlb_hit_g = 1'b0;
        tlb_hit_u = 1'b0;
        tlb_hit_x = 1'b0;
        tlb_hit_w = 1'b0;
        tlb_hit_r = 1'b0;
        tlb_hit_d = 1'b0;
        tlb_hit_a = 1'b0;
        tlb_hit_level = 1'b0;
        
        for (int j = 0; j < TLB_ENTRIES; j++) begin
            logic vpn_match;  // Declare at the beginning of for loop
            vpn_match = 1'b0; // Initialize it
            
            if (tlb_valid[j] && !tlb_hit) begin
                // Check VPN based on page size
                if (tlb_level[j]) begin
                    // 4MB page (superpage)
                    vpn_match = (tlb_vpn[j][19:10] == vpn1);
                end else begin
                    // 4KB page
                    vpn_match = (tlb_vpn[j] == {vpn1, vpn0});
                end
                
                if (vpn_match) begin
                    tlb_hit = 1'b1;
                    tlb_hit_idx = j[$clog2(TLB_ENTRIES)-1:0];
                    tlb_hit_valid = tlb_valid[j];
                    tlb_hit_vpn = tlb_vpn[j];
                    tlb_hit_ppn = tlb_ppn[j];
                    tlb_hit_g = tlb_g[j];
                    tlb_hit_u = tlb_u[j];
                    tlb_hit_x = tlb_x[j];
                    tlb_hit_w = tlb_w[j];
                    tlb_hit_r = tlb_r[j];
                    tlb_hit_d = tlb_d[j];
                    tlb_hit_a = tlb_a[j];
                    tlb_hit_level = tlb_level[j];
                end
            end
        end
    end
    
    // Permission checking
    logic perm_valid;
    logic priv_ok;
    logic perm_ok;

    always_comb begin
        perm_valid = 1'b0;
        priv_ok    = 1'b0;
        perm_ok    = 1'b0;

        if (tlb_hit) begin
            // privilege check
            if (req_priv == 2'b11)       priv_ok = 1'b1;      // M-mode
            else if (req_priv == 2'b01)  priv_ok = !tlb_hit_u; // S-mode
            else                         priv_ok = tlb_hit_u;  // U-mode

            // access type check
            if (req_write) perm_ok = tlb_hit_w;
            else           perm_ok = tlb_hit_r;

            perm_valid = priv_ok && perm_ok;
        end
    end

    // Page table walk state machine - simplified for Sv32
    typedef enum logic [2:0] {
        IDLE       = 3'b000,
        PTW_L1     = 3'b001,
        PTW_L0     = 3'b010,
        PTW_WAIT   = 3'b011,
        UPDATE_TLB = 3'b100,
        FAULT      = 3'b101
    } ptw_state_t;
    
    ptw_state_t ptw_state, ptw_next_state;
    logic [31:0] pte_data;
    logic ptw_level;
    logic [PADDR_WIDTH-1:0] ptw_base;
    
    // Extract PTE fields from data
    always_comb begin
        pte_ppn1     = ptw_data[31:20];
        pte_ppn0     = ptw_data[19:10];
        pte_rsw      = ptw_data[9:8];
        pte_d        = ptw_data[7];
        pte_a        = ptw_data[6];
        pte_g        = ptw_data[5];
        pte_u        = ptw_data[4];
        pte_x        = ptw_data[3];
        pte_w        = ptw_data[2];
        pte_r        = ptw_data[1];
        pte_v        = ptw_data[0];
    end
    
    // State machine
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ptw_state <= IDLE;
            ptw_level <= '0;
            ptw_base <= '0;
            pte_data <= '0;
            ptw_addr <= '0;  // Initialize ptw_addr
        end else begin
            ptw_state <= ptw_next_state;
            
            case (ptw_state)
                IDLE: begin
                    if (!tlb_hit && req_valid && vm_enable) begin
                        ptw_base <= {12'b0, satp[19:0]} << 12; // Page table base
                        ptw_level <= 1'b1; // Start at level 1
                    end
                end
                
                PTW_L1: begin
                    /* verilator lint_off WIDTHEXPAND */
                    ptw_addr <= ptw_base + ({22'b0, vpn1} << 2); // 4-byte PTEs
                    /* verilator lint_on WIDTHEXPAND */
                end
                
                PTW_L0: begin
                    /* verilator lint_off WIDTHEXPAND */
                    /* verilator lint_off WIDTHTRUNC */
                    ptw_addr <= ({10'b0, pte_ppn1, pte_ppn0} << 12) + ({22'b0, vpn0} << 2);
                    /* verilator lint_on WIDTHTRUNC */
                    /* verilator lint_on WIDTHEXPAND */
                    ptw_level <= 1'b0;
                end
                
                PTW_WAIT: begin
                    if (ptw_ready) begin
                        pte_data <= ptw_data;
                    end
                end
                
                UPDATE_TLB: begin
                    // Update TLB with new entry
                    tlb_valid[tlb_replace_idx] <= 1'b1;
                    tlb_vpn[tlb_replace_idx] <= {vpn1, vpn0};
                    /* verilator lint_off WIDTHTRUNC */
                    tlb_ppn[tlb_replace_idx] <= {pte_ppn1, pte_ppn0}[19:0]; // Explicit truncation
                    /* verilator lint_on WIDTHTRUNC */
                    tlb_g[tlb_replace_idx] <= pte_g;
                    tlb_u[tlb_replace_idx] <= pte_u;
                    tlb_x[tlb_replace_idx] <= pte_x;
                    tlb_w[tlb_replace_idx] <= pte_w;
                    tlb_r[tlb_replace_idx] <= pte_r;
                    tlb_d[tlb_replace_idx] <= pte_d;
                    tlb_a[tlb_replace_idx] <= pte_a;
                    tlb_level[tlb_replace_idx] <= ptw_level;
                    
                    // Simple round-robin replacement
                    tlb_replace_idx <= tlb_replace_idx + 1;
                end
                
                default: begin
                    // FAULT and other states - do nothing
                end
            endcase
        end
    end
    
    // Next state logic
    always_comb begin
        ptw_next_state = ptw_state;
        ptw_req = 1'b0;
        
        case (ptw_state)
            IDLE: begin
                if (!tlb_hit && req_valid && vm_enable) begin
                    ptw_next_state = PTW_L1;
                end
            end
            
            PTW_L1, PTW_L0: begin
                ptw_req = 1'b1;
                ptw_next_state = PTW_WAIT;
            end
            
            PTW_WAIT: begin
                if (ptw_ready) begin
                    if (!pte_v || (!pte_r && !pte_w && !pte_x)) begin
                        // Invalid PTE or pointer to next level
                        if (ptw_level) begin
                            ptw_next_state = PTW_L0;
                        end else begin
                            ptw_next_state = FAULT;
                        end
                    end else begin
                        // Valid leaf PTE
                        ptw_next_state = UPDATE_TLB;
                    end
                end
            end
            
            UPDATE_TLB: begin
                ptw_next_state = IDLE;
            end
            
            FAULT: begin
                ptw_next_state = IDLE;
            end
            
            default: begin
                ptw_next_state = IDLE;
            end
        endcase
    end

    // TLB management - use generate for loop to avoid issues
    genvar i;
    generate
        for (i = 0; i < TLB_ENTRIES; i++) begin : tlb_init
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    tlb_valid[i] <= 1'b0;
                end else if (tlb_flush) begin
                    if (tlb_flush_vaddr) begin
                        // Flush specific address
                        if (tlb_valid[i] && tlb_vpn[i] == tlb_flush_addr[31:12]) begin
                            tlb_valid[i] <= 1'b0;
                        end
                    end else begin
                        // Flush entire TLB
                        tlb_valid[i] <= 1'b0;
                    end
                end
            end
        end
    endgenerate
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            tlb_replace_idx <= '0;
        end
    end
    
    // Address translation
    always_comb begin
        if (!vm_enable) begin
            // Virtual memory disabled - direct mapping
            paddr = vaddr;
            trans_valid = req_valid;
            page_fault = 1'b0;
            access_fault = 1'b0;
        end else if (tlb_hit) begin
            // TLB hit - translate address
            if (tlb_hit_level) begin
                // 4MB page
                paddr = {tlb_hit_ppn[19:10], vpn0, page_offset};
            end else begin
                // 4KB page
                paddr = {tlb_hit_ppn, page_offset};
            end
            trans_valid = perm_valid;
            page_fault = !tlb_hit_valid;
            access_fault = !perm_valid;
        end else if (ptw_state == UPDATE_TLB) begin
            // Just completed page table walk
            if (ptw_level) begin
                // 4MB page
                /* verilator lint_off WIDTHTRUNC */
                paddr = {{pte_ppn1, pte_ppn0}[19:10], vpn0, page_offset};
                /* verilator lint_on WIDTHTRUNC */
            end else begin
                // 4KB page
                /* verilator lint_off WIDTHTRUNC */
                paddr = {pte_ppn1[9:0], pte_ppn0, page_offset};
                /* verilator lint_on WIDTHTRUNC */
            end
            trans_valid = 1'b1;
            page_fault = 1'b0;
            access_fault = 1'b0;
        end else begin
            // Miss or walking
            paddr = '0;
            trans_valid = 1'b0;
            page_fault = (ptw_state == FAULT);
            access_fault = 1'b0;
        end
    end

endmodule

`else
// Simplified MMU bypass for resource-constrained FPGA
module mmu #(
    parameter VADDR_WIDTH = 32,
    parameter PADDR_WIDTH = 32,
    parameter DATA_WIDTH = 32,
    parameter TLB_ENTRIES = 16,
    parameter PAGE_SIZE = 4096
)(
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic [VADDR_WIDTH-1:0]  vaddr,
    input  logic                    req_valid,
    input  logic                    req_write,
    input  logic [1:0]              req_priv,
    output logic [PADDR_WIDTH-1:0] paddr,
    output logic                    trans_valid,
    output logic                    page_fault,
    output logic                    access_fault,
    input  logic [PADDR_WIDTH-1:0] satp,
    input  logic                    vm_enable,
    output logic                    ptw_req,
    output logic [PADDR_WIDTH-1:0] ptw_addr,
    input  logic [DATA_WIDTH-1:0]  ptw_data,
    input  logic                    ptw_ready,
    input  logic                    tlb_flush,
    input  logic                    tlb_flush_vaddr,
    input  logic [VADDR_WIDTH-1:0] tlb_flush_addr
);
    // Direct mapping - no translation
    assign paddr = vaddr;
    assign trans_valid = req_valid;
    assign page_fault = 1'b0;
    assign access_fault = 1'b0;
    assign ptw_req = 1'b0;
    assign ptw_addr = '0;
endmodule
`endif