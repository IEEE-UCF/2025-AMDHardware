module controller #(
    parameter int QUEUE_DEPTH = 16
) (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [31:0] i_bus_addr,
    input  logic [31:0] i_bus_wdata,
    input  logic        i_bus_we,
    output logic [31:0] o_bus_rdata,

    input  logic        i_pipeline_busy,
    output logic        o_start_pipeline,

    output logic        o_irq
);

    localparam ADDR_CONTROL = 32'h00;
    localparam ADDR_STATUS  = 32'h04;

    localparam CTRL_START_BIT     = 0;
    localparam CTRL_IRQ_CLEAR_BIT = 1;

    localparam STATUS_BUSY_BIT          = 0;
    localparam STATUS_IRQ_PENDING_BIT   = 1;
    localparam STATUS_QUEUE_PENDING_BIT = 2;
    localparam STATUS_QUEUE_COUNT_LOW   = 4;
    localparam STATUS_QUEUE_COUNT_HIGH  = STATUS_QUEUE_COUNT_LOW + $clog2(QUEUE_DEPTH) - 1;

    logic start_cmd;
    logic irq_clear_cmd;
    logic irq_pending;
    logic busy_last_cycle;
    logic fire_start_pulse;

    logic [$clog2(QUEUE_DEPTH)-1:0] pending_starts_count;

    assign start_cmd     = i_bus_we && (i_bus_addr == ADDR_CONTROL) && i_bus_wdata[CTRL_START_BIT];
    assign irq_clear_cmd = i_bus_we && (i_bus_addr == ADDR_CONTROL) && i_bus_wdata[CTRL_IRQ_CLEAR_BIT];

    assign fire_start_pulse = (pending_starts_count > 0 || start_cmd) && !i_pipeline_busy;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            o_start_pipeline <= 1'b0;
        end else begin
            o_start_pipeline <= fire_start_pulse;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_starts_count <= '0;
        end else begin
            if (start_cmd && fire_start_pulse) begin
                pending_starts_count <= pending_starts_count;
            end else if (fire_start_pulse) begin
                pending_starts_count <= pending_starts_count - 1;
            end else if (start_cmd) begin
                if (pending_starts_count < QUEUE_DEPTH - 1) begin
                    pending_starts_count <= pending_starts_count + 1;
                end
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            irq_pending     <= 1'b0;
            busy_last_cycle <= 1'b0;
        end else begin
            busy_last_cycle <= i_pipeline_busy;
            if (busy_last_cycle && !i_pipeline_busy) begin
                irq_pending <= 1'b1;
            end else if (irq_clear_cmd) begin
                irq_pending <= 1'b0;
            end
        end
    end

    always_comb begin
        o_bus_rdata = '0;
        if (i_bus_addr == ADDR_STATUS) begin
            o_bus_rdata[STATUS_BUSY_BIT]          = i_pipeline_busy;
            o_bus_rdata[STATUS_IRQ_PENDING_BIT]   = irq_pending;
            o_bus_rdata[STATUS_QUEUE_PENDING_BIT] = (pending_starts_count > 0);
            o_bus_rdata[STATUS_QUEUE_COUNT_HIGH:STATUS_QUEUE_COUNT_LOW] = pending_starts_count;
        end
    end

    assign o_irq = irq_pending;

endmodule
