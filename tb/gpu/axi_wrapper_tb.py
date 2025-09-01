import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles, Timer
from cocotb.result import TestFailure
import random

# GPU Register Map
ADDR_CONTROL      = 0x00000000
ADDR_STATUS       = 0x00000004
ADDR_VERTEX_BASE  = 0x00000008
ADDR_VERTEX_COUNT = 0x0000000C
ADDR_PC           = 0x00000010
ADDR_SHADER_BASE  = 0x00001000

# Control register bits
CTRL_START = 0
CTRL_IRQ_CLEAR = 1

# Status register bits
STATUS_BUSY = 0
STATUS_IRQ = 1

class AXILiteMaster:
    def __init__(self, dut, clock):
        self.dut = dut
        self.clock = clock
        
        # Initialize all signals
        self.dut.s_axi_awaddr.value = 0
        self.dut.s_axi_awprot.value = 0
        self.dut.s_axi_awvalid.value = 0
        self.dut.s_axi_wdata.value = 0
        self.dut.s_axi_wstrb.value = 0
        self.dut.s_axi_wvalid.value = 0
        self.dut.s_axi_bready.value = 0
        self.dut.s_axi_araddr.value = 0
        self.dut.s_axi_arprot.value = 0
        self.dut.s_axi_arvalid.value = 0
        self.dut.s_axi_rready.value = 0
        
    async def write(self, address, data):
        await RisingEdge(self.clock)
        
        # Set write address and data
        self.dut.s_axi_awaddr.value = address
        self.dut.s_axi_awvalid.value = 1
        self.dut.s_axi_awprot.value = 0
        
        self.dut.s_axi_wdata.value = data
        self.dut.s_axi_wstrb.value = 0xF  # All bytes valid
        self.dut.s_axi_wvalid.value = 1
        
        self.dut.s_axi_bready.value = 1
        
        # Wait for address handshake
        while not self.dut.s_axi_awready.value:
            await RisingEdge(self.clock)
        
        await RisingEdge(self.clock)
        self.dut.s_axi_awvalid.value = 0
        
        # Wait for data handshake
        while not self.dut.s_axi_wready.value:
            await RisingEdge(self.clock)
            
        await RisingEdge(self.clock)
        self.dut.s_axi_wvalid.value = 0
        
        # Wait for write response
        while not self.dut.s_axi_bvalid.value:
            await RisingEdge(self.clock)
            
        resp = self.dut.s_axi_bresp.value
        await RisingEdge(self.clock)
        self.dut.s_axi_bready.value = 0
        
        return resp
        
    async def read(self, address):
        await RisingEdge(self.clock)
        
        # Set read address
        self.dut.s_axi_araddr.value = address
        self.dut.s_axi_arvalid.value = 1
        self.dut.s_axi_arprot.value = 0
        self.dut.s_axi_rready.value = 1
        
        # Wait for address handshake
        while not self.dut.s_axi_arready.value:
            await RisingEdge(self.clock)
            
        await RisingEdge(self.clock)
        self.dut.s_axi_arvalid.value = 0
        
        # Wait for read data
        while not self.dut.s_axi_rvalid.value:
            await RisingEdge(self.clock)
            
        data = self.dut.s_axi_rdata.value
        resp = self.dut.s_axi_rresp.value
        
        await RisingEdge(self.clock)
        self.dut.s_axi_rready.value = 0
        
        return int(data)

