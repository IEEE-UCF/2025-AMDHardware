import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles
from cocotb.result import TestFailure
import random

# RISC-V instruction patterns for realistic testing
NOP    = 0x00000013  # ADDI x0, x0, 0
ADD_1  = 0x00100093  # ADDI x1, x0, 1
ADD_2  = 0x00200113  # ADDI x2, x0, 2
ADD_3  = 0x00300193  # ADDI x3, x0, 3
ADD_4  = 0x00400213  # ADDI x4, x0, 4
ADD_5  = 0x00500293  # ADDI x5, x0, 5
LOAD   = 0x00002303  # LW x6, 0(x0)
STORE  = 0x00602023  # SW x6, 0(x0)
BRANCH = 0x00108063  # BEQ x1, x1, 0
JUMP   = 0x0000006F  # JAL x0, 0

test_patterns = [
    NOP, ADD_1, ADD_2, ADD_3, ADD_4, ADD_5, LOAD, STORE,
    BRANCH, JUMP, 0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0x9ABCDEF0
]

async def reset_dut(dut):
    """Reset the DUT"""
    dut.rst_n.value = 0
    dut.write_en.value = 0
    dut.read_en.value = 0
    dut.data_in.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

async def write_instruction(dut, instruction):
    """Write a single instruction to the buffer"""
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    dut.data_in.value = instruction
    await RisingEdge(dut.clk)
    dut.write_en.value = 0

async def read_instruction(dut):
    """Read a single instruction from the buffer"""
    await RisingEdge(dut.clk)
    dut.read_en.value = 1
    await RisingEdge(dut.clk)
    dut.read_en.value = 0

async def write_read_simultaneous(dut, write_data):
    """Simultaneously write and read"""
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    dut.read_en.value = 1
    dut.data_in.value = write_data
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    dut.read_en.value = 0

@cocotb.test()
async def test_reset(dut):
    """Test 1: Reset behavior"""
    dut._log.info("Test 1: Reset behavior")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Check initial state
    assert dut.is_empty.value == 1, "Buffer should be empty after reset"
    assert dut.is_full.value == 0, "Buffer should not be full after reset"
    assert dut.data_out.value == 0, f"Output should be 0 after reset, got {hex(dut.data_out.value)}"

    dut._log.info("Reset test passed")

@cocotb.test()
async def test_simple_write_read(dut):
    """Test 2: Simple write and read operations"""
    dut._log.info("Test 2: Simple write and read operations")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Write first instruction
    await write_instruction(dut, ADD_1)
    await RisingEdge(dut.clk)

    # Check immediate availability
    assert dut.data_out.value == ADD_1, f"Expected {hex(ADD_1)}, got {hex(dut.data_out.value)}"
    assert dut.is_empty.value == 0, "Buffer should not be empty after write"

    # Read the instruction
    await read_instruction(dut)
    await RisingEdge(dut.clk) # Wait for the output and flags to update

    # Should be empty now
    assert dut.is_empty.value == 1, "Buffer should be empty after reading last instruction"

    dut._log.info("Simple write/read test passed")

@cocotb.test()
async def test_multiple_writes_reads(dut):
    """Test 3: Multiple writes followed by multiple reads"""
    dut._log.info("Test 3: Multiple writes followed by multiple reads")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Write 5 instructions
    for i in range(5):
        await write_instruction(dut, test_patterns[i])

    await RisingEdge(dut.clk)

    # Read and verify each instruction
    for i in range(5):
        assert dut.data_out.value == test_patterns[i], \
            f"Expected {hex(test_patterns[i])}, got {hex(dut.data_out.value)} at position {i}"
        await read_instruction(dut)
        await RisingEdge(dut.clk) # FIX: Wait for output to update after read

    dut._log.info("Multiple write/read test passed")

@cocotb.test()
async def test_buffer_full(dut):
    """Test 4: Fill buffer completely and verify full flag"""
    dut._log.info("Test 4: Fill buffer completely and verify full flag")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Fill the buffer (BUFFER_DEPTH = 8)
    buffer_depth = 8
    for i in range(buffer_depth):
        await write_instruction(dut, test_patterns[i])

    await RisingEdge(dut.clk)

    # Check full flag
    assert dut.is_full.value == 1, "Buffer should be full after 8 writes"
    assert dut.is_empty.value == 0, "Buffer should not be empty when full"

    # Try to write when full (should be ignored)
    await write_instruction(dut, 0xBADBAD00)
    await RisingEdge(dut.clk)

    # First instruction should still be available
    assert dut.is_full.value == 1, "Buffer should remain full"
    assert dut.data_out.value == test_patterns[0], \
        f"Output should be unchanged when writing to full buffer"

    dut._log.info("Buffer full test passed")

