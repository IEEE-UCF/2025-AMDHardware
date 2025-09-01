module instruction_buffer #(parameter INST_WIDTH = 32, BUFFER_DEPTH = 8)(
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire                  write_en,
    input  wire [INST_WIDTH-1:0] data_in,
    input  wire                  read_en,
    output wire [INST_WIDTH-1:0] data_out,
    output wire                  is_empty,
    output wire                  is_full
);
    localparam int PTRW = $clog2(BUFFER_DEPTH);

    reg [INST_WIDTH-1:0] inst_buffer [0:BUFFER_DEPTH-1];
    reg [PTRW:0]         write_ptr;
    reg [PTRW:0]         read_ptr;

    wire is_empty_flag;
    wire is_full_flag;
    wire lower_bits_equal = (write_ptr[PTRW-1:0] == read_ptr[PTRW-1:0]);
    wire upper_bit_equal  = (write_ptr[PTRW]      == read_ptr[PTRW]);
    assign is_empty_flag    = (upper_bit_equal & lower_bits_equal);
    assign is_full_flag     = (~upper_bit_equal & lower_bits_equal);

    wire do_write = write_en && !is_full_flag;
    wire do_read  = read_en  && !is_empty_flag;

    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            write_ptr <= '0;
            read_ptr  <= '0;
            
            for (i = 0; i < BUFFER_DEPTH; i = i + 1) begin
                inst_buffer[i] <= {INST_WIDTH{1'bX}};
            end
        end else begin
            // Split the read and write pointer updates into their own conditions
            // This is clearer and less error-prone than combining them.
            if (do_write) begin
                inst_buffer[write_ptr[PTRW-1:0]] <= data_in;
                write_ptr <= write_ptr + 1;
            end

            if (do_read) begin
                read_ptr <= read_ptr + 1;
            end
        end
    end

    assign is_empty = is_empty_flag;
    assign is_full  = is_full_flag;

endmodule