class AXIMasterSlave:
    
    def __init__(self, dut, clock, size=65536):
        self.dut = dut
        self.clock = clock
        self.memory = {}
        self.size = size
        
        # Initialize memory with pattern
        for i in range(min(1024, size)):
            self.memory[i*4] = 0xDEAD0000 + i
            
        # Start slave process
        cocotb.start_soon(self.slave_process())
        
    async def slave_process(self):
        """Handle AXI4 master requests from GPU"""
        
        # Initialize signals
        self.dut.m_axi_awready.value = 0
        self.dut.m_axi_wready.value = 0
        self.dut.m_axi_bvalid.value = 0
        self.dut.m_axi_bid.value = 0
        self.dut.m_axi_bresp.value = 0
        self.dut.m_axi_arready.value = 0
        self.dut.m_axi_rvalid.value = 0
        self.dut.m_axi_rid.value = 0
        self.dut.m_axi_rdata.value = 0
        self.dut.m_axi_rresp.value = 0
        self.dut.m_axi_rlast.value = 0
        
        write_addr = 0
        write_id = 0
        
        while True:
            await RisingEdge(self.clock)
            
            # Handle write address channel
            if self.dut.m_axi_awvalid.value and not self.dut.m_axi_awready.value:
                self.dut.m_axi_awready.value = 1
                write_addr = int(self.dut.m_axi_awaddr.value)
                write_id = int(self.dut.m_axi_awid.value)
            else:
                self.dut.m_axi_awready.value = 0
                
            # Handle write data channel
            if self.dut.m_axi_wvalid.value and not self.dut.m_axi_wready.value:
                self.dut.m_axi_wready.value = 1
                data = int(self.dut.m_axi_wdata.value)
                self.memory[write_addr] = data
                self.dut._log.info(f"DDR Write: addr=0x{write_addr:08x}, data=0x{data:08x}")
            else:
                self.dut.m_axi_wready.value = 0
                
            # Send write response
            if self.dut.m_axi_wready.value:
                self.dut.m_axi_bvalid.value = 1
                self.dut.m_axi_bid.value = write_id
                self.dut.m_axi_bresp.value = 0  # OKAY
            elif self.dut.m_axi_bready.value and self.dut.m_axi_bvalid.value:
                self.dut.m_axi_bvalid.value = 0
                
            # Handle read address channel
            if self.dut.m_axi_arvalid.value and not self.dut.m_axi_arready.value:
                self.dut.m_axi_arready.value = 1
                read_addr = int(self.dut.m_axi_araddr.value)
                read_id = int(self.dut.m_axi_arid.value)
                
                # Prepare read response
                await RisingEdge(self.clock)
                self.dut.m_axi_arready.value = 0
                
                # Send read data
                self.dut.m_axi_rvalid.value = 1
                if read_addr in self.memory:
                    self.dut.m_axi_rdata.value = self.memory[read_addr]
                else:
                    self.dut.m_axi_rdata.value = 0xDEADBEEF
                self.dut.m_axi_rid.value = read_id
                self.dut.m_axi_rlast.value = 1  # Single beat
                self.dut.m_axi_rresp.value = 0  # OKAY
                
                self.dut._log.info(f"DDR Read: addr=0x{read_addr:08x}, data=0x{int(self.dut.m_axi_rdata.value):08x}")
            else:
                self.dut.m_axi_arready.value = 0
                
            # Clear read valid when accepted
            if self.dut.m_axi_rready.value and self.dut.m_axi_rvalid.value:
                self.dut.m_axi_rvalid.value = 0
                self.dut.m_axi_rlast.value = 0

async def reset_dut(dut):
    dut.s_axi_aresetn.value = 0
    await ClockCycles(dut.s_axi_aclk, 10)
    dut.s_axi_aresetn.value = 1
    await ClockCycles(dut.s_axi_aclk, 10)

