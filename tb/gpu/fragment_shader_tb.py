import cocotb
import random
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, Timer

def pack_vector(vec, width):
    max_val = (1 << width) - 1
    packed = 0
    for i, val in enumerate(vec):
        packed |= (val & max_val) << (i * width)
    return packed

def unpack_vector(packed, width, size):
    mask = (1 << width) - 1
    return [(packed >> (i * width)) & mask for i in range(size)]

async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.i_frag_valid.value = 0
    dut.i_frag_x.value = 0
    dut.i_frag_y.value = 0
    dut.i_frag_color.value = 0
    dut.i_frag_tex_coord.value = 0
    dut.i_texel_valid.value = 0
    dut.i_texel_color.value = 0
    await Timer(20, units="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    dut._log.info("Reset complete.")

@cocotb.test()
async def test_shader_pipeline(dut):
    data_width = int(dut.DATA_WIDTH.value)
    vec_size = int(dut.VEC_SIZE.value)
    cord_width = int(dut.CORD_WIDTH.value)

    max_data_val = (1 << data_width) - 1
    max_cord_val = (1 << (cord_width - 1)) - 1
    min_cord_val = -(1 << (cord_width - 1))

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    num_tests = 1000
    dut._log.info(f"Running {num_tests} randomized fragment tests...")

    for test_num in range(num_tests):
        frag_x = random.randint(min_cord_val, max_cord_val)
        frag_y = random.randint(min_cord_val, max_cord_val)
        frag_color = [random.randint(0, max_data_val) for _ in range(vec_size)]
        frag_tex_coord = [random.randint(0, max_data_val) for _ in range(2)]

        await RisingEdge(dut.clk)
        dut.i_frag_valid.value = 1
        dut.i_frag_x.value = frag_x
        dut.i_frag_y.value = frag_y
        dut.i_frag_color.value = pack_vector(frag_color, data_width)
        dut.i_frag_tex_coord.value = pack_vector(frag_tex_coord, data_width)

        await ReadOnly()
        assert dut.o_tex_req_valid.value == 1, "Shader did not request texture data"
        assert dut.o_tex_u_coord.value == frag_tex_coord[0], "Incorrect U coordinate"
        assert dut.o_tex_v_coord.value == frag_tex_coord[1], "Incorrect V coordinate"

        await RisingEdge(dut.clk)
        dut.i_frag_valid.value = 0

        texture_latency = random.randint(1, 5)
        for _ in range(texture_latency):
            await RisingEdge(dut.clk)
        
        texel_color = [random.randint(0, max_data_val) for _ in range(vec_size)]
        dut.i_texel_valid.value = 1
        dut.i_texel_color.value = pack_vector(texel_color, data_width)

        await RisingEdge(dut.clk)
        dut.i_texel_valid.value = 0

        await ReadOnly()
        assert dut.o_pixel_valid.value == 1, "Final pixel output is not valid"
        assert dut.o_pixel_x.value.signed_integer == frag_x, "Pixel X coordinate mismatch"
        assert dut.o_pixel_y.value.signed_integer == frag_y, "Pixel Y coordinate mismatch"

        expected_color = [
            (c1 * c2) & max_data_val for c1, c2 in zip(frag_color, texel_color)
        ]
        
        dut_pixel_color = unpack_vector(dut.o_pixel_color.value.integer, data_width, vec_size)

        if dut_pixel_color != expected_color:
            dut._log.error(f"Mismatch on iteration {test_num + 1}!")
            dut._log.error(f" Fragment Color: {frag_color}")
            dut._log.error(f" Texel Color: {texel_color}")
            dut._log.error(f" DUT Color: {dut_pixel_color}")
            dut._log.error(f" Expected Color: {expected_color}")
            assert False, "Pixel color mismatch"

        await RisingEdge(dut.clk)

    dut._log.info(f"--- All {num_tests} tests passed! ---")