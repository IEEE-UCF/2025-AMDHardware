import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer
import random
import numpy as np

CLK_PERIOD = 10

class AluOpcodes:
    ADD  = 0b00001  # Add
    SUB  = 0b00010  # Subtract
    MUL  = 0b00011  # Multiply
    AND  = 0b01001  # Bitwise AND
    OR   = 0b01010  # Bitwise OR
    XOR  = 0b01011  # Bitwise XOR
    MOVA = 0b10001  # Move operand A
    MOVB = 0b10010  # Move operand B
    NOP  = 0b00000  # No operation (returns 0)

class ShaderCoreMonitor:
    def __init__(self, dut):
        self.dut = dut
        self.operations = []
        self.pipeline_state = []
        self.register_writes = {}
        self.hazards_detected = []
        
    def record_operation(self, cycle, opcode, rd, rs1, rs2):
        op_record = {
            'cycle': cycle,
            'opcode': opcode,
            'rd': rd,
            'rs1': rs1,
            'rs2': rs2
        }
        self.operations.append(op_record)
        
        if len(self.operations) >= 2:
            prev_op = self.operations[-2]
            if prev_op['rd'] in [rs1, rs2] and prev_op['rd'] != 0:
                self.hazards_detected.append({
                    'type': 'RAW',
                    'cycle': cycle,
                    'register': prev_op['rd']
                })
    
    def get_statistics(self):
        return {
            'total_operations': len(self.operations),
            'unique_opcodes': len(set(op['opcode'] for op in self.operations)),
            'hazards_detected': len(self.hazards_detected),
            'register_utilization': len(self.register_writes)
        }

async def initialize_dut(dut):
    dut.i_exec_en.value = 0
    dut.i_opcode.value = AluOpcodes.NOP
    dut.i_rd_addr.value = 0
    dut.i_rs1_addr.value = 0
    dut.i_rs2_addr.value = 0
    dut.i_mem_ready.value = 1

async def reset_dut(dut):
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

async def execute_instruction(dut, opcode, rd, rs1, rs2, wait_cycles=2):
    dut.i_opcode.value = opcode
    dut.i_rd_addr.value = rd
    dut.i_rs1_addr.value = rs1
    dut.i_rs2_addr.value = rs2
    dut.i_exec_en.value = 1
    
    await RisingEdge(dut.clk)
    dut.i_exec_en.value = 0
    
    await ClockCycles(dut.clk, wait_cycles)

def calculate_expected_result(opcode, val_a, val_b, data_width=32):
    mask = (1 << data_width) - 1
    
    if opcode == AluOpcodes.ADD:
        return (val_a + val_b) & mask
    elif opcode == AluOpcodes.SUB:
        return (val_a - val_b) & mask
    elif opcode == AluOpcodes.MUL:
        return (val_a * val_b) & mask
    elif opcode == AluOpcodes.AND:
        return val_a & val_b
    elif opcode == AluOpcodes.OR:
        return val_a | val_b
    elif opcode == AluOpcodes.XOR:
        return val_a ^ val_b
    elif opcode == AluOpcodes.MOVA:
        return val_a
    elif opcode == AluOpcodes.MOVB:
        return val_b
    else:
        return 0

def pack_vector(vec, data_width=32):
    packed = 0
    for i, val in enumerate(vec):
        packed |= (val & ((1 << data_width) - 1)) << (i * data_width)
    return packed

def unpack_vector(packed, vec_size=4, data_width=32):
    mask = (1 << data_width) - 1
    return [(packed >> (i * data_width)) & mask for i in range(vec_size)]

