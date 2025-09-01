import cocotb
import random
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, Timer

async def reset_dut(dut, cycles=3):
    dut._log.info("Resetting DUT...")
    dut.i_pixel_we.value = 0
    dut.i_pixel_x.value = 0
    dut.i_pixel_y.value = 0
    dut.i_pixel_color.value = 0
    dut.rst_n.value = 0
    await Timer(1, units="ns")
    for _ in range(cycles):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    dut._log.info("Reset complete.")

async def drive_pixel(dut, x, y, color):
    dut.i_pixel_we.value = 1
    dut.i_pixel_x.value = x
    dut.i_pixel_y.value = y
    dut.i_pixel_color.value = color
    await RisingEdge(dut.clk)
    dut.i_pixel_we.value = 0

class RefFB:
    def __init__(self, dut, width, height, color_width):
        self.dut = dut
        self.width = width
        self.height = height
        self.color_width = color_width
        self.color_mask = (1 << color_width) - 1
        self.mem = [[0] * width for _ in range(height)]
        self.dut._log.info(f"Reference model initialized with size {width}x{height}.")

    def get_addr(self, x, y):
        return y * self.width + x

    def write(self, x, y, data):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.mem[y][x] = data & self.color_mask

class Coverage:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.bins = {
            "corners": set(),
            "edges": set(),
        }
        self.required_corners = {
            (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)
        }

    def update(self, x, y):
        pos = (x, y)
        if pos in self.required_corners:
            self.bins["corners"].add(pos)
        elif x == 0 or x == self.width - 1 or y == 0 or y == self.height - 1:
            self.bins["edges"].add(pos)

    def check(self):
        missing_corners = self.required_corners - self.bins["corners"]
        assert not missing_corners, f"Coverage FAILED: Missing corner writes: {missing_corners}"
        cocotb.log.info("Coverage check PASSED.")

async def monitor_and_check(dut, ref_model, coverage):
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()

        if dut.i_pixel_we.value == 1:
            assert dut.o_mem_req.value.is_resolvable, "o_mem_req is X/Z"
            assert dut.o_mem_addr.value.is_resolvable, "o_mem_addr is X/Z"
            assert dut.o_mem_wdata.value.is_resolvable, "o_mem_wdata is X/Z"

            x, y = int(dut.i_pixel_x.value), int(dut.i_pixel_y.value)
            color = int(dut.i_pixel_color.value)
            
            dut_req = int(dut.o_mem_req.value)
            dut_addr = int(dut.o_mem_addr.value)
            dut_wdata = int(dut.o_mem_wdata.value)

            assert dut_req == 1, f"Write at ({x},{y}), but o_mem_req was not asserted!"
            
            expected_addr = ref_model.get_addr(x, y)
            assert dut_addr == expected_addr, \
                f"Address mismatch at ({x},{y}): DUT addr={dut_addr}, EXP addr={expected_addr}"
            
            assert dut_wdata == color, \
                f"Data mismatch at ({x},{y}): DUT wdata={dut_wdata}, EXP wdata={color}"

            ref_model.write(x, y, color)
            coverage.update(x, y)

@cocotb.test(timeout_time=500, timeout_unit="us")
async def test_framebuffer_comprehensive(dut):
    width = int(dut.SCREEN_WIDTH.value)
    height = int(dut.SCREEN_HEIGHT.value)
    color_width = int(dut.COLOR_WIDTH.value)
    color_mask = (1 << color_width) - 1
    
    num_iters = int(os.getenv("FB_ITERS", 20000))
    seed = int(os.getenv("FB_SEED", 1337))
    random.seed(seed)

    ref_model = RefFB(dut, width, height, color_width)
    coverage = Coverage(width, height)
    
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    monitor_task = cocotb.start_soon(monitor_and_check(dut, ref_model, coverage))
    
    await reset_dut(dut)

    dut._log.info("Starting directed tests...")
    await drive_pixel(dut, 0, 0, 0xAAAAAAAA)
    await drive_pixel(dut, width - 1, 0, 0xBBBBBBBB)
    await drive_pixel(dut, 0, height - 1, 0xCCCCCCCC)
    await drive_pixel(dut, width - 1, height - 1, 0xDDDDDDDD)
    await drive_pixel(dut, width // 2, height // 2, 0x12345678)
    await drive_pixel(dut, 10, 10, 0xDEADBEEF)
    await drive_pixel(dut, 10, 10, 0xCAFEF00D)
    
    await RisingEdge(dut.clk)
    assert ref_model.mem[10][10] == 0xCAFEF00D, "Overwrite test failed in reference model."
    dut._log.info("Directed tests passed.")

    dut._log.info(f"Starting random stress test with {num_iters} writes (seed={seed})...")
    for _ in range(num_iters):
        rand_x = random.randint(0, width - 1)
        rand_y = random.randint(0, height - 1)
        rand_color = random.randint(0, color_mask)
        await drive_pixel(dut, rand_x, rand_y, rand_color)

    await RisingEdge(dut.clk)
    dut._log.info("Random stress test finished.")
    
    coverage.check()
    monitor_task.kill()
    dut._log.info("All tests passed.")
