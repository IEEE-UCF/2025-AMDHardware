module vertex_fetch #(
    parameter int ATTR_WIDTH = 32,  // width of one attribute (e.g., x)
    parameter int ATTRS_PER_VERTEX = 8,  // e.g., pos(4), color(4)
    parameter int ADDR_WIDTH = 32
) (
    input logic clk,
    input logic rst_n,

    // control
    input logic i_start_fetch,
    input logic [ADDR_WIDTH-1:0] i_base_addr,  // start of vertex array in memory
    input logic [15:0] i_vertex_index,
    output logic o_fetch_done,

    // connection to memory bus
    output logic o_mem_req,
    output logic [ADDR_WIDTH-1:0] o_mem_addr,
    input logic i_mem_ready,
    input logic [ATTR_WIDTH*ATTRS_PER_VERTEX-1:0] i_mem_rdata,

    // output
    output logic [ATTR_WIDTH*ATTRS_PER_VERTEX-1:0] o_vertex_data
);

  typedef enum logic [1:0] {
    IDLE,
    FETCH,
    WAIT_MEM,
    DONE
  } state_t;
  state_t current_state, next_state;

  logic [ATTR_WIDTH*ATTRS_PER_VERTEX-1:0] data_reg;

  // vertex stride is the size of one vertex in bytes
  localparam int VERTEXSTRIDE = (ATTR_WIDTH * ATTRS_PER_VERTEX) / 8;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) current_state <= IDLE;
    else current_state <= next_state;
  end

  always_comb begin
    next_state = current_state;
    o_mem_req = 1'b0;
    o_fetch_done = 1'b0;

    case (current_state)
      IDLE: if (i_start_fetch) next_state = FETCH;
      FETCH: begin
        o_mem_req = 1'b1;
        if (i_mem_ready) next_state = WAIT_MEM;
      end
      WAIT_MEM: begin
        o_fetch_done = 1'b1;
        next_state   = DONE;
      end
      DONE: begin
        o_fetch_done = 1'b1;
        next_state   = IDLE;
      end
    endcase
  end

  // register the read data when it's ready
  always_ff @(posedge clk) begin
    if (current_state == FETCH && i_mem_ready) begin
      data_reg <= i_mem_rdata;
    end
  end

  // calculate where the vertex is in memory
  assign o_mem_addr = i_base_addr + (i_vertex_index * VERTEXSTRIDE);
  assign o_vertex_data = data_reg;

endmodule