@cocotb.test()
async def test_shader_core_basic(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    data_width = int(dut.DATA_WIDTH.value)
    vec_size = int(dut.VEC_SIZE.value)
    num_regs = int(dut.NUM_REGS.value)
    
    dut._log.info(f"Starting shader core test (DATA_WIDTH={data_width}, VEC_SIZE={vec_size}, NUM_REGS={num_regs})")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    monitor = ShaderCoreMonitor(dut)
    
    dut._log.info("Test 1: Basic arithmetic operations")
    
    test_vectors = [
        (AluOpcodes.ADD, 1, 2, 3, "ADD: r1 = r2 + r3"),
        (AluOpcodes.SUB, 4, 1, 3, "SUB: r4 = r1 - r3"),
        (AluOpcodes.MUL, 5, 1, 4, "MUL: r5 = r1 * r4"),
        (AluOpcodes.AND, 6, 2, 3, "AND: r6 = r2 & r3"),
        (AluOpcodes.OR,  7, 2, 3, "OR:  r7 = r2 | r3"),
        (AluOpcodes.XOR, 8, 6, 7, "XOR: r8 = r6 ^ r7"),
    ]
    
    for opcode, rd, rs1, rs2, desc in test_vectors:
        dut._log.info(f"  Executing: {desc}")
        monitor.record_operation(cocotb.simulator.get_sim_time(), opcode, rd, rs1, rs2)
        await execute_instruction(dut, opcode, rd, rs1, rs2)
    
    dut._log.info("Test 2: Pipeline behavior - back-to-back operations")
    
    for i in range(5):
        dut.i_opcode.value = AluOpcodes.ADD
        dut.i_rd_addr.value = (i + 1) % num_regs
        dut.i_rs1_addr.value = i % num_regs
        dut.i_rs2_addr.value = (i + 2) % num_regs
        dut.i_exec_en.value = 1
        await RisingEdge(dut.clk)
        monitor.record_operation(cocotb.simulator.get_sim_time(), AluOpcodes.ADD, 
                                (i + 1) % num_regs, i % num_regs, (i + 2) % num_regs)
    
    dut.i_exec_en.value = 0
    await ClockCycles(dut.clk, 3)
    
    dut._log.info("Test 3: Data hazard scenarios")
    
    await execute_instruction(dut, AluOpcodes.ADD, 1, 2, 3)
    await execute_instruction(dut, AluOpcodes.SUB, 4, 1, 2)
    
    dut._log.info("Test 4: Writeback timing verification")
    
    dut.i_opcode.value = AluOpcodes.ADD
    dut.i_rd_addr.value = 9
    dut.i_rs1_addr.value = 0
    dut.i_rs2_addr.value = 0
    dut.i_exec_en.value = 1
    
    await RisingEdge(dut.clk)
    assert dut.reg_write_en.value == 0, "Write enable should not be active immediately"
    
    dut.i_exec_en.value = 0
    await RisingEdge(dut.clk)
    assert dut.reg_write_en.value == 1, "Write enable should be active one cycle later"
    
    await RisingEdge(dut.clk)
    assert dut.reg_write_en.value == 0, "Write enable should be deasserted"
    
    stats = monitor.get_statistics()
    dut._log.info(f"Test statistics: {stats}")
    
    dut._log.info("Basic shader core test passed!")

@cocotb.test()
async def test_shader_core_vector_ops(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    vec_size = int(dut.VEC_SIZE.value)
    data_width = int(dut.DATA_WIDTH.value)
    
    dut._log.info(f"Testing vector operations (VEC_SIZE={vec_size})")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    # Test vector-wide operations
    vector_ops = [
        (AluOpcodes.ADD, "Vector ADD"),
        (AluOpcodes.MUL, "Vector MUL"),
        (AluOpcodes.AND, "Vector AND"),
        (AluOpcodes.OR, "Vector OR"),
        (AluOpcodes.XOR, "Vector XOR"),
        (AluOpcodes.MOVA, "Vector MOVA"),
    ]
    
    for opcode, desc in vector_ops:
        dut._log.info(f"Testing {desc}")
        await execute_instruction(dut, opcode, 1, 2, 3)
        await ClockCycles(dut.clk, 2)
    
    dut._log.info("Vector operations test passed!")

@cocotb.test()
async def test_shader_core_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    num_regs = int(dut.NUM_REGS.value)
    
    dut._log.info("Starting shader core stress test")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    monitor = ShaderCoreMonitor(dut)
    
    num_instructions = 1000
    instruction_mix = {
        AluOpcodes.ADD: 0.30,
        AluOpcodes.SUB: 0.20,
        AluOpcodes.MUL: 0.15,
        AluOpcodes.AND: 0.10,
        AluOpcodes.OR:  0.10,
        AluOpcodes.XOR: 0.10,
        AluOpcodes.MOVA: 0.025,
        AluOpcodes.MOVB: 0.025,
    }
    
    opcodes = []
    for op, weight in instruction_mix.items():
        opcodes.extend([op] * int(weight * num_instructions))
    random.shuffle(opcodes)
    
    active_cycles = 0
    bubble_cycles = 0
    
    for i, opcode in enumerate(opcodes[:num_instructions]):
        rd = random.randint(1, num_regs - 1)
        rs1 = random.randint(0, num_regs - 1)
        rs2 = random.randint(0, num_regs - 1)
        
        if random.random() < 0.1:
            dut.i_exec_en.value = 0
            await RisingEdge(dut.clk)
            bubble_cycles += 1
        
        dut.i_opcode.value = opcode
        dut.i_rd_addr.value = rd
        dut.i_rs1_addr.value = rs1
        dut.i_rs2_addr.value = rs2
        dut.i_exec_en.value = 1
        
        monitor.record_operation(cocotb.simulator.get_sim_time(), opcode, rd, rs1, rs2)
        
        await RisingEdge(dut.clk)
        active_cycles += 1
        
        if random.random() < 0.05:
            dut.i_exec_en.value = 0
            pause_cycles = random.randint(1, 5)
            await ClockCycles(dut.clk, pause_cycles)
            bubble_cycles += pause_cycles
        
        if (i + 1) % 100 == 0:
            dut._log.info(f"Stress test progress: {i + 1}/{num_instructions} instructions")
    
    dut.i_exec_en.value = 0
    await ClockCycles(dut.clk, 3)
    
    stats = monitor.get_statistics()
    efficiency = active_cycles / (active_cycles + bubble_cycles) * 100
    
    dut._log.info(f"Stress test completed!")
    dut._log.info(f"  Total instructions: {stats['total_operations']}")
    dut._log.info(f"  Unique opcodes used: {stats['unique_opcodes']}")
    dut._log.info(f"  Pipeline efficiency: {efficiency:.1f}%")
    dut._log.info(f"  Hazards detected: {stats['hazards_detected']}")

@cocotb.test()
async def test_shader_core_memory_interface(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing memory interface")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    dut._log.info("Test 1: Memory interface with varying ready signal")
    
    async def memory_controller():
        """Simulate memory controller with variable latency"""
        for _ in range(20):
            await RisingEdge(dut.clk)
            dut.i_mem_ready.value = random.choice([0, 1, 1, 1])  # 75% ready
    
    cocotb.start_soon(memory_controller())
    
    for i in range(10):
        await execute_instruction(dut, AluOpcodes.ADD, i % 8 + 1, 0, i % 8)
        
        if dut.o_mem_req.value == 1:
            dut._log.info(f"  Memory request detected at cycle {i}")
            while dut.i_mem_ready.value == 0:
                await RisingEdge(dut.clk)
    
    dut._log.info("Memory interface test passed!")

@cocotb.test()
async def test_shader_core_corner_cases(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    num_regs = int(dut.NUM_REGS.value)
    
    dut._log.info("Testing corner cases")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    dut._log.info("Test 1: Register 0 operations")
    await execute_instruction(dut, AluOpcodes.ADD, 0, 1, 2)
    await execute_instruction(dut, AluOpcodes.SUB, 1, 0, 2)
    
    dut._log.info("Test 2: Maximum register addresses")
    max_reg = num_regs - 1
    await execute_instruction(dut, AluOpcodes.ADD, max_reg, max_reg, max_reg)
    
    dut._log.info("Test 3: Rapid execution enable toggling")
    for i in range(10):
        dut.i_exec_en.value = i % 2
        dut.i_opcode.value = AluOpcodes.XOR
        dut.i_rd_addr.value = (i % (num_regs - 1)) + 1
        dut.i_rs1_addr.value = i % num_regs
        dut.i_rs2_addr.value = (i + 1) % num_regs
        await RisingEdge(dut.clk)
    
    dut.i_exec_en.value = 0
    await ClockCycles(dut.clk, 3)
    
    dut._log.info("Test 4: Same register for all operands")
    for reg in range(1, min(4, num_regs)):
        await execute_instruction(dut, AluOpcodes.ADD, reg, reg, reg)
    
    dut._log.info("Test 5: Invalid opcode handling")
    await execute_instruction(dut, 0b11111, 1, 2, 3)  # Invalid opcode
    await execute_instruction(dut, AluOpcodes.NOP, 1, 2, 3)  # NOP
    
    dut._log.info("Test 6: Reset during operation")
    dut.i_exec_en.value = 1
    dut.i_opcode.value = AluOpcodes.MUL
    dut.i_rd_addr.value = 5
    await RisingEdge(dut.clk)
    
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    assert dut.reg_write_en.value == 0, "Write enable should be cleared on reset"
    
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut._log.info("Corner cases test passed!")

@cocotb.test()
async def test_shader_core_performance(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Starting performance test")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    start_time = cocotb.utils.get_sim_time(units='ns')
    num_instructions = 500
    
    dut._log.info("Test 1: Maximum throughput measurement")
    
    for i in range(num_instructions):
        dut.i_exec_en.value = 1
        dut.i_opcode.value = AluOpcodes.ADD
        dut.i_rd_addr.value = (i % 15) + 1
        dut.i_rs1_addr.value = ((i + 1) % 15) + 1
        dut.i_rs2_addr.value = ((i + 2) % 15) + 1
        await RisingEdge(dut.clk)
    
    dut.i_exec_en.value = 0
    await ClockCycles(dut.clk, 2)
    
    end_time = cocotb.utils.get_sim_time(units='ns')
    elapsed_ns = end_time - start_time
    throughput = num_instructions / (elapsed_ns / 1000)  # Instructions per microsecond
    
    dut._log.info(f"  Executed {num_instructions} instructions in {elapsed_ns:.0f} ns")
    dut._log.info(f"  Throughput: {throughput:.2f} instructions/μs")
    
    dut._log.info("Test 2: Mixed instruction performance")
    
    instruction_types = [
        (AluOpcodes.ADD, "ADD", 100),
        (AluOpcodes.MUL, "MUL", 100),
        (AluOpcodes.XOR, "XOR", 100),
        (AluOpcodes.MOVA, "MOV", 100),
    ]
    
    for opcode, name, count in instruction_types:
        start_time = cocotb.utils.get_sim_time(units='ns')
        
        for i in range(count):
            dut.i_exec_en.value = 1
            dut.i_opcode.value = opcode
            dut.i_rd_addr.value = (i % 15) + 1
            dut.i_rs1_addr.value = ((i * 2) % 15) + 1
            dut.i_rs2_addr.value = ((i * 3) % 15) + 1
            await RisingEdge(dut.clk)
        
        dut.i_exec_en.value = 0
        await ClockCycles(dut.clk, 2)
        
        end_time = cocotb.utils.get_sim_time(units='ns')
        elapsed_ns = end_time - start_time
        ops_per_us = count / (elapsed_ns / 1000)
        
        dut._log.info(f"  {name}: {ops_per_us:.2f} ops/μs")
    
    dut._log.info("Performance test completed!")

# Helper test for debugging
@cocotb.test(skip=False)
async def test_shader_core_debug(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Debug test - manual signal inspection")
    
    await initialize_dut(dut)
    await reset_dut(dut)
    
    test_sequence = [
        (AluOpcodes.ADD, 1, 0, 0, "Initialize r1"),
        (AluOpcodes.ADD, 2, 1, 1, "r2 = r1 + r1"),
        (AluOpcodes.MUL, 3, 2, 1, "r3 = r2 * r1"),
        (AluOpcodes.SUB, 4, 3, 2, "r4 = r3 - r2"),
    ]
    
    for opcode, rd, rs1, rs2, comment in test_sequence:
        dut._log.info(f"  {comment}")
        await execute_instruction(dut, opcode, rd, rs1, rs2)
        
        dut._log.info(f"    exec_en={dut.i_exec_en.value}, write_en={dut.reg_write_en.value}")
    
    await ClockCycles(dut.clk, 5)
    
    dut._log.info("Debug test completed - check waveforms for details")
