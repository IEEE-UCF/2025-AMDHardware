import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles


async def reset_dut(dut):
    """Reset DUT and initialize all inputs"""
    dut.rst_n.value = 0
    dut.imem_addr.value = 0
    dut.imem_read.value = 0
    dut.dmem_addr.value = 0
    dut.dmem_write_data.value = 0
    dut.dmem_read.value = 0
    dut.dmem_write.value = 0
    dut.dmem_byte_enable.value = 0
    dut.cache_flush.value = 0
    dut.cache_invalidate.value = 0

    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


# Helper routines ---------------------------------------------------------


async def imem_fetch(dut, addr):
    """Fetch instruction from memory"""
    dut.imem_addr.value = addr
    dut.imem_read.value = 1
    await RisingEdge(dut.clk)

    # Wait for ready signal
    cycles = 0
    while dut.imem_ready.value.integer != 1:
        await RisingEdge(dut.clk)
        cycles += 1
        assert cycles < 10, f"Timeout waiting for imem_ready at addr {hex(addr)}"

    data = dut.imem_read_data.value.integer
    dut.imem_read.value = 0
    await RisingEdge(dut.clk)
    return data


async def dmem_write(dut, addr, data, byte_en):
    """Write data to memory"""
    dut.dmem_addr.value = addr
    dut.dmem_write_data.value = data
    dut.dmem_byte_enable.value = byte_en
    dut.dmem_write.value = 1
    await RisingEdge(dut.clk)

    # Wait for ready signal
    cycles = 0
    while dut.dmem_ready.value.integer != 1:
        await RisingEdge(dut.clk)
        cycles += 1
        assert cycles < 10, f"Timeout waiting for dmem_ready at addr {hex(addr)}"

    dut.dmem_write.value = 0
    dut.dmem_byte_enable.value = 0
    await RisingEdge(dut.clk)


async def dmem_read(dut, addr):
    """Read data from memory"""
    dut.dmem_addr.value = addr
    dut.dmem_read.value = 1
    await RisingEdge(dut.clk)

    # Wait for ready signal
    cycles = 0
    while dut.dmem_ready.value.integer != 1:
        await RisingEdge(dut.clk)
        cycles += 1
        assert cycles < 10, f"Timeout waiting for dmem_ready at addr {hex(addr)}"

    data = dut.dmem_read_data.value.integer
    dut.dmem_read.value = 0
    await RisingEdge(dut.clk)
    return data


async def flush_caches(dut, invalidate=False):
    """Flush or invalidate caches"""
    if invalidate:
        dut.cache_invalidate.value = 1
    else:
        dut.cache_flush.value = 1
    await RisingEdge(dut.clk)
    dut.cache_invalidate.value = 0
    dut.cache_flush.value = 0
    await RisingEdge(dut.clk)


# Testcases ---------------------------------------------------------------


