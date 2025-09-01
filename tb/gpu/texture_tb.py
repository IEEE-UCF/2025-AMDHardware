import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock


@cocotb.test()
async def test_texture_corner0(dut):
	cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

	# apply reset
	dut.rst_n.value = 0
	dut.i_req_valid.value = 0
	dut.i_u_coord.value = 0
	dut.i_v_coord.value = 0
	await Timer(100, units="ns")
	dut.rst_n.value = 1
	await RisingEdge(dut.clk)

	expected = 0xDEADBEEF
	try:
		dut.texture_mem[0].value = expected
	except Exception:
		getattr(dut, "texture_mem")[0].value = expected

	# ensure inputs steady, then pulse request for one clock
	dut.i_u_coord.value = 0
	dut.i_v_coord.value = 0
	await RisingEdge(dut.clk)

	dut.i_req_valid.value = 1
	await RisingEdge(dut.clk)
	dut.i_req_valid.value = 0
	await RisingEdge(dut.clk)

	assert int(dut.o_data_valid.value) == 1, f"o_data_valid expected 1, got {int(dut.o_data_valid.value)}"

	got = int(dut.o_texel_color.value)
	assert got == expected, f"o_texel_color mismatch: got 0x{got:08X}, expected 0x{expected:08X}"


@cocotb.test()
async def test_data_valid_follows_req(dut):
	cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

	# reset
	dut.rst_n.value = 0
	await Timer(50, units="ns")
	dut.rst_n.value = 1
	await RisingEdge(dut.clk)

	# make sure inputs are zero
	dut.i_u_coord.value = 0
	dut.i_v_coord.value = 0
	dut.i_req_valid.value = 0
	await RisingEdge(dut.clk)

	# pulse request low->high->low and observe registered valid
	dut.i_req_valid.value = 1
	await RisingEdge(dut.clk)

	for cycle in range(2):
		cocotb.log.info(f"Cycle {cycle}: i_req_valid={int(dut.i_req_valid.value)} o_data_valid={int(dut.o_data_valid.value)}")
		if int(dut.o_data_valid.value) == 1:
			break
		await RisingEdge(dut.clk)

	assert int(dut.o_data_valid.value) == 1, f"o_data_valid did not follow i_req_valid after two cycles (o_data_valid={int(dut.o_data_valid.value)})"

	dut.i_req_valid.value = 0
	await RisingEdge(dut.clk)
	assert int(dut.o_data_valid.value) in (0, 1), "o_data_valid has invalid value"


@cocotb.test()
async def test_random_samples(dut):
	import random

	cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

	# reset
	dut.rst_n.value = 0
	await Timer(50, units="ns")
	dut.rst_n.value = 1
	await RisingEdge(dut.clk)

	# Read parameters
	try:
		TEX_WIDTH = int(dut.TEX_WIDTH.value)
	except Exception:
		TEX_WIDTH = 256
	try:
		TEX_HEIGHT = int(dut.TEX_HEIGHT.value)
	except Exception:
		TEX_HEIGHT = 256
	try:
		CORD_WIDTH = int(dut.CORD_WIDTH.value)
	except Exception:
		CORD_WIDTH = 16
	try:
		DATA_WIDTH = int(dut.DATA_WIDTH.value)
	except Exception:
		DATA_WIDTH = 32

	TEX_DEPTH = TEX_WIDTH * TEX_HEIGHT
	width_bits = (TEX_WIDTH - 1).bit_length()
	height_bits = (TEX_HEIGHT - 1).bit_length()
	depth_bits = (TEX_DEPTH - 1).bit_length()
	mask_x = (1 << width_bits) - 1
	mask_y = (1 << height_bits) - 1
	mask_depth = (1 << depth_bits) - 1

	rng = random.Random(0xC0FFEE)

	samples = 100000
	for i in range(samples):
		u = rng.randint(0, (1 << CORD_WIDTH) - 1)
		v = rng.randint(0, (1 << CORD_WIDTH) - 1)

		# tex_x := (u * TEX_WIDTH) truncated to width_bits
		tex_x = (u * TEX_WIDTH) & mask_x
		tex_y = (v * TEX_HEIGHT) & mask_y
		addr = ((tex_y * TEX_WIDTH) + tex_x) & mask_depth

		value = rng.randint(0, (1 << DATA_WIDTH) - 1)

		# write to DUT memory (try couple access styles)
		try:
			dut.texture_mem[addr].value = value
		except Exception:
			getattr(dut, "texture_mem")[addr].value = value

		# apply coords and pulse request (same timing as earlier tests)
		dut.i_u_coord.value = u
		dut.i_v_coord.value = v
		await RisingEdge(dut.clk)

		dut.i_req_valid.value = 1
		await RisingEdge(dut.clk)
		dut.i_req_valid.value = 0
		await RisingEdge(dut.clk)

		got_valid = int(dut.o_data_valid.value)
		got = int(dut.o_texel_color.value)

		if got_valid != 1:
			raise cocotb.result.TestFailure(f"Sample {i}: expected o_data_valid=1 got {got_valid} (u={u} v={v} addr={addr})")
		if got != value:
			raise cocotb.result.TestFailure(f"Sample {i}: texel mismatch at addr {addr}: got 0x{got:08X}, expected 0x{value:08X} (u={u} v={v})")

