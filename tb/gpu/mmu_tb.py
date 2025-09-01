import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random

CLK_PERIOD = 10

@cocotb.test()
async def test_mmu_basic(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    addr_width = int(dut.ADDR_WIDTH.value)
    max_addr = (1 << addr_width) - 1
    
    dut._log.info(f"Starting MMU test (Address width: {addr_width} bits)")
    
    dut.rst_n.value = 0
    dut.i_base_addr.value = 0
    dut.i_bound_addr.value = 0
    dut.i_valid.value = 0
    dut.i_virtual_addr.value = 0
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    dut._log.info("Test 1: Basic address translation")
    base_addr = 0x1000
    bound_addr = 0x800
    
    dut.i_base_addr.value = base_addr
    dut.i_bound_addr.value = bound_addr
    await RisingEdge(dut.clk)
    
    virtual_addr = 0x100
    dut.i_virtual_addr.value = virtual_addr
    dut.i_valid.value = 1
    await RisingEdge(dut.clk)
    
    expected_physical = base_addr + virtual_addr
    physical_addr = int(dut.o_physical_addr.value)
    valid = int(dut.o_valid.value)
    error = int(dut.o_error.value)
    
    dut._log.info(f"Virtual: 0x{virtual_addr:x}, Physical: 0x{physical_addr:x}, Expected: 0x{expected_physical:x}")
    
    assert physical_addr == expected_physical, f"Address translation failed: got 0x{physical_addr:x}, expected 0x{expected_physical:x}"
    assert valid == 1, "Valid signal should be high for valid access"
    assert error == 0, "Error signal should be low for valid access"
    
    dut._log.info("Test 2: Boundary conditions")
    
    virtual_addr = bound_addr - 1
    dut.i_virtual_addr.value = virtual_addr
    await RisingEdge(dut.clk)
    
    physical_addr = int(dut.o_physical_addr.value)
    valid = int(dut.o_valid.value)
    error = int(dut.o_error.value)
    
    dut._log.info(f"Boundary test: Virtual: 0x{virtual_addr:x}, Error: {error}")
    assert error == 0, "Access within bounds should not generate error"
    assert valid == 1, "Access within bounds should be valid"
    
    virtual_addr = bound_addr
    dut.i_virtual_addr.value = virtual_addr
    await RisingEdge(dut.clk)
    
    error = int(dut.o_error.value)
    valid = int(dut.o_valid.value)
    
    dut._log.info(f"Boundary violation: Virtual: 0x{virtual_addr:x}, Error: {error}")
    assert error == 1, "Access at boundary should generate error"
    assert valid == 0, "Access with error should not be valid"
    
    dut._log.info("Test 3: Out of bounds access")
    
    virtual_addr = bound_addr + 0x100
    dut.i_virtual_addr.value = virtual_addr
    await RisingEdge(dut.clk)
    
    error = int(dut.o_error.value)
    valid = int(dut.o_valid.value)
    
    assert error == 1, "Out of bounds access should generate error"
    assert valid == 0, "Out of bounds access should not be valid"
    
    dut._log.info("Test 4: Invalid input handling")
    
    virtual_addr = 0x100
    dut.i_virtual_addr.value = virtual_addr
    dut.i_valid.value = 0
    await RisingEdge(dut.clk)
    
    valid = int(dut.o_valid.value)
    assert valid == 0, "Output should be invalid when input is invalid"
    
    dut._log.info("Basic MMU test passed!")

@cocotb.test()
async def test_mmu_complex_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    addr_width = int(dut.ADDR_WIDTH.value)
    max_addr = (1 << addr_width) - 1
    
    dut._log.info("Starting complex MMU stress test")
    
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    current_base = 0
    current_bound = 0
    config_pending = False
    pending_base = 0
    pending_bound = 0
    
    errors = 0
    valid_accesses = 0
    boundary_hits = 0
    overflows = 0
    
    for i in range(2000):
        
        config_change = False
        if i == 0:
            config_change = True
        elif i < 100:
            config_change = random.random() < 0.3
        elif i < 500:
            config_change = random.random() < 0.1  
        else:
            config_change = random.random() < 0.05
            
        if config_change:
            pending_base = random.randint(0, max_addr // 2)
            pending_bound = random.randint(0x1000, max_addr // 2)
            config_pending = True
            
            dut.i_base_addr.value = pending_base
            dut.i_bound_addr.value = pending_bound
            
        await RisingEdge(dut.clk)
        
        if config_pending:
            current_base = pending_base
            current_bound = pending_bound
            config_pending = False
        
        if i < 50:
            virtual_addr = random.randint(0, 0x1000)
        else:
            virtual_addr = random.randint(0, max_addr // 2)
            
        if i % 13 == 0:
            valid_input = 0
        else:
            valid_input = 1
            
        burst_size = 1
        if random.random() < 0.1:
            burst_size = random.randint(2, 5)
            
        for burst in range(burst_size):
            if burst > 0:
                virtual_addr = (virtual_addr + random.randint(-0x100, 0x100)) & (max_addr // 2)
            
            dut.i_virtual_addr.value = virtual_addr
            dut.i_valid.value = valid_input
            await RisingEdge(dut.clk)
            
            physical_addr = int(dut.o_physical_addr.value)
            error = int(dut.o_error.value)
            valid_output = int(dut.o_valid.value)
            
            expected_physical = (current_base + virtual_addr) % (1 << addr_width)
            expected_error = 1 if virtual_addr >= current_bound else 0
            expected_valid = valid_input and not expected_error
            
            if virtual_addr >= current_bound:
                errors += 1
                if abs(virtual_addr - current_bound) < 16:
                    boundary_hits += 1
                    
            if valid_output:
                valid_accesses += 1
                
            if (current_base + virtual_addr) >= (1 << addr_width):
                overflows += 1
            
            if physical_addr != expected_physical:
                dut._log.error(f"Cycle {i}.{burst}: Physical address mismatch")
                dut._log.error(f"  current_base: 0x{current_base:08x}")
                dut._log.error(f"  virtual_addr: 0x{virtual_addr:08x}")
                dut._log.error(f"  sum: 0x{current_base + virtual_addr:08x}")
                dut._log.error(f"  expected: 0x{expected_physical:08x}")
                dut._log.error(f"  actual:   0x{physical_addr:08x}")
                dut._log.error(f"  diff: {physical_addr - expected_physical}")
                
            assert physical_addr == expected_physical, \
                f"Cycle {i}.{burst}: Physical mismatch - base=0x{current_base:x}, virtual=0x{virtual_addr:x}"
                
            assert error == expected_error, \
                f"Cycle {i}.{burst}: Error mismatch - virtual=0x{virtual_addr:x}, bound=0x{current_bound:x}"
                
            assert valid_output == expected_valid, \
                f"Cycle {i}.{burst}: Valid mismatch"
        
        if (i + 1) % 400 == 0:
            dut._log.info(f"Complex stress: {i + 1}/2000 cycles")
            dut._log.info(f"  Stats: errors={errors}, valid={valid_accesses}, boundaries={boundary_hits}, overflows={overflows}")
    
    dut._log.info(f"Complex stress test passed!")
    dut._log.info(f"Final stats - Errors: {errors}, Valid: {valid_accesses}")
    dut._log.info(f"Boundary hits: {boundary_hits}, Overflows: {overflows}")
    dut._log.info(f"Error rate: {100*errors/2000:.1f}%, Valid rate: {100*valid_accesses/2000:.1f}%")

@cocotb.test()
async def test_mmu_directed_edges(dut):
    from cocotb.clock import Clock
    from cocotb.triggers import RisingEdge
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    dut.i_valid.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    def load_cfg(base, bound):
        dut.i_base_addr.value = base
        dut.i_bound_addr.value = bound
        return RisingEdge(dut.clk)

    await load_cfg(0x2000_0000, 0x1000)
    for virt, exp_err in [(0x0FFE,0),(0x0FFF,0),(0x1000,1),(0x1001,1)]:
        dut.i_virtual_addr.value = virt
        dut.i_valid.value = 1
        await RisingEdge(dut.clk)
        assert int(dut.o_error.value) == exp_err
        assert int(dut.o_valid.value) == (0 if exp_err else 1)

    await load_cfg(0x1000_0000, 0x0)
    for virt in [0x0, 0x1, 0x123]:
        dut.i_virtual_addr.value = virt
        dut.i_valid.value = 1
        await RisingEdge(dut.clk)
        assert int(dut.o_error.value) == 1
        assert int(dut.o_valid.value) == 0

    await load_cfg(0x3000_0000, 0x1)
    for virt, exp_valid in [(0x0,1),(0x1,0),(0x2,0)]:
        dut.i_virtual_addr.value = virt
        dut.i_valid.value = 1
        await RisingEdge(dut.clk)
        assert int(dut.o_valid.value) == exp_valid

    addr_w = int(dut.ADDR_WIDTH.value)
    max_addr = (1 << addr_w) - 1
    base = max_addr - 0x7F
    bound = 0x200
    await load_cfg(base, bound)
    virt = 0x180
    dut.i_virtual_addr.value = virt
    dut.i_valid.value = 1
    await RisingEdge(dut.clk)
    expected_phys = (base + virt) & max_addr
    assert int(dut.o_physical_addr.value) == expected_phys

@cocotb.test()
async def test_mmu_reset(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing reset behavior")
    
    dut.rst_n.value = 1
    dut.i_base_addr.value = 0x5000
    dut.i_bound_addr.value = 0x1000
    dut.i_valid.value = 1
    dut.i_virtual_addr.value = 0x100
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    physical_before = int(dut.o_physical_addr.value)
    assert physical_before != 0x100, "Should have non-trivial translation"
    
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    
    physical_after = int(dut.o_physical_addr.value)
    assert physical_after == 0x100, "Reset should clear base register"
    
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    physical_after2 = int(dut.o_physical_addr.value)
    assert physical_after2 == 0x100, "Should use zero base after reset"
    
    dut._log.info("Reset test passed!")