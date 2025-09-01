import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random

CLK_PERIOD = 10

@cocotb.test()
async def test_interconnect_basic(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    num_masters = int(dut.NUM_MASTERS.value)
    num_slaves = int(dut.NUM_SLAVES.value)
    addr_width = 32
    data_width = 32
    
    dut._log.info(f"Starting interconnect test ({num_masters} masters, {num_slaves} slaves)")
    
    # Reset
    dut.rst_n.value = 0
    dut.i_master_req.value = 0
    dut.i_master_addr.value = 0
    dut.i_master_wdata.value = 0
    dut.i_slave_rdata.value = 0
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    dut._log.info("Test 1: Single master access to different slaves")
    
    for slave_idx in range(min(num_slaves, 4)):
        addr = (slave_idx << 14) | 0x1000
        wdata = 0x1234
        rdata_val = 0x5678 + slave_idx
        
        # Set master 0 to request (bit 0 = 1)
        dut.i_master_req.value = 1
        
        # For packed arrays, we need to set the entire vector
        # Master 0 gets the lower bits, Master 1 gets the upper bits
        master_addr_vector = 0
        master_wdata_vector = 0
        
        # Set address for master 0 (lower 32 bits of the packed array)
        master_addr_vector = addr
        
        # Set write data for master 0 (lower 32 bits)
        master_wdata_vector = wdata
        
        dut.i_master_addr.value = master_addr_vector
        dut.i_master_wdata.value = master_wdata_vector
        
        # Set slave read data - each slave gets 32 bits
        slave_rdata_vector = 0
        for i in range(num_slaves):
            if i == slave_idx:
                slave_rdata_vector |= (rdata_val << (i * data_width))
        
        dut.i_slave_rdata.value = slave_rdata_vector
        
        await RisingEdge(dut.clk)
        
        req_out = int(dut.o_slave_req.value)
        expected_req = 1 << slave_idx
        
        dut._log.info(f"Slave {slave_idx}: addr=0x{addr:x}, req_out=0x{req_out:x}, expected=0x{expected_req:x}")
        
        assert req_out == expected_req, f"Slave {slave_idx} should receive request"
        
        # Extract read data for master 0 (lower 32 bits)
        rdata_back = int(dut.o_master_rdata.value) & 0xFFFFFFFF
        
        if slave_idx == 0:
            assert rdata_back == rdata_val, f"Should receive correct read data from slave 0"
    
    dut.i_master_req.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Test 2: Multiple master arbitration")
    
    # Both masters request (bits 0 and 1)
    dut.i_master_req.value = 3
    
    # Set addresses for both masters
    # Master 0: address 0x4000 (slave 1)
    # Master 1: address 0x8000 (slave 2)
    master_addr_vector = 0x4000 | (0x8000 << addr_width)
    dut.i_master_addr.value = master_addr_vector
    
    # Set write data for both masters
    master_wdata_vector = 0x1111 | (0x2222 << data_width)
    dut.i_master_wdata.value = master_wdata_vector
    
    # Set slave 1 read data
    slave_rdata_vector = 0x9999 << (1 * data_width)
    dut.i_slave_rdata.value = slave_rdata_vector
    
    await RisingEdge(dut.clk)
    
    req_out = int(dut.o_slave_req.value)
    # Either slave 1 or slave 2 should be accessed depending on arbitration
    assert req_out in [2, 4], f"Should access slave 1 or 2, got {req_out}"
    
    dut.i_master_req.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Basic interconnect test passed!")

@cocotb.test()
async def test_interconnect_address_decode(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    num_slaves = int(dut.NUM_SLAVES.value)
    addr_width = 32
    data_width = 32
    
    dut._log.info("Testing address decoding")
    
    # Reset
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    # Test patterns: (address, expected_slave)
    address_patterns = [
        (0x00000000, 0),  # Slave 0
        (0x00004000, 1),  # Slave 1
        (0x00008000, 2),  # Slave 2
        (0x0000C000, 3),  # Slave 3
        (0x12340000, 0),  # High bits ignored, still slave 0
        (0x12344000, 1),  # High bits ignored, still slave 1
        (0x12348000, 2),  # High bits ignored, still slave 2
        (0x1234C000, 3),  # High bits ignored, still slave 3
    ]
    
    for addr, expected_slave in address_patterns[:min(8, num_slaves * 2)]:
        if expected_slave >= num_slaves:
            continue
            
        # Master 0 requests
        dut.i_master_req.value = 1
        dut.i_master_addr.value = addr
        dut.i_master_wdata.value = 0x12345678
        
        # Set expected slave read data
        slave_rdata_vector = (0xAAAA0000 | expected_slave) << (expected_slave * data_width)
        dut.i_slave_rdata.value = slave_rdata_vector
        
        await RisingEdge(dut.clk)
        
        req_out = int(dut.o_slave_req.value)
        expected_req_mask = 1 << expected_slave
        
        dut._log.info(f"Addr 0x{addr:08x} -> slave {expected_slave}, req_mask=0x{req_out:x}")
        
        assert req_out == expected_req_mask, f"Address 0x{addr:08x} should route to slave {expected_slave}"
    
    dut.i_master_req.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Address decoding test passed!")

@cocotb.test()
async def test_interconnect_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    num_masters = int(dut.NUM_MASTERS.value)
    num_slaves = int(dut.NUM_SLAVES.value)
    addr_width = 32
    data_width = 32
    
    dut._log.info("Starting interconnect stress test")
    
    # Reset
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    total_cycles = 500
    active_cycles = 0
    
    for cycle in range(total_cycles):
        # Random master requests
        req_pattern = random.randint(0, (1 << num_masters) - 1)
        
        # Random target slave and address
        slave_target = random.randint(0, num_slaves - 1)
        addr = (slave_target << 14) | random.randint(0, 0x3FFF)
        wdata = random.randint(0, 0xFFFFFFFF)
        rdata = random.randint(0, 0xFFFFFFFF)
        
        dut.i_master_req.value = req_pattern
        
        # Build packed address vector for all masters
        master_addr_vector = 0
        master_wdata_vector = 0
        for i in range(num_masters):
            master_addr_vector |= (addr << (i * addr_width))
            master_wdata_vector |= (wdata << (i * data_width))
        
        dut.i_master_addr.value = master_addr_vector
        dut.i_master_wdata.value = master_wdata_vector
        
        # Build packed slave read data vector
        slave_rdata_vector = 0
        for i in range(num_slaves):
            slave_rdata_vector |= (rdata << (i * data_width))
        
        dut.i_slave_rdata.value = slave_rdata_vector
        
        await RisingEdge(dut.clk)
        
        req_out = int(dut.o_slave_req.value)
        
        if req_pattern != 0:
            active_cycles += 1
            assert req_out != 0, f"Cycle {cycle}: No slave received request despite master requests"
            
            # Check only one slave is active
            exactly_one_slave = bin(req_out).count('1') == 1
            assert exactly_one_slave, f"Cycle {cycle}: Multiple slaves active simultaneously (req_out=0x{req_out:x})"
            
            # Check correct slave is selected
            expected_slave = (addr >> 14) & 0x3
            expected_req = 1 << expected_slave if expected_slave < num_slaves else 0
            
            if expected_req > 0:
                assert req_out == expected_req, f"Cycle {cycle}: Wrong slave selected"
        else:
            assert req_out == 0, f"Cycle {cycle}: Slaves active despite no master requests"
        
        if (cycle + 1) % 100 == 0:
            dut._log.info(f"Stress test: {cycle + 1}/{total_cycles} cycles")
    
    dut._log.info(f"Stress test completed! Active cycles: {active_cycles}/{total_cycles}")

@cocotb.test()
async def test_interconnect_edge_cases(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    num_masters = int(dut.NUM_MASTERS.value)
    num_slaves = int(dut.NUM_SLAVES.value)
    data_width = 32
    
    dut._log.info("Testing edge cases")
    
    # Reset
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    dut._log.info("Edge case 1: No master requests")
    dut.i_master_req.value = 0
    
    # Set all slaves to return DEADBEEF
    slave_rdata_vector = 0
    for i in range(num_slaves):
        slave_rdata_vector |= (0xDEADBEEF << (i * data_width))
    dut.i_slave_rdata.value = slave_rdata_vector
    
    await RisingEdge(dut.clk)
    
    req_out = int(dut.o_slave_req.value)
    assert req_out == 0, "No slaves should be active when no masters request"
    
    rdata = int(dut.o_master_rdata.value)
    assert rdata == 0, "Masters should not receive data when not requesting"
    
    dut._log.info("Edge case 2: All masters request simultaneously")
    all_req = (1 << num_masters) - 1
    dut.i_master_req.value = all_req
    
    # All masters request slave 1
    master_addr_vector = 0
    master_wdata_vector = 0
    for i in range(num_masters):
        master_addr_vector |= (0x4000 << (i * 32))
        master_wdata_vector |= ((0x1000 + i) << (i * 32))
    
    dut.i_master_addr.value = master_addr_vector
    dut.i_master_wdata.value = master_wdata_vector
    
    # Slave 1 returns data
    slave_rdata_vector = 0x87654321 << (1 * data_width)
    dut.i_slave_rdata.value = slave_rdata_vector
    
    await RisingEdge(dut.clk)
    
    req_out = int(dut.o_slave_req.value)
    assert req_out == 2, "Exactly one slave (slave 1) should be active"
    
    dut._log.info("Edge case 3: Maximum address values")
    dut.i_master_req.value = 1
    dut.i_master_addr.value = 0xFFFFFFFF
    dut.i_master_wdata.value = 0xFFFFFFFF
    
    # Expected slave based on bits [15:14] of 0xFFFFFFFF = 0b11 = slave 3
    expected_slave = 3
    slave_rdata_vector = 0x12345678 << (expected_slave * data_width)
    dut.i_slave_rdata.value = slave_rdata_vector
    
    await RisingEdge(dut.clk)
    
    req_out = int(dut.o_slave_req.value)
    expected_req = 1 << expected_slave
    
    dut._log.info(f"Max address routes to slave {expected_slave}")
    assert req_out == expected_req, f"Max address should route to slave {expected_slave}"
    
    dut._log.info("Edge case 4: Boundary addresses")
    boundary_addrs = [0x0000, 0x4000, 0x8000, 0xC000]
    
    for i, addr in enumerate(boundary_addrs[:num_slaves]):
        dut.i_master_req.value = 1
        dut.i_master_addr.value = addr
        
        # Set slave read data
        slave_rdata_vector = (0x1000 + i) << (i * data_width)
        dut.i_slave_rdata.value = slave_rdata_vector
        
        await RisingEdge(dut.clk)
        
        req_out = int(dut.o_slave_req.value)
        expected_req = 1 << i
        assert req_out == expected_req, f"Boundary address 0x{addr:x} should route to slave {i}"
    
    dut.i_master_req.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Edge cases test passed!")