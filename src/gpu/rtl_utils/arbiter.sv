module arbiter #(
    parameter int NUM_REQUESTERS = 4
) (
    input logic clk,
    input logic rst_n,

    input logic [NUM_REQUESTERS-1:0] i_requests,
    output logic [NUM_REQUESTERS-1:0] o_grants
);

    logic [NUM_REQUESTERS-1:0] last_grant_reg;
    logic [NUM_REQUESTERS-1:0] next_grant_state;
    logic [NUM_REQUESTERS*2-1:0] priority_mask;
    logic [NUM_REQUESTERS*2-1:0] masked_requests;

    always_comb begin
        logic grant_found;

        next_grant_state = '0;
        grant_found = 1'b0; // Initialize the flag to 0

        // duplicating the request vector avoids tricky wrap around logic
        masked_requests = {i_requests, i_requests} & priority_mask;

        if (|i_requests) begin
            for (int i = 0; i < NUM_REQUESTERS * 2; i++) begin
                if (masked_requests[i] && !grant_found) begin
                    next_grant_state[i % NUM_REQUESTERS] = 1'b1;
                    grant_found = 1'b1; // set the flag to 1 to block other grants
                end
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // default priority to requester 0
            last_grant_reg <= {{(NUM_REQUESTERS-1){1'b0}}, 1'b1};
        end else begin
            if (|next_grant_state) begin
                last_grant_reg <= next_grant_state;
            end
        end
    end

    // rotate priority based on the last grant
    assign priority_mask = ({{NUM_REQUESTERS{1'b1}}, {NUM_REQUESTERS{1'b0}}}) >> $countones(last_grant_reg);
    assign o_grants = next_grant_state;

endmodule