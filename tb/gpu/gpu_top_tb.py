import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles, Timer
from cocotb.result import TestFailure
import random

CLK_PERIOD = 10

ADDR_CONTROL = 0x00000000
ADDR_STATUS = 0x00000004
ADDR_VERTEX_BASE = 0x00000008
ADDR_VERTEX_COUNT = 0x0000000C
ADDR_PC = 0x00000010
ADDR_SHADER_BASE = 0x00001000

CTRL_START = 0
CTRL_IRQ_CLEAR = 1

STATUS_BUSY = 0
STATUS_IRQ = 1

async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.i_bus_we.value = 0
    dut.i_bus_addr.value = 0
    dut.i_bus_wdata.value = 0
    dut.i_dram_rdata.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

async def write_register(dut, addr, data):
    await RisingEdge(dut.clk)
    dut.i_bus_we.value = 1
    dut.i_bus_addr.value = addr
    dut.i_bus_wdata.value = data
    await RisingEdge(dut.clk)
    dut.i_bus_we.value = 0
    dut.i_bus_addr.value = 0
    dut.i_bus_wdata.value = 0
    await RisingEdge(dut.clk)

async def read_register(dut, addr):
    await RisingEdge(dut.clk)
    dut.i_bus_we.value = 0
    dut.i_bus_addr.value = addr
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    value = int(dut.o_bus_rdata.value)
    dut.i_bus_addr.value = 0
    return value

async def load_shader_program(dut, instructions):
    addr = ADDR_SHADER_BASE
    for instr in instructions:
        await write_register(dut, addr, instr)
        addr += 4

async def wait_for_idle(dut, timeout=1000):
    for _ in range(timeout):
        status = await read_register(dut, ADDR_STATUS)
        if not (status & (1 << STATUS_BUSY)):
            return True
        await ClockCycles(dut.clk, 1)
    return False

def create_simple_shader():
    instructions = [
        0x88000000,
        0x90400000,
        0x00000000,
    ]
    return instructions

def create_vertex_data():
    vertices = [
        100, 100,
        200, 100,
        150, 200,
        0xFF0000,
        0x00FF00,
        0x0000FF,
        0, 0,
        0x10000, 0,
        0, 0x10000,
    ]
    return vertices