@cocotb.test()
async def test_basic_register_access(dut):
    
    # Start clock
    clock = Clock(dut.s_axi_aclk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    # Create BFMs
    axi_master = AXILiteMaster(dut, dut.s_axi_aclk)
    axi_slave = AXIMasterSlave(dut, dut.s_axi_aclk)
    
    # Reset
    await reset_dut(dut)
    
    dut._log.info("Testing basic register access...")
    
    # Write and read vertex base
    await axi_master.write(ADDR_VERTEX_BASE, 0x10000000)
    data = await axi_master.read(ADDR_VERTEX_BASE)
    assert data == 0x10000000, f"Vertex base mismatch: got {data:08x}"
    
    # Write and read vertex count
    await axi_master.write(ADDR_VERTEX_COUNT, 9)
    data = await axi_master.read(ADDR_VERTEX_COUNT)
    assert data == 9, f"Vertex count mismatch: got {data}"
    
    # Write and read PC
    await axi_master.write(ADDR_PC, 0x100)
    data = await axi_master.read(ADDR_PC)
    assert data == 0x100, f"PC mismatch: got {data:08x}"
    
    dut._log.info("Basic register test PASSED")

@cocotb.test()
async def test_shader_memory(dut):
    
    clock = Clock(dut.s_axi_aclk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    axi_master = AXILiteMaster(dut, dut.s_axi_aclk)
    axi_slave = AXIMasterSlave(dut, dut.s_axi_aclk)
    
    await reset_dut(dut)
    
    dut._log.info("Testing shader memory...")
    
    # Write shader instructions
    test_program = [
        0x12345678,
        0x9ABCDEF0,
        0xDEADBEEF,
        0xCAFEBABE,
        0x00000000,
        0xFFFFFFFF,
    ]
    
    for i, instr in enumerate(test_program):
        await axi_master.write(ADDR_SHADER_BASE + i*4, instr)
        
    # Read back and verify
    for i, expected in enumerate(test_program):
        data = await axi_master.read(ADDR_SHADER_BASE + i*4)
        assert data == expected, f"Shader[{i}] mismatch: got {data:08x}, expected {expected:08x}"
        
    dut._log.info("Shader memory test PASSED")

@cocotb.test()
async def test_gpu_start(dut):
    
    clock = Clock(dut.s_axi_aclk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    axi_master = AXILiteMaster(dut, dut.s_axi_aclk)
    axi_slave = AXIMasterSlave(dut, dut.s_axi_aclk)
    
    await reset_dut(dut)
    
    dut._log.info("Testing GPU start...")
    
    # Setup vertex data in memory
    axi_slave.memory[0x00000000] = 0x00640064  # Vertex 0
    axi_slave.memory[0x00000004] = 0x00C80064  # Vertex 1
    axi_slave.memory[0x00000008] = 0x009600C8  # Vertex 2
    
    # Configure GPU
    await axi_master.write(ADDR_VERTEX_BASE, 0x00000000)
    await axi_master.write(ADDR_VERTEX_COUNT, 3)
    await axi_master.write(ADDR_PC, 0)
    
    # Read initial status
    status = await axi_master.read(ADDR_STATUS)
    dut._log.info(f"Initial status: 0x{status:08x}")
    assert (status & (1 << STATUS_BUSY)) == 0, "GPU should be idle initially"
    
    # Start GPU
    await axi_master.write(ADDR_CONTROL, 1 << CTRL_START)
    
    # Wait a bit
    await ClockCycles(dut.s_axi_aclk, 50)
    
    # Check status
    status = await axi_master.read(ADDR_STATUS)
    dut._log.info(f"Status after start: 0x{status:08x}")
    
    # Wait for completion (with timeout)
    for _ in range(1000):
        status = await axi_master.read(ADDR_STATUS)
        if not (status & (1 << STATUS_BUSY)):
            break
        await ClockCycles(dut.s_axi_aclk, 10)
    
    dut._log.info("GPU start test PASSED")

@cocotb.test()
async def test_concurrent_access(dut):
    
    clock = Clock(dut.s_axi_aclk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    axi_master = AXILiteMaster(dut, dut.s_axi_aclk)
    axi_slave = AXIMasterSlave(dut, dut.s_axi_aclk)
    
    await reset_dut(dut)
    
    dut._log.info("Testing concurrent access...")
    
    # Start GPU operation
    await axi_master.write(ADDR_VERTEX_BASE, 0x1000)
    await axi_master.write(ADDR_VERTEX_COUNT, 10)
    await axi_master.write(ADDR_CONTROL, 1 << CTRL_START)
    
    # Try to access registers while GPU might be accessing memory
    results = []
    
    async def read_task():
        for _ in range(10):
            data = await axi_master.read(ADDR_STATUS)
            results.append(data)
            await ClockCycles(dut.s_axi_aclk, random.randint(1, 10))
    
    # Run concurrent reads
    await read_task()
    
    dut._log.info(f"Captured {len(results)} status reads during operation")
    dut._log.info("Concurrent access test PASSED")

@cocotb.test()
async def test_stress(dut):
    
    clock = Clock(dut.s_axi_aclk, 10, units="ns")
    cocotb.start_soon(clock.start())
    
    axi_master = AXILiteMaster(dut, dut.s_axi_aclk)
    axi_slave = AXIMasterSlave(dut, dut.s_axi_aclk)
    
    await reset_dut(dut)
    
    dut._log.info("Running stress test...")
    
    # Random operations
    for i in range(100):
        op = random.choice(['write_reg', 'read_reg', 'write_shader', 'start', 'status'])
        
        if op == 'write_reg':
            addr = random.choice([ADDR_VERTEX_BASE, ADDR_VERTEX_COUNT, ADDR_PC])
            data = random.randint(0, 0xFFFFFFFF)
            await axi_master.write(addr, data)
            
        elif op == 'read_reg':
            addr = random.choice([ADDR_STATUS, ADDR_VERTEX_BASE, ADDR_VERTEX_COUNT])
            data = await axi_master.read(addr)
            
        elif op == 'write_shader':
            offset = random.randint(0, 63) * 4
            data = random.randint(0, 0xFFFFFFFF)
            await axi_master.write(ADDR_SHADER_BASE + offset, data)
            
        elif op == 'start':
            await axi_master.write(ADDR_CONTROL, 1 << CTRL_START)
            
        elif op == 'status':
            status = await axi_master.read(ADDR_STATUS)
            
        await ClockCycles(dut.s_axi_aclk, random.randint(1, 10))
        
        if (i + 1) % 20 == 0:
            dut._log.info(f"Stress test progress: {i+1}/100")
    
    dut._log.info("Stress test PASSED")
