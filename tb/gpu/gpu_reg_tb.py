import cocotb
import random
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, Timer

async def reset_dut(dut, cycles=3):
    dut._log.info("Resetting DUT...")
    dut.rst_n.value = 0
    dut.i_wr_en.value = 0
    dut.i_wr_addr.value = 0
    dut.i_wr_data.value = 0
    dut.i_rd_addr_a.value = 0
    dut.i_rd_addr_b.value = 0
    await Timer(1, units="ns")
    for _ in range(cycles):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    dut._log.info("Reset complete.")

class RefRF:
    def __init__(self, dut, num_regs, data_width):
        self.dut = dut
        self.num_regs = num_regs
        self.data_width = data_width
        self.data_mask = (1 << data_width) - 1
        self.regs = [0] * num_regs
        self.dut._log.info(f"Reference model initialized with {num_regs} registers.")

    def write(self, addr, data):
        if 0 <= addr < self.num_regs:
            self.regs[addr] = data & self.data_mask

    def read(self, addr):
        if 0 <= addr < self.num_regs:
            return self.regs[addr]
        return 0

class Coverage:
    def __init__(self, num_regs):
        self.num_regs = num_regs
        self.bins = {
            "addresses_written": set(),
            "hazards": set(),
            "ports_written": set(),
            "ports_read": set()
        }

    def update(self, write_op, read_ops):
        if write_op:
            addr, _ = write_op
            self.bins["addresses_written"].add(addr)
            self.bins["ports_written"].add(0)
            for port, read_addr in read_ops:
                if addr == read_addr:
                    self.bins["hazards"].add("RAW_SAME_CYCLE")
        
        for port, _ in read_ops:
            self.bins["ports_read"].add(port)

    def check(self):
        assert 0 in self.bins["addresses_written"], "Coverage FAILED: Address 0 was not written."
        assert self.num_regs - 1 in self.bins["addresses_written"], f"Coverage FAILED: Address {self.num_regs - 1} was not written."
        assert "RAW_SAME_CYCLE" in self.bins["hazards"], "Coverage FAILED: RAW hazard was not tested."
        assert 0 in self.bins["ports_read"], "Coverage FAILED: Read port A was not used."
        assert 1 in self.bins["ports_read"], "Coverage FAILED: Read port B was not used."
        cocotb.log.info("Coverage check PASSED.")

async def run_and_check_cycle(dut, ref_model, coverage, write_op=None, read_ops=None):
    if read_ops is None:
        read_ops = []

    dut.i_rd_addr_a.value = next((addr for p, addr in read_ops if p == 0), 0)
    dut.i_rd_addr_b.value = next((addr for p, addr in read_ops if p == 1), 0)
    
    if write_op:
        wr_addr, wr_data = write_op
        dut.i_wr_en.value = 1
        dut.i_wr_addr.value = wr_addr
        dut.i_wr_data.value = wr_data
    else:
        dut.i_wr_en.value = 0

    await ReadOnly()
    for port, addr in read_ops:
        expected_data = ref_model.read(addr)
        dut_data = dut.o_rd_data_a.value if port == 0 else dut.o_rd_data_b.value
        
        assert dut_data.is_resolvable, f"Read data on port {port} is X/Z"
        assert int(dut_data) == expected_data, \
            f"Read Mismatch on Port {port} Addr {addr}: DUT={int(dut_data)}, EXP={expected_data}"

    await RisingEdge(dut.clk)

    if write_op:
        wr_addr, wr_data = write_op
        ref_model.write(wr_addr, wr_data)
    
    coverage.update(write_op, read_ops)
    dut.i_wr_en.value = 0

@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_register_file_comprehensive(dut):
    num_iters = int(os.getenv("RF_ITERS", 50000))
    seed = int(os.getenv("RF_SEED", 1337))
    random.seed(seed)

    num_regs = int(dut.NUM_REGS.value)
    data_width = int(dut.DATA_WIDTH.value)
    data_mask = (1 << data_width) - 1

    ref_model = RefRF(dut, num_regs, data_width)
    coverage = Coverage(num_regs)

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    dut._log.info("Starting directed tests...")
    await run_and_check_cycle(dut, ref_model, coverage, write_op=(5, 0xDEADBEEF))
    await run_and_check_cycle(dut, ref_model, coverage, read_ops=[(0, 5)])
    await run_and_check_cycle(dut, ref_model, coverage, write_op=(0, 0xAAAAAAAA))
    await run_and_check_cycle(dut, ref_model, coverage, write_op=(num_regs - 1, 0xBBBBBBBB))
    await run_and_check_cycle(dut, ref_model, coverage, read_ops=[(0, 0), (1, num_regs - 1)])
    
    dut._log.info("Testing RAW hazard (read-first)...")
    await run_and_check_cycle(dut, ref_model, coverage, write_op=(7, 0xCAFEF00D), read_ops=[(0, 7)])
    await run_and_check_cycle(dut, ref_model, coverage, read_ops=[(0, 7)])
    dut._log.info("Directed tests passed.")

    dut._log.info(f"Starting random stress test with {num_iters} cycles (seed={seed})...")
    for _ in range(num_iters):
        write_op = None
        if random.random() < 0.5:
            write_op = (random.randint(0, num_regs - 1), random.randint(0, data_mask))
        
        read_ops = [
            (0, random.randint(0, num_regs - 1)),
            (1, random.randint(0, num_regs - 1))
        ]
        
        await run_and_check_cycle(dut, ref_model, coverage, write_op, read_ops)

    await RisingEdge(dut.clk)
    coverage.check()
    dut._log.info("Random stress test passed.")
