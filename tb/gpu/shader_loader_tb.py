import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer
import random

CLK_PERIOD = 10

class ShaderProgram:
    def __init__(self, size=256):
        self.instructions = []
        self.size = size
        
    def add_instruction(self, instr):
        self.instructions.append(instr)
        return self
    
    def generate_random(self, num_instructions):
        self.instructions = [random.randint(0, 0xFFFFFFFF) for _ in range(num_instructions)]
        return self
    
    def generate_pattern(self, pattern_type="sequential"):
        if pattern_type == "sequential":
            self.instructions = [i for i in range(self.size)]
        elif pattern_type == "alternating":
            self.instructions = [0xAAAAAAAA if i % 2 == 0 else 0x55555555 for i in range(self.size)]
        elif pattern_type == "address_based":
            self.instructions = [(i << 16) | i for i in range(self.size)]
        elif pattern_type == "checkered":
            self.instructions = [0xDEADBEEF if (i // 16) % 2 == 0 else 0xCAFEBABE for i in range(self.size)]
        return self

async def write_shader_program(dut, program, start_addr=0):
    for i, instr in enumerate(program.instructions):
        dut.i_host_we.value = 1
        dut.i_host_addr.value = start_addr + i
        dut.i_host_wdata.value = instr
        await RisingEdge(dut.clk)
    
    dut.i_host_we.value = 0
    await RisingEdge(dut.clk)

async def verify_shader_program(dut, program, start_addr=0):
    errors = 0
    for i, expected in enumerate(program.instructions):
        dut.i_gpu_addr.value = start_addr + i
        await Timer(1, units='ns')
        actual = int(dut.o_gpu_instr.value)
        
        if actual != expected:
            dut._log.error(f"Mismatch at addr {start_addr + i}: expected 0x{expected:08x}, got 0x{actual:08x}")
            errors += 1
    
    return errors == 0

async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.i_host_we.value = 0
    dut.i_host_addr.value = 0
    dut.i_host_wdata.value = 0
    dut.i_gpu_addr.value = 0
    
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

@cocotb.test()
async def test_shader_loader_basic(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    instr_width = int(dut.INSTR_WIDTH.value)
    instr_depth = int(dut.INSTR_DEPTH.value)
    
    dut._log.info(f"Starting shader loader test (WIDTH={instr_width}, DEPTH={instr_depth})")
    
    await reset_dut(dut)
    
    dut._log.info("Test 1: Simple write and read")
    
    test_data = [0x12345678, 0xDEADBEEF, 0xCAFEBABE, 0x87654321]
    
    for i, data in enumerate(test_data):
        dut.i_host_we.value = 1
        dut.i_host_addr.value = i
        dut.i_host_wdata.value = data
        await RisingEdge(dut.clk)
    
    dut.i_host_we.value = 0
    await RisingEdge(dut.clk)
    
    for i, expected in enumerate(test_data):
        dut.i_gpu_addr.value = i
        await Timer(1, units='ns')
        actual = int(dut.o_gpu_instr.value)
        assert actual == expected, f"Address {i}: expected 0x{expected:08x}, got 0x{actual:08x}"
    
    dut._log.info("Test 2: Overwrite existing data")
    
    new_data = 0xAAAAAAAA
    dut.i_host_we.value = 1
    dut.i_host_addr.value = 1
    dut.i_host_wdata.value = new_data
    await RisingEdge(dut.clk)
    
    dut.i_host_we.value = 0
    dut.i_gpu_addr.value = 1
    await Timer(1, units='ns')
    
    actual = int(dut.o_gpu_instr.value)
    assert actual == new_data, f"Overwrite failed: expected 0x{new_data:08x}, got 0x{actual:08x}"
    
    dut._log.info("Basic shader loader test passed!")

@cocotb.test()
async def test_shader_loader_simultaneous_access(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing simultaneous read/write access")
    
    await reset_dut(dut)
    
    program = ShaderProgram().generate_pattern("sequential")
    await write_shader_program(dut, program)
    
    dut._log.info("Performing simultaneous reads while writing")
    
    write_addr = 64
    read_addr = 32
    write_data = 0xFFFFFFFF
    
    dut.i_host_we.value = 1
    dut.i_host_addr.value = write_addr
    dut.i_host_wdata.value = write_data
    dut.i_gpu_addr.value = read_addr
    
    await Timer(1, units='ns')
    read_value = int(dut.o_gpu_instr.value)
    
    await RisingEdge(dut.clk)
    dut.i_host_we.value = 0
    
    assert read_value == read_addr, f"Read during write failed: expected {read_addr}, got {read_value}"
    
    dut.i_gpu_addr.value = write_addr
    await Timer(1, units='ns')
    assert int(dut.o_gpu_instr.value) == write_data, "Write during read failed"
    
    dut._log.info("Simultaneous access test passed!")

@cocotb.test()
async def test_shader_loader_full_memory(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    instr_depth = int(dut.INSTR_DEPTH.value)
    
    dut._log.info(f"Testing full memory write/read ({instr_depth} locations)")
    
    await reset_dut(dut)
    
    program = ShaderProgram(size=instr_depth).generate_pattern("address_based")
    
    dut._log.info("Writing full memory...")
    await write_shader_program(dut, program)
    
    dut._log.info("Verifying full memory...")
    success = await verify_shader_program(dut, program)
    
    assert success, "Full memory verification failed"
    
    dut._log.info("Full memory test passed!")

@cocotb.test()
async def test_shader_loader_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    instr_depth = int(dut.INSTR_DEPTH.value)
    
    dut._log.info("Starting shader loader stress test")
    
    await reset_dut(dut)
    
    num_operations = 5000
    write_count = 0
    read_count = 0
    memory_state = {}
    
    for op in range(num_operations):
        if random.random() < 0.3 or len(memory_state) == 0:
            addr = random.randint(0, instr_depth - 1)
            data = random.randint(0, 0xFFFFFFFF)
            
            dut.i_host_we.value = 1
            dut.i_host_addr.value = addr
            dut.i_host_wdata.value = data
            await RisingEdge(dut.clk)
            dut.i_host_we.value = 0
            
            memory_state[addr] = data
            write_count += 1
            
        else:
            addr = random.choice(list(memory_state.keys()))
            expected = memory_state[addr]
            
            dut.i_gpu_addr.value = addr
            await Timer(1, units='ns')
            actual = int(dut.o_gpu_instr.value)
            
            assert actual == expected, f"Stress test failed at addr {addr}: expected 0x{expected:08x}, got 0x{actual:08x}"
            read_count += 1
        
        if (op + 1) % 500 == 0:
            dut._log.info(f"Stress test progress: {op + 1}/{num_operations} operations")
    
    dut._log.info(f"Stress test completed! Writes: {write_count}, Reads: {read_count}")

@cocotb.test()
async def test_shader_loader_patterns(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing various data patterns")
    
    await reset_dut(dut)
    
    patterns = [
        ("All zeros", [0x00000000] * 32),
        ("All ones", [0xFFFFFFFF] * 32),
        ("Walking ones", [1 << i for i in range(32)]),
        ("Walking zeros", [~(1 << i) & 0xFFFFFFFF for i in range(32)]),
        ("Checkerboard", [0xAAAAAAAA if i % 2 == 0 else 0x55555555 for i in range(32)]),
        ("Address pattern", [(i << 24) | (i << 16) | (i << 8) | i for i in range(32)]),
    ]
    
    base_addr = 0
    
    for name, pattern in patterns:
        dut._log.info(f"  Testing pattern: {name}")
        
        for i, data in enumerate(pattern):
            dut.i_host_we.value = 1
            dut.i_host_addr.value = base_addr + i
            dut.i_host_wdata.value = data
            await RisingEdge(dut.clk)
        
        dut.i_host_we.value = 0
        
        for i, expected in enumerate(pattern):
            dut.i_gpu_addr.value = base_addr + i
            await Timer(1, units='ns')
            actual = int(dut.o_gpu_instr.value)
            assert actual == expected, f"{name} failed at offset {i}"
        
        base_addr += len(pattern)
    
    dut._log.info("Pattern test passed!")

@cocotb.test()
async def test_shader_loader_boundary(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    instr_depth = int(dut.INSTR_DEPTH.value)
    
    dut._log.info("Testing boundary conditions")
    
    await reset_dut(dut)
    
    boundary_addresses = [0, 1, instr_depth - 2, instr_depth - 1]
    
    dut._log.info("Test 1: Boundary address writes")
    for addr in boundary_addresses:
        data = 0x1000 + addr
        dut.i_host_we.value = 1
        dut.i_host_addr.value = addr
        dut.i_host_wdata.value = data
        await RisingEdge(dut.clk)
    
    dut.i_host_we.value = 0
    
    dut._log.info("Test 2: Boundary address reads")
    for addr in boundary_addresses:
        expected = 0x1000 + addr
        dut.i_gpu_addr.value = addr
        await Timer(1, units='ns')
        actual = int(dut.o_gpu_instr.value)
        assert actual == expected, f"Boundary test failed at addr {addr}"
    
    dut._log.info("Test 3: Rapid address switching")
    for _ in range(100):
        addr1 = 0
        addr2 = instr_depth - 1
        
        dut.i_gpu_addr.value = addr1
        await Timer(1, units='ns')
        val1 = int(dut.o_gpu_instr.value)
        
        dut.i_gpu_addr.value = addr2
        await Timer(1, units='ns')
        val2 = int(dut.o_gpu_instr.value)
        
        assert val1 == 0x1000, f"Rapid switch failed for addr 0"
        assert val2 == 0x1000 + instr_depth - 1, f"Rapid switch failed for max addr"
    
    dut._log.info("Boundary test passed!")

@cocotb.test()
async def test_shader_loader_pipeline_fetch(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing pipeline-style instruction fetch")
    
    await reset_dut(dut)
    
    test_program = [
        0x00000001,
        0x00000002, 
        0x00000003,
        0x00000004,
        0x00000005,
        0x00000006,
        0x00000007,
        0x00000008,
    ]
    
    for i, instr in enumerate(test_program):
        dut.i_host_we.value = 1
        dut.i_host_addr.value = i
        dut.i_host_wdata.value = instr
        await RisingEdge(dut.clk)
    
    dut.i_host_we.value = 0
    
    pc = 0
    fetched_instructions = []
    
    for _ in range(len(test_program) * 2):
        dut.i_gpu_addr.value = pc
        await Timer(1, units='ns')
        fetched = int(dut.o_gpu_instr.value)
        fetched_instructions.append(fetched)
        
        pc = (pc + 1) % len(test_program)
        await RisingEdge(dut.clk)
    
    for i in range(len(test_program)):
        assert fetched_instructions[i] == test_program[i], f"Pipeline fetch failed at PC={i}"
    
    dut._log.info("Pipeline fetch test passed!")

@cocotb.test()
async def test_shader_loader_performance(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    instr_depth = int(dut.INSTR_DEPTH.value)
    
    dut._log.info("Performance testing")
    
    await reset_dut(dut)
    
    dut._log.info("Test 1: Write throughput")
    start_time = cocotb.utils.get_sim_time(units='ns')
    
    for addr in range(min(256, instr_depth)):
        dut.i_host_we.value = 1
        dut.i_host_addr.value = addr
        dut.i_host_wdata.value = addr
        await RisingEdge(dut.clk)
    
    dut.i_host_we.value = 0
    
    end_time = cocotb.utils.get_sim_time(units='ns')
    elapsed_ns = end_time - start_time
    writes_per_us = 256 / (elapsed_ns / 1000)
    
    dut._log.info(f"  Write throughput: {writes_per_us:.2f} writes/μs")
    
    dut._log.info("Test 2: Read latency")
    
    latencies = []
    for _ in range(100):
        addr = random.randint(0, min(255, instr_depth - 1))
        
        start_time = cocotb.utils.get_sim_time(units='ns')
        dut.i_gpu_addr.value = addr
        await Timer(1, units='ns')
        read_value = int(dut.o_gpu_instr.value)
        end_time = cocotb.utils.get_sim_time(units='ns')
        
        latencies.append(end_time - start_time)
    
    avg_latency = sum(latencies) / len(latencies)
    dut._log.info(f"  Average read latency: {avg_latency:.2f} ns")
    
    dut._log.info("Test 3: Back-to-back read performance")
    
    start_time = cocotb.utils.get_sim_time(units='ns')
    
    for i in range(1000):
        dut.i_gpu_addr.value = i % min(256, instr_depth)
        await Timer(1, units='ns')
    
    end_time = cocotb.utils.get_sim_time(units='ns')
    elapsed_ns = end_time - start_time
    reads_per_us = 1000 / (elapsed_ns / 1000)
    
    dut._log.info(f"  Read throughput: {reads_per_us:.2f} reads/μs")
    
    dut._log.info("Performance test completed!")