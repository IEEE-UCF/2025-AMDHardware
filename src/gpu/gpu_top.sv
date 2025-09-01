module gpu_top #(
  parameter int DATA_WIDTH   = 32,
  parameter int VEC_SIZE     = 4,
  parameter int CORD_WIDTH   = 10,
  parameter int FB_WIDTH     = 640,
  parameter int FB_HEIGHT    = 480,
  parameter int ADDR_WIDTH   = 32,
  parameter int INSTR_DEPTH  = 256,
  parameter int FIFO_DEPTH   = 64,
  parameter int NUM_MASTERS  = 3, // 0: vertex_fetch, 1: shader_core, 2: framebuffer
  parameter int NUM_SLAVES   = 1  // 0: main memory (DRAM)
)(
  input  logic                     clk,
  input  logic                     rst_n,

  // CPU bus interface for control and shader loading
  input  logic                     i_bus_we,
  input  logic [ADDR_WIDTH-1:0]    i_bus_addr,
  input  logic [DATA_WIDTH-1:0]    i_bus_wdata,
  output logic [DATA_WIDTH-1:0]    o_bus_rdata,

  // Main memory (DRAM) interface
  output logic                     o_dram_we,
  output logic [ADDR_WIDTH-1:0]    o_dram_addr,
  output logic [DATA_WIDTH-1:0]    o_dram_wdata,
  input  logic [DATA_WIDTH-1:0]    i_dram_rdata
);

  localparam int VERTEX_POS_BITS    = CORD_WIDTH * 2 * 3; // 3 vertices x,y
  localparam int VERTEX_COLOR_BITS  = DATA_WIDTH * 3;     // 3 colors
  localparam int VERTEX_UV_BITS     = DATA_WIDTH * 2 * 3; // 3 UV pairs
  localparam int VERTEX_TOTAL_BITS  = VERTEX_POS_BITS + VERTEX_COLOR_BITS + VERTEX_UV_BITS;
  localparam int FIFO_DATA_WIDTH    = (2 * CORD_WIDTH) + (3 * (2 * CORD_WIDTH + 1));

  // Memory map for CPU interface
  localparam ADDR_CONTROL      = 32'h00000000;  // Control register
  localparam ADDR_STATUS       = 32'h00000004;  // Status register
  localparam ADDR_VERTEX_BASE  = 32'h00000008;  // Vertex buffer base address
  localparam ADDR_VERTEX_COUNT = 32'h0000000C;  // Number of vertices
  localparam ADDR_PC           = 32'h00000010;  // Shader program counter
  localparam ADDR_SHADER_BASE  = 32'h00001000;  // Shader memory starts here

  // Pipeline states
  typedef enum logic [2:0] {
    PIPE_IDLE,
    PIPE_FETCH_VERTEX,
    PIPE_EXECUTE_SHADER,
    PIPE_RASTERIZE,
    PIPE_FRAGMENT,
    PIPE_DONE
  } pipeline_state_t;

  // Reset sync
  logic glbl_rst_n;

  // Control registers
  logic [ADDR_WIDTH-1:0] vertex_base_addr;
  logic [15:0]           vertex_count;
  logic [15:0]           current_vertex;
  // program counter is 32 bits for bus access, lower bits index instruction memory
  logic [31:0]           shader_pc;
  
  // Pipeline control
  pipeline_state_t pipe_state, next_pipe_state;
  logic pipeline_start;
  logic pipeline_busy;
  logic vertex_fetch_done;
  logic rasterizer_done;
  logic shader_exec_done;
  
  // Controller interface
  logic controller_start;
  logic controller_irq;
  
  // Interconnect signals
  logic [NUM_MASTERS-1:0] master_req;
  logic [NUM_MASTERS-1:0][ADDR_WIDTH-1:0] master_addr;
  logic [NUM_MASTERS-1:0][DATA_WIDTH-1:0] master_wdata;
  logic [NUM_MASTERS-1:0][DATA_WIDTH-1:0] master_rdata;

  logic [NUM_SLAVES-1:0] slave_req;
  logic [NUM_SLAVES-1:0][ADDR_WIDTH-1:0] slave_addr;
  logic [NUM_SLAVES-1:0][DATA_WIDTH-1:0] slave_wdata;
  logic [NUM_SLAVES-1:0][DATA_WIDTH-1:0] slave_rdata;

  // Shader signals
  logic [INSTR_WIDTH-1:0] shader_instruction;
  logic [INSTR_WIDTH-1:0] shader_host_rdata;
  logic shader_exec_en;
  logic [4:0] shader_opcode;
  logic [3:0] shader_rd, shader_rs1, shader_rs2;
  logic [11:0] shader_imm;
  
  // Vertex data
  logic [VERTEX_TOTAL_BITS-1:0] vertex_data;
  logic signed [CORD_WIDTH-1:0] v0x, v0y, v1x, v1y, v2x, v2y;
  logic [DATA_WIDTH-1:0] v0_color, v1_color, v2_color;
  logic [DATA_WIDTH-1:0] v0_u, v0_v, v1_u, v1_v, v2_u, v2_v;
  
  // Rasterizer signals
  logic rast_start;
  logic rast_frag_valid;
  logic signed [CORD_WIDTH-1:0] frag_x, frag_y;
  logic signed [(CORD_WIDTH*2):0] lambda0, lambda1, lambda2;
  
  // FIFO signals
  logic fifo_wr, fifo_rd, fifo_full, fifo_empty;
  logic [FIFO_DATA_WIDTH-1:0] fifo_wdata, fifo_rdata;
  
  // Fragment shader signals
  logic fs_in_valid;
  logic signed [CORD_WIDTH-1:0] fs_in_x, fs_in_y;
  logic signed [(CORD_WIDTH*2):0] fs_in_lambda0, fs_in_lambda1, fs_in_lambda2;
  logic [DATA_WIDTH-1:0] interpolated_color, interpolated_u, interpolated_v;
  
  // Texture unit signals
  logic tex_req_valid;
  logic [DATA_WIDTH-1:0] tex_u, tex_v;
  logic texel_valid;
  logic [DATA_WIDTH-1:0] texel_color_single;
  logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] texel_color_vec;
  
  // Framebuffer signals
  logic pixel_we;
  logic signed [CORD_WIDTH-1:0] pixel_x, pixel_y;
  logic [VEC_SIZE-1:0][DATA_WIDTH-1:0] pixel_color;

  reset_sync reset_sync_inst (
    .clk    (clk),
    .arst_n (rst_n),
    .srst_n (glbl_rst_n)
  );

  always_ff @(posedge clk or negedge glbl_rst_n) begin
    if (!glbl_rst_n) begin
      vertex_base_addr <= '0;
      vertex_count     <= '0;
      shader_pc        <= '0;
      controller_start <= 1'b0;
    end else begin
      controller_start <= 1'b0;  // Single cycle pulse
      
      if (i_bus_we) begin
        case (i_bus_addr)
          ADDR_CONTROL: begin
            if (i_bus_wdata[0]) controller_start <= 1'b1;
          end
          ADDR_VERTEX_BASE:  vertex_base_addr <= i_bus_wdata;
          ADDR_VERTEX_COUNT: vertex_count     <= i_bus_wdata[15:0];
          ADDR_PC:           shader_pc        <= i_bus_wdata;
        endcase
      end
    end
  end
  
  // CPU read path
  always_comb begin
    if (i_bus_addr >= ADDR_SHADER_BASE) begin
      o_bus_rdata = shader_host_rdata;
    end else begin
      o_bus_rdata = '0;
      case (i_bus_addr)
        ADDR_STATUS:       o_bus_rdata = {30'b0, controller_irq, pipeline_busy};
        ADDR_VERTEX_BASE:  o_bus_rdata = vertex_base_addr;
        ADDR_VERTEX_COUNT: o_bus_rdata = {16'b0, vertex_count};
        ADDR_PC:           o_bus_rdata = shader_pc;
        default:           o_bus_rdata = '0;
      endcase
    end
  end

  assign pipeline_busy = (pipe_state != PIPE_IDLE);
  
  always_ff @(posedge clk or negedge glbl_rst_n) begin
    if (!glbl_rst_n) begin
      pipe_state <= PIPE_IDLE;
      current_vertex <= '0;
    end else begin
      pipe_state <= next_pipe_state;
      
      if (pipe_state == PIPE_IDLE && controller_start) begin
        current_vertex <= '0;
      end else if (pipe_state == PIPE_FETCH_VERTEX && vertex_fetch_done) begin
        current_vertex <= current_vertex + 3;  // Move to next triangle
      end
    end
  end
  
  always_comb begin
    next_pipe_state = pipe_state;
    
    case (pipe_state)
      PIPE_IDLE: begin
        if (controller_start) next_pipe_state = PIPE_FETCH_VERTEX;
      end
      
      PIPE_FETCH_VERTEX: begin
        if (vertex_fetch_done) next_pipe_state = PIPE_EXECUTE_SHADER;
      end
      
      PIPE_EXECUTE_SHADER: begin
        // Simple: execute one shader instruction then move on
        next_pipe_state = PIPE_RASTERIZE;
      end
      
      PIPE_RASTERIZE: begin
        if (rasterizer_done) begin
          if (current_vertex >= vertex_count) 
            next_pipe_state = PIPE_DONE;
          else
            next_pipe_state = PIPE_FETCH_VERTEX;
        end
      end
      
      PIPE_DONE: begin
        next_pipe_state = PIPE_IDLE;
      end
      
      default: next_pipe_state = PIPE_IDLE;
    endcase
  end

  controller #(
    .QUEUE_DEPTH(16)
  ) ctrl_inst (
    .clk              (clk),
    .rst_n            (glbl_rst_n),
    .i_bus_addr       (i_bus_addr),
    .i_bus_wdata      (i_bus_wdata),
    .i_bus_we         (i_bus_we && (i_bus_addr == ADDR_CONTROL || i_bus_addr == ADDR_STATUS)),
    .o_bus_rdata      (),  // Not used, we handle reads above
    .i_pipeline_busy  (pipeline_busy),
    .o_start_pipeline (pipeline_start),
    .o_irq            (controller_irq)
  );

  localparam int INSTR_WIDTH = 32;
  
  shader_loader #(
    .INSTR_WIDTH(INSTR_WIDTH),
    .INSTR_DEPTH(INSTR_DEPTH)
  ) shader_loader_inst (
    .clk          (clk),
    .rst_n        (glbl_rst_n),
    .i_host_we    (i_bus_we && i_bus_addr >= ADDR_SHADER_BASE),
    .i_host_addr  (i_bus_addr[$clog2(INSTR_DEPTH)-1+2:2]),  // Word addressing
    .i_host_wdata (i_bus_wdata),
    .o_host_rdata (shader_host_rdata),
    .i_gpu_addr   (shader_pc[$clog2(INSTR_DEPTH)-1:0]),
    .o_gpu_instr  (shader_instruction)
  );
  
  instruction_decoder decoder_inst (
    .i_instruction_word (shader_instruction),
    .o_opcode          (shader_opcode),
    .o_rd_addr         (shader_rd),
    .o_rs1_addr        (shader_rs1),
    .o_rs2_addr        (shader_rs2),
    .o_imm             (shader_imm)
  );

  assign shader_exec_en = (pipe_state == PIPE_EXECUTE_SHADER);
  
  shader_core #(
    .DATA_WIDTH(DATA_WIDTH),
    .VEC_SIZE  (VEC_SIZE),
    .NUM_REGS  (16)
  ) core0 (
    .clk        (clk),
    .rst_n      (glbl_rst_n),
    .i_exec_en  (shader_exec_en),
    .i_opcode   (shader_opcode),
    .i_rd_addr  (shader_rd),
    .i_rs1_addr (shader_rs1),
    .i_rs2_addr (shader_rs2),
    .o_mem_req  (master_req[1]),
    .i_mem_ready(1'b1)  // Always ready for simplicity
  );
  
  assign master_addr[1] = '0;   // Would need proper address generation
  assign master_wdata[1] = '0;

  _interconnect #(
    .NUM_MASTERS (NUM_MASTERS),
    .NUM_SLAVES  (NUM_SLAVES),
    .ADDR_WIDTH  (ADDR_WIDTH),
    .DATA_WIDTH  (DATA_WIDTH)
  ) interconnect_inst (
    .clk            (clk),
    .rst_n          (glbl_rst_n),
    .i_master_req   (master_req),
    .i_master_addr  (master_addr),
    .i_master_wdata (master_wdata),
    .o_master_rdata (master_rdata),
    .o_slave_req    (slave_req),
    .o_slave_addr   (slave_addr),
    .o_slave_wdata  (slave_wdata),
    .i_slave_rdata  (slave_rdata)
  );
  
  logic [DATA_WIDTH-1:0] dram_rdata_delayed;
  always_ff @(posedge clk) begin
    dram_rdata_delayed <= i_dram_rdata;
  end

  assign o_dram_we = slave_req[0];  // Your interconnect doesn't have separate we signal
  assign o_dram_addr = slave_addr[0];
  assign o_dram_wdata = slave_wdata[0];
  assign slave_rdata[0] = i_dram_rdata;

  vertex_fetch #(
    .ATTR_WIDTH       (32),
    .ATTRS_PER_VERTEX (11),
    .ADDR_WIDTH       (ADDR_WIDTH)
  ) vf_inst (
    .clk           (clk),
    .rst_n         (glbl_rst_n),
    .i_start_fetch (pipe_state == PIPE_FETCH_VERTEX),
    .i_base_addr   (vertex_base_addr),
    .i_vertex_index(current_vertex),
    .o_fetch_done  (vertex_fetch_done),
    .o_mem_req     (master_req[0]),
    .o_mem_addr    (master_addr[0]),
    .i_mem_ready   (1'b1),  // Always ready for simplicity
    .i_mem_rdata   (master_rdata[0]),
    .o_vertex_data (vertex_data[VERTEX_TOTAL_BITS-1:0])
  );
  
  assign master_wdata[0] = '0;  // Vertex fetch only reads
  
  // Unpack vertex data
  assign {v0x, v0y, v1x, v1y, v2x, v2y} = 
         vertex_data[0 +: VERTEX_POS_BITS];
  assign {v0_color, v1_color, v2_color} = 
         vertex_data[VERTEX_POS_BITS +: VERTEX_COLOR_BITS];
  assign {v0_u, v0_v, v1_u, v1_v, v2_u, v2_v} = 
         vertex_data[VERTEX_POS_BITS + VERTEX_COLOR_BITS +: VERTEX_UV_BITS];

  assign rast_start = (pipe_state == PIPE_RASTERIZE);
  
  rasterizer #(
    .CORD_WIDTH(CORD_WIDTH)
  ) rast_inst (
    .clk              (clk),
    .rst_n            (glbl_rst_n),
    .i_start          (rast_start),
    .i_v0_x           (v0x),
    .i_v0_y           (v0y),
    .i_v1_x           (v1x),
    .i_v1_y           (v1y),
    .i_v2_x           (v2x),
    .i_v2_y           (v2y),
    .o_fragment_valid (rast_frag_valid),
    .o_fragment_x     (frag_x),
    .o_fragment_y     (frag_y),
    .o_lambda0        (lambda0),
    .o_lambda1        (lambda1),
    .o_lambda2        (lambda2),
    .o_done           (rasterizer_done)
  );

  assign fifo_wr = rast_frag_valid;
  assign fifo_wdata = {frag_x, frag_y, lambda0, lambda1, lambda2};
  
  fifo #(
    .DATA_WIDTH(FIFO_DATA_WIDTH),
    .DEPTH     (FIFO_DEPTH)
  ) frag_fifo (
    .clk      (clk),
    .rst_n    (glbl_rst_n),
    .i_wr_en  (fifo_wr),
    .i_w_data (fifo_wdata),
    .i_rd_en  (fifo_rd),
    .o_r_data (fifo_rdata),
    .o_full   (fifo_full),
    .o_empty  (fifo_empty)
  );
  
  assign fs_in_valid = !fifo_empty;
  assign fifo_rd = fs_in_valid && !fifo_full;  // Read when we can process
  assign {fs_in_x, fs_in_y, fs_in_lambda0, fs_in_lambda1, fs_in_lambda2} = fifo_rdata;

  attribute_interpolator #(
    .ATTR_WIDTH  (DATA_WIDTH),
    .WEIGHT_WIDTH(2*CORD_WIDTH+1)
  ) color_interp (
    .i_attr0   (v0_color),
    .i_attr1   (v1_color),
    .i_attr2   (v2_color),
    .i_lambda0 (fs_in_lambda0),
    .i_lambda1 (fs_in_lambda1),
    .i_lambda2 (fs_in_lambda2),
    .o_interpolated_attr(interpolated_color)
  );
  
  attribute_interpolator #(
    .ATTR_WIDTH  (DATA_WIDTH),
    .WEIGHT_WIDTH(2*CORD_WIDTH+1)
  ) u_interp (
    .i_attr0   (v0_u),
    .i_attr1   (v1_u),
    .i_attr2   (v2_u),
    .i_lambda0 (fs_in_lambda0),
    .i_lambda1 (fs_in_lambda1),
    .i_lambda2 (fs_in_lambda2),
    .o_interpolated_attr(interpolated_u)
  );
  
  attribute_interpolator #(
    .ATTR_WIDTH  (DATA_WIDTH),
    .WEIGHT_WIDTH(2*CORD_WIDTH+1)
  ) v_interp (
    .i_attr0   (v0_v),
    .i_attr1   (v1_v),
    .i_attr2   (v2_v),
    .i_lambda0 (fs_in_lambda0),
    .i_lambda1 (fs_in_lambda1),
    .i_lambda2 (fs_in_lambda2),
    .o_interpolated_attr(interpolated_v)
  );

  fragment_shader #(
    .DATA_WIDTH(DATA_WIDTH),
    .VEC_SIZE  (VEC_SIZE),
    .CORD_WIDTH(CORD_WIDTH)
  ) fs_inst (
    .clk             (clk),
    .rst_n           (glbl_rst_n),
    .i_frag_valid    (fs_in_valid),
    .i_frag_x        (fs_in_x),
    .i_frag_y        (fs_in_y),
    .i_frag_color    ({VEC_SIZE{interpolated_color}}),  // Replicate for all channels
    .i_frag_tex_coord({interpolated_v, interpolated_u}),
    .o_tex_req_valid (tex_req_valid),
    .o_tex_u_coord   (tex_u),
    .o_tex_v_coord   (tex_v),
    .i_texel_valid   (texel_valid),
    .i_texel_color   (texel_color_vec),
    .o_pixel_valid   (pixel_we),
    .o_pixel_x       (pixel_x),
    .o_pixel_y       (pixel_y),
    .o_pixel_color   (pixel_color)
  );
  
  texture_unit #(
    .TEX_WIDTH  (256),
    .TEX_HEIGHT (256),
    .CORD_WIDTH (16),
    .DATA_WIDTH (DATA_WIDTH)
  ) tex_unit (
    .clk          (clk),
    .rst_n        (glbl_rst_n),
    .i_req_valid  (tex_req_valid),
    .i_u_coord    (tex_u[15:0]),
    .i_v_coord    (tex_v[15:0]),
    .o_data_valid (texel_valid),
    .o_texel_color(texel_color_single)
  );
  
  // Replicate texture color to all vector channels
  assign texel_color_vec = {VEC_SIZE{texel_color_single}};

  framebuffer #(
    .SCREEN_WIDTH (FB_WIDTH),
    .SCREEN_HEIGHT(FB_HEIGHT),
    .COLOR_WIDTH  (DATA_WIDTH)
  ) fb_inst (
    .clk          (clk),
    .rst_n        (glbl_rst_n),
    .i_pixel_we   (pixel_we),
    .i_pixel_x    (pixel_x),
    .i_pixel_y    (pixel_y),
    .i_pixel_color(pixel_color[0]),  // Use first channel for now
    .o_mem_req    (master_req[2]),
    .o_mem_addr   (master_addr[2]),
    .o_mem_wdata  (master_wdata[2])
  );

endmodule