@cocotb.test()
async def test_stall_behavior(dut):
    """Test 5: Verify stall behavior (read_en = 0)"""
    dut._log.info("Test 5: Verify stall behavior (read_en = 0)")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Write several instructions
    for i in range(4):
        await write_instruction(dut, test_patterns[i])

    await RisingEdge(dut.clk)

    # Verify first instruction is available
    assert dut.data_out.value == test_patterns[0], "First instruction should be available"

    # Simulate stall - don't assert read_en for several cycles
    for _ in range(5):
        await RisingEdge(dut.clk)
        assert dut.data_out.value == test_patterns[0], \
            "Output should remain stable during stall"

    # Resume reading
    await read_instruction(dut)
    await RisingEdge(dut.clk) # FIX: Wait for output to update after read
    assert dut.data_out.value == test_patterns[1], \
        "Should advance to next instruction after stall"

    dut._log.info("Stall behavior test passed")

@cocotb.test()
async def test_simultaneous_read_write(dut):
    """Test 6: Simultaneous read and write operations"""
    dut._log.info("Test 6: Simultaneous read and write operations")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Fill with some initial data
    for i in range(3):
        await write_instruction(dut, test_patterns[i])

    await RisingEdge(dut.clk)

    # Simultaneous read/write
    await write_read_simultaneous(dut, 0xAAAAAAAA)
    await RisingEdge(dut.clk) # FIX: Wait for output to update after operation

    # Should have read first instruction and written new one
    assert dut.data_out.value == test_patterns[1], \
        "Should advance to next instruction after simultaneous read/write"

    dut._log.info("Simultaneous read/write test passed")

@cocotb.test()
async def test_circular_buffer(dut):
    """Test 7: Circular buffer wrap-around behavior"""
    dut._log.info("Test 7: Circular buffer wrap-around behavior")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    buffer_depth = 8

    # Fill and empty buffer multiple times to test wrap-around
    for iteration in range(3):
        # Fill buffer
        for i in range(buffer_depth):
            await write_instruction(dut, test_patterns[i] + (iteration * 0x100))
        await RisingEdge(dut.clk)

        # Empty buffer
        for i in range(buffer_depth):
            expected = test_patterns[i] + (iteration * 0x100)
            assert dut.data_out.value == expected, \
                f"Iteration {iteration}, position {i}: Expected {hex(expected)}, got {hex(dut.data_out.value)}"
            await read_instruction(dut)
            await RisingEdge(dut.clk) # FIX: Wait for output to update after read
        
        # After the loop, the last read has happened, but the empty flag is not yet updated.
        # The final RisingEdge above handles this, so the assert below is now correctly timed.
        assert dut.is_empty.value == 1, f"Buffer should be empty after iteration {iteration}"

    dut._log.info("Circular buffer test passed")

@cocotb.test()
async def test_random_operations(dut):
    """Test 8: Random sequence of operations"""
    dut._log.info("Test 8: Random sequence of operations")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Track expected buffer state using a simple list as a queue
    expected_buffer = []

    for i in range(100): # Increased iterations for better randomness
        # First, check current state against expected state
        if not expected_buffer:
            assert dut.is_empty.value == 1, f"Random[{i}]: HW should be empty, but is not"
        else:
            assert dut.data_out.value == expected_buffer[0], \
                f"Random[{i}]: Pre-op check fail. Expected {hex(expected_buffer[0])}, got {hex(dut.data_out.value)}"

        # Decide on next operation
        can_write = len(expected_buffer) < 8
        can_read = len(expected_buffer) > 0
        
        op = 'stall'
        if can_write and can_read:
            op = random.choice(['write', 'read', 'both', 'stall'])
        elif can_write:
            op = random.choice(['write', 'stall'])
        elif can_read:
            op = random.choice(['read', 'stall'])

        # Perform operation and update model
        if op == 'write':
            inst = random.choice(test_patterns)
            await write_instruction(dut, inst)
            expected_buffer.append(inst)
        elif op == 'read':
            await read_instruction(dut)
            expected_buffer.pop(0)
        elif op == 'both':
            inst = random.choice(test_patterns)
            await write_read_simultaneous(dut, inst)
            expected_buffer.pop(0)
            expected_buffer.append(inst)
        else: # stall
            pass # just wait for the clock edge at the end

        await RisingEdge(dut.clk) # Wait one cycle for all operations to settle

    dut._log.info("Random operations test passed")


@cocotb.test()
async def test_prefetch_behavior(dut):
    """Test 9: Verify standard FIFO behavior (was prefetch)"""
    dut._log.info("Test 9: Verify standard FIFO behavior")
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Write two instructions
    await write_instruction(dut, ADD_1)
    await write_instruction(dut, ADD_2)
    await RisingEdge(dut.clk)

    # First should be available
    assert dut.data_out.value == ADD_1, "First instruction should be available"

    # Read and check for next instruction
    await read_instruction(dut)
    await RisingEdge(dut.clk) # FIX: Wait for output to update after read

    # Next should now be available
    assert dut.data_out.value == ADD_2, "Second instruction should be available after reading first"

    dut._log.info("FIFO behavior test passed")