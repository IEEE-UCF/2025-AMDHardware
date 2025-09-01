import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random

CLK_PERIOD = 10

@cocotb.test()
async def test_controller_basic(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())

    dut._log.info("Starting controller test")

    dut.rst_n.value = 0
    dut.i_bus_addr.value = 0
    dut.i_bus_wdata.value = 0
    dut.i_bus_we.value = 0
    dut.i_pipeline_busy.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    dut._log.info("Test 1: Reading status register")
    dut.i_bus_addr.value = 0x04
    dut.i_bus_we.value = 0
    await RisingEdge(dut.clk)

    status = int(dut.o_bus_rdata.value)
    dut._log.info(f"Initial status: 0x{status:08x}")
    assert status == 0, f"Initial status should be 0, got 0x{status:08x}"

    dut._log.info("Test 2: Start command")
    dut.i_bus_addr.value = 0x00
    dut.i_bus_wdata.value = 0x01
    dut.i_bus_we.value = 1
    await RisingEdge(dut.clk)

    dut.i_bus_we.value = 0
    await RisingEdge(dut.clk)

    start_pulse = int(dut.o_start_pipeline.value)
    dut._log.info(f"Start pulse: {start_pulse}")
    assert start_pulse == 1, f"Expected start pulse, got {start_pulse}"

    dut._log.info("Test 3: Pipeline busy")
    dut.i_pipeline_busy.value = 1
    await RisingEdge(dut.clk)

    start_pulse = int(dut.o_start_pipeline.value)
    assert start_pulse == 0, f"Start should be 0 when pipeline busy, got {start_pulse}"

    dut._log.info("Test 4: IRQ generation")
    dut.i_pipeline_busy.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    irq = int(dut.o_irq.value)
    dut._log.info(f"IRQ: {irq}")
    assert irq == 1, f"Expected IRQ, got {irq}"

    dut.i_bus_addr.value = 0x04
    await RisingEdge(dut.clk)
    status = int(dut.o_bus_rdata.value)
    dut._log.info(f"Status with IRQ: 0x{status:08x}")
    assert (status & 0x02) != 0, "IRQ pending bit should be set"

    dut._log.info("Test 5: Clear IRQ")
    dut.i_bus_addr.value = 0x00
    dut.i_bus_wdata.value = 0x02
    dut.i_bus_we.value = 1
    await RisingEdge(dut.clk)

    dut.i_bus_we.value = 0
    await RisingEdge(dut.clk)

    irq = int(dut.o_irq.value)
    assert irq == 0, f"IRQ should be cleared, got {irq}"

    dut._log.info("Test 6: Queue behavior")

    dut.i_pipeline_busy.value = 1
    await RisingEdge(dut.clk)

    for i in range(5):
        dut.i_bus_addr.value = 0x00
        dut.i_bus_wdata.value = 0x01
        dut.i_bus_we.value = 1
        await RisingEdge(dut.clk)
        dut.i_bus_we.value = 0
        await RisingEdge(dut.clk)

    dut.i_bus_addr.value = 0x04
    await RisingEdge(dut.clk)
    status = int(dut.o_bus_rdata.value)
    queue_count = (status >> 4) & 0xF
    dut._log.info(f"Queue count: {queue_count}")
    assert queue_count > 0, "Queue should have pending commands"

    dut.i_pipeline_busy.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    start_pulse = int(dut.o_start_pipeline.value)
    assert start_pulse == 1, "Should see start pulse from queue"

    dut._log.info("Controller test passed!")

@cocotb.test()
async def test_controller_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())

    num_cycles = int(dut.QUEUE_DEPTH.value) * 50
    report_interval = max(100, num_cycles // 10)

    dut._log.info(f"Starting stress test ({num_cycles} cycles)")

    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    random.seed(42)

    for i in range(num_cycles):
        op_weights = [30, 10, 20, 40]
        op = random.choices(['start', 'irq_clear', 'status_read', 'idle'], weights=op_weights)[0]

        pipeline_busy = random.choice([0, 1]) if i > num_cycles // 10 else 0

        dut.i_pipeline_busy.value = pipeline_busy

        if op == 'start':
            dut.i_bus_addr.value = 0x00
            dut.i_bus_wdata.value = 0x01
            dut.i_bus_we.value = 1
        elif op == 'irq_clear':
            dut.i_bus_addr.value = 0x00
            dut.i_bus_wdata.value = 0x02
            dut.i_bus_we.value = 1
        elif op == 'status_read':
            dut.i_bus_addr.value = 0x04
            dut.i_bus_we.value = 0
        else:
            dut.i_bus_we.value = 0

        await RisingEdge(dut.clk)

        if (i + 1) % report_interval == 0:
            dut._log.info(f"Stress test: {i + 1}/{num_cycles} cycles")

    dut._log.info(f"Stress test completed! ({num_cycles} cycles)")

@cocotb.test()
async def test_controller_extended_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())

    num_cycles = 2000

    dut._log.info(f"Starting extended stress test ({num_cycles} cycles)")

    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    random.seed(12345)

    for i in range(num_cycles):
        op = random.choices(['start', 'irq_clear', 'status_read', 'idle'],
                            weights=[40, 15, 25, 20])[0]

        pipeline_busy = random.choice([0, 1]) if i > 100 else 0

        dut.i_pipeline_busy.value = pipeline_busy

        if op == 'start':
            dut.i_bus_addr.value = 0x00
            dut.i_bus_wdata.value = 0x01
            dut.i_bus_we.value = 1
        elif op == 'irq_clear':
            dut.i_bus_addr.value = 0x00
            dut.i_bus_wdata.value = 0x02
            dut.i_bus_we.value = 1
        elif op == 'status_read':
            dut.i_bus_addr.value = 0x04
            dut.i_bus_we.value = 0
        else:
            dut.i_bus_we.value = 0

        await RisingEdge(dut.clk)

        if (i + 1) % 400 == 0:
            dut._log.info(f"Extended stress: {i + 1}/{num_cycles} cycles")

    dut._log.info("Extended stress test completed!")
