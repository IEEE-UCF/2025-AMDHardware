module _interconnect #(
    parameter int NUM_MASTERS = 2,
    parameter int NUM_SLAVES  = 4,
    parameter int ADDR_WIDTH  = 32,
    parameter int DATA_WIDTH  = 32
) (
    input  logic                               clk,
    input  logic                               rst_n,

    input  logic [NUM_MASTERS-1:0]                         i_master_req,
    input  logic [NUM_MASTERS-1:0][ADDR_WIDTH-1:0]         i_master_addr,
    input  logic [NUM_MASTERS-1:0][DATA_WIDTH-1:0]         i_master_wdata,
    output logic [NUM_MASTERS-1:0][DATA_WIDTH-1:0]         o_master_rdata,

    output logic [NUM_SLAVES-1:0]                          o_slave_req,
    output logic [NUM_SLAVES-1:0][ADDR_WIDTH-1:0]          o_slave_addr,
    output logic [NUM_SLAVES-1:0][DATA_WIDTH-1:0]          o_slave_wdata,
    input  logic [NUM_SLAVES-1:0][DATA_WIDTH-1:0]          i_slave_rdata
);

    logic [NUM_MASTERS-1:0]                 grants;
    logic [ADDR_WIDTH-1:0]                  granted_addr;
    logic [DATA_WIDTH-1:0]                  granted_wdata;
    logic [$clog2(NUM_MASTERS)-1:0]         granted_index;

    arbiter #(
        .NUM_REQUESTERS(NUM_MASTERS)
    ) arbiter_inst (
        .clk        (clk),
        .rst_n      (rst_n),
        .i_requests (i_master_req),
        .o_grants   (grants)
    );

    always_comb begin
        granted_addr  = '0;
        granted_wdata = '0;
        granted_index = '0;
        for (int i = 0; i < NUM_MASTERS; i++) begin
            if (grants[i]) begin
                granted_addr  = i_master_addr[i];
                granted_wdata = i_master_wdata[i];
                granted_index = i;
            end
        end
    end

    logic [1:0] slave_select;
    assign slave_select = granted_addr[15:14];

    always_comb begin
        o_slave_req   = '0;
        o_slave_addr  = '0;
        o_slave_wdata = '0;

        if (|grants) begin
            o_slave_req[slave_select]   = 1'b1;
            o_slave_addr[slave_select]  = granted_addr;
            o_slave_wdata[slave_select] = granted_wdata;
        end
    end

    always_comb begin
        o_master_rdata = '0;
        for (int i = 0; i < NUM_MASTERS; i++) begin
            if (grants[i]) begin
                o_master_rdata[i] = i_slave_rdata[slave_select];
            end
        end
    end

endmodule
