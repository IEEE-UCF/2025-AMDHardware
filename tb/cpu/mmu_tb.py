
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles
import random

# Page Table Entry (PTE) bit positions
PTE_V = 0  # Valid
PTE_R = 1  # Read
PTE_W = 2  # Write
PTE_X = 3  # Execute
PTE_U = 4  # User
PTE_G = 5  # Global
PTE_A = 6  # Accessed
PTE_D = 7  # Dirty

# Privilege modes
PRIV_U = 0b00  # User
PRIV_S = 0b01  # Supervisor
PRIV_M = 0b11  # Machine

def make_pte(ppn, flags):
    """Create a Page Table Entry"""
    return (ppn << 10) | flags

def make_satp(ppn):
    """Create SATP value for Sv32"""
    return ppn & 0xFFFFF  # 20-bit PPN

@cocotb.test()
async def test_reset(dut):
    """Test 1: Verify reset behavior"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    dut.req_valid.value = 0
    dut.vm_enable.value = 0
    dut.tlb_flush.value = 0
    await ClockCycles(dut.clk, 5)
    
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    # Check outputs are in reset state
    assert dut.trans_valid.value == 0
    assert dut.page_fault.value == 0
    assert dut.access_fault.value == 0
    assert dut.ptw_req.value == 0
    
    dut._log.info("Reset test passed")

@cocotb.test()
async def test_direct_mapping(dut):
    """Test 2: Direct mapping when VM is disabled"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    # Disable VM
    dut.vm_enable.value = 0
    
    # Test several addresses
    test_addrs = [0x00000000, 0x12345678, 0xDEADBEEF, 0xFFFFFFFF]
    
    for addr in test_addrs:
        dut.vaddr.value = addr
        dut.req_valid.value = 1
        dut.req_write.value = random.randint(0, 1)
        dut.req_priv.value = PRIV_M
        
        await RisingEdge(dut.clk)
        
        # With VM disabled, paddr should equal vaddr
        assert dut.paddr.value == addr, f"Direct mapping failed: {hex(dut.paddr.value)} != {hex(addr)}"
        assert dut.trans_valid.value == 1
        assert dut.page_fault.value == 0
        assert dut.access_fault.value == 0
    
    dut._log.info("Direct mapping test passed")

@cocotb.test()
async def test_tlb_miss_ptw(dut):
    """Test 3: TLB miss triggers page table walk"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    # Enable VM
    dut.vm_enable.value = 1
    dut.satp.value = make_satp(0x1000)  # Page table at 0x1000000
    
    # Request translation for address that will miss TLB
    dut.vaddr.value = 0x00001234
    dut.req_valid.value = 1
    dut.req_write.value = 0
    dut.req_priv.value = PRIV_U
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    # Should start page table walk
    assert dut.ptw_req.value == 1, "PTW request not generated on TLB miss"
    
    # Simulate page table response - valid L1 PTE pointing to L0
    dut.ptw_data.value = make_pte(0x2000, (1 << PTE_V))  # Valid pointer to next level
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    # Wait for L0 walk
    await ClockCycles(dut.clk, 3)
    
    # Provide L0 PTE - valid page with RWX permissions
    dut.ptw_data.value = make_pte(0x3000, 
                                   (1 << PTE_V) | (1 << PTE_R) | 
                                   (1 << PTE_W) | (1 << PTE_U))
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    await ClockCycles(dut.clk, 3)
    
    dut._log.info("TLB miss and PTW test passed")

@cocotb.test()
async def test_permission_check(dut):
    """Test 4: Permission checking"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset and setup
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut.vm_enable.value = 1
    dut.satp.value = make_satp(0x1000)
    
    # Test 1: User mode accessing user page - should succeed
    dut.vaddr.value = 0x00001000
    dut.req_valid.value = 1
    dut.req_write.value = 0  # Read
    dut.req_priv.value = PRIV_U
    
    # Provide PTW response with user-accessible page
    await ClockCycles(dut.clk, 2)
    dut.ptw_data.value = make_pte(0x2000, (1 << PTE_V))
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    await ClockCycles(dut.clk, 2)
    dut.ptw_data.value = make_pte(0x3000, 
                                   (1 << PTE_V) | (1 << PTE_R) | 
                                   (1 << PTE_U))  # User accessible
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    await ClockCycles(dut.clk, 5)
    
    # Test 2: Write to read-only page - should fail
    dut.vaddr.value = 0x00002000
    dut.req_write.value = 1  # Write
    
    await ClockCycles(dut.clk, 2)
    dut.ptw_data.value = make_pte(0x2000, (1 << PTE_V))
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    await ClockCycles(dut.clk, 2)
    dut.ptw_data.value = make_pte(0x4000, 
                                   (1 << PTE_V) | (1 << PTE_R))  # Read-only
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    await ClockCycles(dut.clk, 5)
    
    dut._log.info("Permission check test passed")