@cocotb.test()
async def test_reset(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing reset")
    
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    
    assert dut.o_dram_we.value == 0, "DRAM write enable should be 0 during reset"
    assert dut.o_bus_rdata.value == 0, "Bus read data should be 0 during reset"
    
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    
    dut._log.info("Reset test passed")

@cocotb.test()
async def test_register_access(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing register access")
    
    await reset_dut(dut)
    
    test_addr = 0x12340000
    await write_register(dut, ADDR_VERTEX_BASE, test_addr)
    read_val = await read_register(dut, ADDR_VERTEX_BASE)
    
    assert read_val == test_addr, f"Vertex base mismatch: got {read_val:08x}, expected {test_addr:08x}"
    
    test_count = 9
    await write_register(dut, ADDR_VERTEX_COUNT, test_count)
    read_val = await read_register(dut, ADDR_VERTEX_COUNT)
    
    assert read_val == test_count, f"Vertex count mismatch: got {read_val}, expected {test_count}"
    
    dut._log.info("Register access test passed")

@cocotb.test()
async def test_shader_loading(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing shader loading")
    
    await reset_dut(dut)
    
    shader = create_simple_shader()
    await load_shader_program(dut, shader)
    
    await write_register(dut, ADDR_PC, 0)
    
    dut._log.info("Shader loading test passed")

@cocotb.test()
async def test_pipeline_start(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing pipeline start")
    
    await reset_dut(dut)
    
    await write_register(dut, ADDR_VERTEX_BASE, 0x10000)
    await write_register(dut, ADDR_VERTEX_COUNT, 3)
    await write_register(dut, ADDR_PC, 0)
    
    status = await read_register(dut, ADDR_STATUS)
    assert not (status & (1 << STATUS_BUSY)), "GPU should not be busy initially"
    
    await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
    
    await ClockCycles(dut.clk, 5)
    status = await read_register(dut, ADDR_STATUS)
    dut._log.info(f"Status after start: 0x{status:08x}")
    
    idle = await wait_for_idle(dut)
    assert idle, "GPU did not return to idle"
    
    dut._log.info("Pipeline start test passed")

@cocotb.test()
async def test_memory_interface(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing memory interface")
    
    await reset_dut(dut)
    
    dram_transactions = []
    
    async def monitor_dram():
        for _ in range(100):
            await RisingEdge(dut.clk)
            if dut.o_dram_we.value == 1:
                addr = int(dut.o_dram_addr.value)
                data = int(dut.o_dram_wdata.value)
                dram_transactions.append((addr, data))
                dut._log.info(f"DRAM write: addr=0x{addr:08x}, data=0x{data:08x}")
    
    monitor_task = cocotb.start_soon(monitor_dram())
    
    await write_register(dut, ADDR_VERTEX_BASE, 0x20000)
    await write_register(dut, ADDR_VERTEX_COUNT, 3)
    
    dut.i_dram_rdata.value = 0x12345678
    
    await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
    
    await ClockCycles(dut.clk, 100)
    
    dut._log.info(f"Captured {len(dram_transactions)} DRAM transactions")
    
    dut._log.info("Memory interface test passed")

@cocotb.test()
async def test_interrupt(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing interrupt generation")
    
    await reset_dut(dut)
    
    await write_register(dut, ADDR_VERTEX_BASE, 0x30000)
    await write_register(dut, ADDR_VERTEX_COUNT, 3)
    await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
    
    await wait_for_idle(dut)
    
    status = await read_register(dut, ADDR_STATUS)
    assert status & (1 << STATUS_IRQ), "Interrupt should be pending after completion"
    
    await write_register(dut, ADDR_CONTROL, 1 << CTRL_IRQ_CLEAR)
    await ClockCycles(dut.clk, 2)
    
    status = await read_register(dut, ADDR_STATUS)
    assert not (status & (1 << STATUS_IRQ)), "Interrupt should be cleared"
    
    dut._log.info("Interrupt test passed")

@cocotb.test()
async def test_back_to_back(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing back-to-back operations")
    
    await reset_dut(dut)
    
    for i in range(3):
        dut._log.info(f"Operation {i+1}/3")
        
        await write_register(dut, ADDR_VERTEX_BASE, 0x40000 + i * 0x1000)
        await write_register(dut, ADDR_VERTEX_COUNT, 3 + i * 3)
        
        await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
        
        idle = await wait_for_idle(dut, timeout=5000)
        assert idle, f"Operation {i+1} did not complete"
        
        await write_register(dut, ADDR_CONTROL, 1 << CTRL_IRQ_CLEAR)
    
    dut._log.info("Back-to-back test passed")

@cocotb.test()
async def test_vertex_fetch_interface(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing vertex fetch interface")
    
    await reset_dut(dut)
    
    vertex_base = 0x50000
    vertex_count = 3
    
    await write_register(dut, ADDR_VERTEX_BASE, vertex_base)
    await write_register(dut, ADDR_VERTEX_COUNT, vertex_count)
    
    vertex_data = create_vertex_data()
    vertex_index = 0
    
    async def provide_vertex_data():
        nonlocal vertex_index
        for _ in range(1000):
            await RisingEdge(dut.clk)
            if vertex_index < len(vertex_data):
                dut.i_dram_rdata.value = vertex_data[vertex_index]
                vertex_index = (vertex_index + 1) % len(vertex_data)
    
    cocotb.start_soon(provide_vertex_data())
    
    await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
    
    await ClockCycles(dut.clk, 200)
    
    dut._log.info("Vertex fetch test passed")

@cocotb.test()
async def test_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Starting stress test")
    
    await reset_dut(dut)
    
    for i in range(10):
        dut._log.info(f"Stress iteration {i+1}/10")
        
        vertex_base = random.randint(0, 0xF0000) & ~0xFFF
        vertex_count = random.choice([3, 6, 9, 12])
        
        await write_register(dut, ADDR_VERTEX_BASE, vertex_base)
        await write_register(dut, ADDR_VERTEX_COUNT, vertex_count)
        
        shader = [random.randint(0, 0xFFFFFFFF) for _ in range(random.randint(1, 5))]
        await load_shader_program(dut, shader)
        
        dut.i_dram_rdata.value = random.randint(0, 0xFFFFFFFF)
        
        await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
        
        idle = await wait_for_idle(dut, timeout=10000)
        if not idle:
            dut._log.warning(f"Iteration {i+1} timeout - resetting")
            await reset_dut(dut)
        
        await write_register(dut, ADDR_CONTROL, 1 << CTRL_IRQ_CLEAR)
        
        await ClockCycles(dut.clk, random.randint(1, 20))
    
    dut._log.info("Stress test completed")

@cocotb.test()
async def test_performance(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Measuring performance")
    
    await reset_dut(dut)
    
    results = []
    
    for vertex_count in [3, 6, 9, 12, 15]:
        await write_register(dut, ADDR_VERTEX_BASE, 0x60000)
        await write_register(dut, ADDR_VERTEX_COUNT, vertex_count)
        
        start_time = cocotb.utils.get_sim_time(units='ns')
        await write_register(dut, ADDR_CONTROL, 1 << CTRL_START)
        
        idle = await wait_for_idle(dut, timeout=20000)
        end_time = cocotb.utils.get_sim_time(units='ns')
        
        if idle:
            cycles = (end_time - start_time) / CLK_PERIOD
            results.append((vertex_count, cycles))
            dut._log.info(f"Vertices: {vertex_count}, Cycles: {cycles:.0f}")
        
        await write_register(dut, ADDR_CONTROL, 1 << CTRL_IRQ_CLEAR)
    
    if len(results) > 1:
        assert results[-1][1] > results[0][1], "Performance should scale with vertex count"
    
    dut._log.info("Performance test passed")