@cocotb.test()
async def test_instruction_cache_behavior(dut):
    """Exercise instruction cache including flush/invalidate and counters"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Memory is pre-initialized in SystemVerilog
    # inst_mem[0] = 0x00000013  # NOP
    # inst_mem[1] = 0x00100093  # ADDI x1, x0, 1
    # inst_mem[2] = 0x00200113  # ADDI x2, x0, 2

    # Get initial counter value
    initial_hit_count = dut.cache_hit_count.value.integer
    initial_access_count = dut.imem_access_count.value.integer

    # First fetch - cache miss
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP (0x00000013), got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count, (
        "Should be a cache miss"
    )
    assert dut.imem_access_count.value.integer == initial_access_count + 1

    # Second fetch of same address - cache hit
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP (0x00000013), got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 1, (
        "Should be a cache hit"
    )
    assert dut.imem_access_count.value.integer == initial_access_count + 2

    # Fetch different address - cache miss
    data = await imem_fetch(dut, 4)
    assert data == 0x00100093, f"Expected ADDI (0x00100093), got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 1, (
        "Should be a cache miss"
    )
    assert dut.imem_access_count.value.integer == initial_access_count + 3

    # Fetch same address again - cache hit
    data = await imem_fetch(dut, 4)
    assert data == 0x00100093, f"Expected ADDI (0x00100093), got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 2, (
        "Should be a cache hit"
    )
    assert dut.imem_access_count.value.integer == initial_access_count + 4

    # Invalidate cache
    await flush_caches(dut, invalidate=True)

    # Fetch after invalidate - cache miss
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP (0x00000013), got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 2, (
        "Should be a cache miss after invalidate"
    )
    assert dut.imem_access_count.value.integer == initial_access_count + 5

    # Fetch again - cache hit
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP (0x00000013), got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 3, (
        "Should be a cache hit"
    )
    assert dut.imem_access_count.value.integer == initial_access_count + 6

    cocotb.log.info(
        f"Test passed: {dut.imem_access_count.value.integer - initial_access_count} accesses, "
        f"{dut.cache_hit_count.value.integer - initial_hit_count} hits"
    )


@cocotb.test()
async def test_data_memory_operations(dut):
    """Verify byte enables, cache behaviour and counter for data memory"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Get initial counter value
    initial_access_count = dut.dmem_access_count.value.integer

    # Data memory is pre-initialized with data_mem[0] = 0x89ABCDEF
    # First read - cache miss
    data = await dmem_read(dut, 0)
    assert data == 0x89ABCDEF, f"Expected 0x89ABCDEF, got {hex(data)}"
    assert dut.dmem_access_count.value.integer == initial_access_count + 1

    # Second read - cache hit
    data = await dmem_read(dut, 0)
    assert data == 0x89ABCDEF, f"Expected 0x89ABCDEF, got {hex(data)}"
    assert dut.dmem_access_count.value.integer == initial_access_count + 2

    # Full word write
    await dmem_write(dut, 4, 0xDEADBEEF, 0xF)
    assert dut.dmem_access_count.value.integer == initial_access_count + 3

    # Read back written value
    data = await dmem_read(dut, 4)
    assert data == 0xDEADBEEF, f"Expected 0xDEADBEEF, got {hex(data)}"
    assert dut.dmem_access_count.value.integer == initial_access_count + 4

    # Byte write (byte 1 only)
    await dmem_write(dut, 4, 0x0000CC00, 0b0010)
    assert dut.dmem_access_count.value.integer == initial_access_count + 5

    # Read back and verify byte write
    data = await dmem_read(dut, 4)
    assert data == 0xDEADCCEF, f"Expected 0xDEADCCEF after byte write, got {hex(data)}"
    assert dut.dmem_access_count.value.integer == initial_access_count + 6

    # Halfword write (lower half)
    await dmem_write(dut, 4, 0x000055AA, 0b0011)
    assert dut.dmem_access_count.value.integer == initial_access_count + 7

    # Read back and verify halfword write
    data = await dmem_read(dut, 4)
    assert data == 0xDEAD55AA, (
        f"Expected 0xDEAD55AA after halfword write, got {hex(data)}"
    )
    assert dut.dmem_access_count.value.integer == initial_access_count + 8

    cocotb.log.info(
        f"Test passed: {dut.dmem_access_count.value.integer - initial_access_count} data memory accesses"
    )


@cocotb.test()
async def test_cache_flush_and_concurrent_ports(dut):
    """Issue concurrent instruction/data ops and exercise flush control"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Get initial counter values
    initial_hit_count = dut.cache_hit_count.value.integer
    initial_imem_count = dut.imem_access_count.value.integer
    initial_dmem_count = dut.dmem_access_count.value.integer

    # Pre-warm the instruction cache
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP, got {hex(data)}"

    # Verify it's cached
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP, got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 1, (
        "Should have one cache hit"
    )

    # Flush caches
    await flush_caches(dut)

    # After flush, next fetch should miss
    data = await imem_fetch(dut, 0)
    assert data == 0x00000013, f"Expected NOP, got {hex(data)}"
    assert dut.cache_hit_count.value.integer == initial_hit_count + 1, (
        "Should still have only one hit (flush caused miss)"
    )

    # Do some data operations
    data = await dmem_read(dut, 0)
    assert data == 0x89ABCDEF, f"Expected 0x89ABCDEF, got {hex(data)}"

    await dmem_write(dut, 0, 0x87654321, 0xF)
    data = await dmem_read(dut, 0)
    assert data == 0x87654321, f"Expected 0x87654321, got {hex(data)}"

    final_imem_count = dut.imem_access_count.value.integer - initial_imem_count
    final_dmem_count = dut.dmem_access_count.value.integer - initial_dmem_count
    final_hit_count = dut.cache_hit_count.value.integer - initial_hit_count

    cocotb.log.info(
        f"Test passed: {final_imem_count} imem accesses, "
        f"{final_dmem_count} dmem accesses, {final_hit_count} cache hits"
    )


@cocotb.test()
async def test_out_of_range_access(dut):
    """Ensure out-of-range accesses return RV32I defaults"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Test out-of-range instruction fetch
    data = await imem_fetch(dut, 0x8000)
    assert data == 0x00000013, f"Expected NOP for out-of-range imem, got {hex(data)}"

    # Test out-of-range data read
    data = await dmem_read(dut, 0x8000)
    assert data == 0, f"Expected 0 for out-of-range dmem, got {hex(data)}"

    # Test misaligned access
    data = await imem_fetch(dut, 0x0001)  # Misaligned address
    assert data == 0x00000013, f"Expected NOP for misaligned imem, got {hex(data)}"

    data = await dmem_read(dut, 0x0003)  # Misaligned address
    assert data == 0, f"Expected 0 for misaligned dmem, got {hex(data)}"

    cocotb.log.info(
        "Test passed: Out-of-range and misaligned accesses handled correctly"
    )