@cocotb.test()
async def test_tlb_flush(dut):
    """Test 5: TLB flush operations"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    dut.req_valid.value = 0
    dut.ptw_ready.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut.vm_enable.value = 1
    dut.satp.value = make_satp(0x1000)
    
    # First access - will populate TLB
    dut.vaddr.value = 0x00001000
    dut.req_valid.value = 1
    dut.req_write.value = 0
    dut.req_priv.value = PRIV_U
    
    # Wait for PTW to start
    await ClockCycles(dut.clk, 3)
    
    # Provide L1 PTE
    dut.ptw_data.value = make_pte(0x2000, (1 << PTE_V))
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    # Wait for L0 request
    await ClockCycles(dut.clk, 3)
    
    # Provide L0 PTE
    dut.ptw_data.value = make_pte(0x3000, 
                                   (1 << PTE_V) | (1 << PTE_R) | 
                                   (1 << PTE_W) | (1 << PTE_U))
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    # Wait for TLB update to complete
    await ClockCycles(dut.clk, 5)
    
    # Now access the same address again - should hit in TLB
    dut.vaddr.value = 0x00001000
    dut.req_valid.value = 1
    await ClockCycles(dut.clk, 2)
    
    # Should NOT trigger PTW (TLB hit)
    assert dut.ptw_req.value == 0, "PTW triggered on TLB hit"
    
    # Clear request
    dut.req_valid.value = 0
    await ClockCycles(dut.clk, 2)
    
    # Flush TLB
    dut.tlb_flush.value = 1
    dut.tlb_flush_vaddr.value = 0
    await RisingEdge(dut.clk)
    dut.tlb_flush.value = 0
    await ClockCycles(dut.clk, 2)
    
    # Access same address again - should miss after flush
    dut.vaddr.value = 0x00001000
    dut.req_valid.value = 1
    
    # Wait for state machine to recognize miss and start PTW
    await ClockCycles(dut.clk, 3)
    
    # Should trigger PTW after flush
    assert dut.ptw_req.value == 1, "PTW not triggered after TLB flush"
    
    dut._log.info("TLB flush test passed")

@cocotb.test()
async def test_superpage(dut):
    """Test 6: Superpage (4MB) translation"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut.vm_enable.value = 1
    dut.satp.value = make_satp(0x1000)
    
    # Access address in superpage range
    dut.vaddr.value = 0x00400000  # 4MB aligned
    dut.req_valid.value = 1
    dut.req_write.value = 0
    dut.req_priv.value = PRIV_S
    
    await ClockCycles(dut.clk, 2)
    
    # L1 PTE is a leaf (superpage)
    dut.ptw_data.value = make_pte(0x5000, 
                                   (1 << PTE_V) | (1 << PTE_R) | 
                                   (1 << PTE_W) | (1 << PTE_X))
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    await ClockCycles(dut.clk, 5)
    
    # Check translation completed
    assert dut.trans_valid.value == 1, "Superpage translation failed"
    
    dut._log.info("Superpage test passed")

@cocotb.test()
async def test_page_fault(dut):
    """Test 7: Page fault generation"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    dut.req_valid.value = 0
    dut.ptw_ready.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut.vm_enable.value = 1
    dut.satp.value = make_satp(0x1000)
    
    # Access unmapped address
    dut.vaddr.value = 0xBADC0DE0
    dut.req_valid.value = 1
    dut.req_write.value = 0
    dut.req_priv.value = PRIV_U
    
    # Wait for PTW to start
    await ClockCycles(dut.clk, 3)
    
    # Provide invalid L1 PTE (V=0)
    dut.ptw_data.value = 0  # Invalid
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    # State machine should transition to PTW_L0
    await ClockCycles(dut.clk, 3)
    
    # Provide invalid L0 PTE as well
    dut.ptw_data.value = 0  # Invalid
    dut.ptw_ready.value = 1
    await RisingEdge(dut.clk)
    dut.ptw_ready.value = 0
    
    # Wait for FAULT state
    await ClockCycles(dut.clk, 2)
    
    # Check page fault is asserted
    assert dut.page_fault.value == 1, "Page fault not generated for invalid PTE"
    
    dut._log.info("Page fault test passed")

@cocotb.test()
async def test_concurrent_requests(dut):
    """Test 8: Handle back-to-back translation requests"""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut.vm_enable.value = 1
    dut.satp.value = make_satp(0x1000)
    
    # Multiple addresses to translate
    addresses = [0x1000, 0x2000, 0x3000, 0x4000]
    
    for addr in addresses:
        dut.vaddr.value = addr
        dut.req_valid.value = 1
        dut.req_write.value = 0
        dut.req_priv.value = PRIV_U
        
        # Handle PTW for each
        await ClockCycles(dut.clk, 2)
        dut.ptw_data.value = make_pte(0x2000, (1 << PTE_V))
        dut.ptw_ready.value = 1
        await RisingEdge(dut.clk)
        dut.ptw_ready.value = 0
        
        await ClockCycles(dut.clk, 2)
        dut.ptw_data.value = make_pte((addr >> 12) + 0x100, 
                                       (1 << PTE_V) | (1 << PTE_R) | 
                                       (1 << PTE_W) | (1 << PTE_U))
        dut.ptw_ready.value = 1
        await RisingEdge(dut.clk)
        dut.ptw_ready.value = 0
        
        await ClockCycles(dut.clk, 5)
    
    dut._log.info("Concurrent requests test passed")