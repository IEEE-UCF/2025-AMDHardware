import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer
import random
from dataclasses import dataclass
from enum import Enum

"""
GPU Operation Queue Testbench

Tests the GPU operation queue module which manages GPU instructions
sent from the CPU. The queue handles instruction buffering, priority
management, and flow control between CPU and GPU.

Based on the GPU ISA documentation:
- Bit 0: Scalar/Vector mode
- Bit 1: Write memory
- Bit 2: Read memory  
- Bit 3: Multi-value
- Bits 11:4: Opcode
- Bits 15:12: Destination register
- Bits 79:16: Data field
"""


class GPUInstructionType(Enum):
    """GPU instruction types based on mode bits"""

    SCALAR_COMPUTE = "SCALAR_COMPUTE"
    VECTOR_COMPUTE = "VECTOR_COMPUTE"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    MULTI_VALUE = "MULTI_VALUE"


@dataclass
class GPUInstruction:
    """GPU instruction representation"""

    scalar_vector_mode: int  # Bit 0
    write_mem: int  # Bit 1
    read_mem: int  # Bit 2
    multi_value: int  # Bit 3
    opcode: int  # Bits 11:4
    dest_reg: int  # Bits 15:12
    data_field: int  # Bits 79:16

    def to_bits(self) -> int:
        """Convert to 80-bit instruction format"""
        instruction = 0
        instruction |= self.scalar_vector_mode & 0x1
        instruction |= (self.write_mem & 0x1) << 1
        instruction |= (self.read_mem & 0x1) << 2
        instruction |= (self.multi_value & 0x1) << 3
        instruction |= (self.opcode & 0xFF) << 4
        instruction |= (self.dest_reg & 0xF) << 12
        instruction |= (self.data_field & 0xFFFFFFFFFFFFFFFF) << 16
        return instruction

    def get_type(self) -> GPUInstructionType:
        """Determine instruction type from mode bits"""
        if self.write_mem:
            return GPUInstructionType.MEMORY_WRITE
        elif self.read_mem:
            return GPUInstructionType.MEMORY_READ
        elif self.multi_value:
            return GPUInstructionType.MULTI_VALUE
        elif self.scalar_vector_mode:
            return GPUInstructionType.VECTOR_COMPUTE
        else:
            return GPUInstructionType.SCALAR_COMPUTE

    def get_priority(self) -> int:
        """Get priority level (higher value = higher priority)"""
        if self.write_mem:
            return 7  # Highest priority
        elif self.read_mem:
            return 6
        elif self.scalar_vector_mode:
            return 4
        else:
            return 2  # Lowest priority


class GPUOpQueueDriver:
    """Driver for GPU operation queue"""

    def __init__(self, dut):
        self.dut = dut
        # Initialize inputs
        self.dut.i_enqueue_valid.value = 0
        self.dut.i_instruction.value = 0
        self.dut.i_src_addr.value = 0
        self.dut.i_dst_addr.value = 0
        self.dut.i_dequeue_req.value = 0

    async def reset(self):
        """Reset the queue"""
        self.dut.rst_n.value = 0
        self.dut.i_enqueue_valid.value = 0
        self.dut.i_dequeue_req.value = 0
        await ClockCycles(self.dut.clk, 5)
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, 2)

    async def enqueue(self, instruction: GPUInstruction, src_addr: int, dst_addr: int):
        """Enqueue a GPU operation"""
        self.dut.i_instruction.value = instruction.to_bits()
        self.dut.i_src_addr.value = src_addr
        self.dut.i_dst_addr.value = dst_addr
        self.dut.i_enqueue_valid.value = 1
        await RisingEdge(self.dut.clk)
        self.dut.i_enqueue_valid.value = 0
        await Timer(1, units="ns")

    async def dequeue(self):
        """Request dequeue of next operation"""
        self.dut.i_dequeue_req.value = 1
        await RisingEdge(self.dut.clk)
        self.dut.i_dequeue_req.value = 0
        await Timer(1, units="ns")

    async def enqueue_dequeue_simultaneous(
        self, instruction: GPUInstruction, src_addr: int, dst_addr: int
    ):
        """Simultaneously enqueue and dequeue"""
        self.dut.i_instruction.value = instruction.to_bits()
        self.dut.i_src_addr.value = src_addr
        self.dut.i_dst_addr.value = dst_addr
        self.dut.i_enqueue_valid.value = 1
        self.dut.i_dequeue_req.value = 1
        await RisingEdge(self.dut.clk)
        self.dut.i_enqueue_valid.value = 0
        self.dut.i_dequeue_req.value = 0
        await Timer(1, units="ns")


class GPUOpQueueMonitor:
    """Monitor for GPU operation queue outputs"""

    def __init__(self, dut):
        self.dut = dut

    def is_full(self) -> bool:
        """Check if queue is full"""
        return bool(int(self.dut.o_queue_full.value))

    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return bool(int(self.dut.o_queue_empty.value))

    def get_count(self) -> int:
        """Get number of entries in queue"""
        return int(self.dut.o_queue_count.value)

    def is_nearly_full(self) -> bool:
        """Check if queue is nearly full"""
        return bool(int(self.dut.o_queue_nearly_full.value))

    def has_underrun(self) -> bool:
        """Check if underrun occurred"""
        return bool(int(self.dut.o_queue_underrun.value))

    def has_overflow(self) -> bool:
        """Check if overflow occurred"""
        return bool(int(self.dut.o_queue_overflow.value))

    def is_dequeue_valid(self) -> bool:
        """Check if dequeued data is valid"""
        return bool(int(self.dut.o_dequeue_valid.value))

    def get_dequeued_instruction(self) -> int:
        """Get dequeued instruction"""
        return int(self.dut.o_instruction.value)

    def get_dequeued_src_addr(self) -> int:
        """Get dequeued source address"""
        return int(self.dut.o_src_addr.value)

    def get_dequeued_dst_addr(self) -> int:
        """Get dequeued destination address"""
        return int(self.dut.o_dst_addr.value)


def create_random_instruction() -> GPUInstruction:
    """Create a random GPU instruction for testing"""
    # Randomly choose instruction type
    instr_type = random.choice(list(GPUInstructionType))

    if instr_type == GPUInstructionType.SCALAR_COMPUTE:
        return GPUInstruction(
            scalar_vector_mode=0,
            write_mem=0,
            read_mem=0,
            multi_value=0,
            opcode=random.randint(0, 255),
            dest_reg=random.randint(0, 15),
            data_field=random.randint(0, 0xFFFFFFFFFFFFFFFF),
        )
    elif instr_type == GPUInstructionType.VECTOR_COMPUTE:
        return GPUInstruction(
            scalar_vector_mode=1,
            write_mem=0,
            read_mem=0,
            multi_value=0,
            opcode=random.randint(0, 255),
            dest_reg=random.randint(0, 15),
            data_field=random.randint(0, 0xFFFFFFFFFFFFFFFF),
        )
    elif instr_type == GPUInstructionType.MEMORY_READ:
        return GPUInstruction(
            scalar_vector_mode=random.randint(0, 1),
            write_mem=0,
            read_mem=1,
            multi_value=0,
            opcode=random.randint(0, 255),
            dest_reg=random.randint(0, 15),
            data_field=random.randint(0, 0xFFFFFFFFFFFFFFFF),
        )
    elif instr_type == GPUInstructionType.MEMORY_WRITE:
        return GPUInstruction(
            scalar_vector_mode=random.randint(0, 1),
            write_mem=1,
            read_mem=0,
            multi_value=0,
            opcode=random.randint(0, 255),
            dest_reg=random.randint(0, 15),
            data_field=random.randint(0, 0xFFFFFFFFFFFFFFFF),
        )
    else:  # MULTI_VALUE
        return GPUInstruction(
            scalar_vector_mode=random.randint(0, 1),
            write_mem=0,
            read_mem=0,
            multi_value=1,
            opcode=random.randint(0, 255),
            dest_reg=random.randint(0, 15),
            data_field=random.randint(0, 0xFFFFFFFFFFFFFFFF),
        )


@cocotb.test()
async def test_reset(dut):
    """Test reset behavior"""
    dut._log.info("=== Testing Reset Behavior ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # Check initial state after reset
    assert monitor.is_empty(), "Queue should be empty after reset"
    assert not monitor.is_full(), "Queue should not be full after reset"
    assert monitor.get_count() == 0, "Queue count should be 0 after reset"
    assert not monitor.is_nearly_full(), "Queue should not be nearly full after reset"
    assert not monitor.has_underrun(), "No underrun should be flagged after reset"
    assert not monitor.has_overflow(), "No overflow should be flagged after reset"
    assert not monitor.is_dequeue_valid(), "No valid data to dequeue after reset"

    dut._log.info("✓ Reset test passed")


@cocotb.test()
async def test_simple_enqueue_dequeue(dut):
    """Test simple enqueue and dequeue operations"""
    dut._log.info("=== Testing Simple Enqueue/Dequeue ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # Create a test instruction
    instr = GPUInstruction(
        scalar_vector_mode=0,
        write_mem=0,
        read_mem=0,
        multi_value=0,
        opcode=0x42,
        dest_reg=5,
        data_field=0xDEADBEEF,
    )

    # Enqueue the instruction
    await driver.enqueue(instr, 0x1000, 0x2000)

    # Check queue state
    assert not monitor.is_empty(), "Queue should not be empty after enqueue"
    assert monitor.get_count() == 1, "Queue should have 1 entry"
    assert monitor.is_dequeue_valid(), "Should have valid data to dequeue"

    # Check dequeued data
    dequeued_instr = monitor.get_dequeued_instruction()
    assert dequeued_instr == instr.to_bits(), "Dequeued instruction mismatch"
    assert monitor.get_dequeued_src_addr() == 0x1000, "Source address mismatch"
    assert monitor.get_dequeued_dst_addr() == 0x2000, "Destination address mismatch"

    # Dequeue the instruction
    await driver.dequeue()

    # Check queue is empty
    assert monitor.is_empty(), "Queue should be empty after dequeue"
    assert monitor.get_count() == 0, "Queue count should be 0"
    assert not monitor.is_dequeue_valid(), "No valid data after dequeue"

    dut._log.info("✓ Simple enqueue/dequeue test passed")


@cocotb.test()
async def test_queue_full(dut):
    """Test queue full condition"""
    dut._log.info("=== Testing Queue Full Condition ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    queue_depth = 32  # From parameter
    instructions = []

    # Fill the queue
    for i in range(queue_depth):
        instr = GPUInstruction(
            scalar_vector_mode=i % 2,
            write_mem=0,
            read_mem=0,
            multi_value=0,
            opcode=i,
            dest_reg=i % 16,
            data_field=0x1000 + i,
        )
        instructions.append(instr)
        await driver.enqueue(instr, 0x2000 + i, 0x3000 + i)

        if i < queue_depth - 1:
            assert not monitor.is_full(), f"Queue should not be full at entry {i + 1}"

    # Queue should be full now
    assert monitor.is_full(), "Queue should be full after filling"
    assert monitor.get_count() == min(31, queue_depth), (
        "Queue count should be at max displayable value"
    )
    assert monitor.is_nearly_full(), "Queue should be nearly full when full"

    # Try to enqueue when full (should trigger overflow)
    overflow_instr = create_random_instruction()
    await driver.enqueue(overflow_instr, 0x9000, 0xA000)

    # Check overflow flag
    assert monitor.has_overflow(), "Overflow should be flagged"

    # Dequeue one and check
    await driver.dequeue()
    assert not monitor.is_full(), "Queue should not be full after one dequeue"

    dut._log.info("✓ Queue full test passed")


@cocotb.test()
async def test_queue_empty_dequeue(dut):
    """Test dequeue from empty queue"""
    dut._log.info("=== Testing Empty Queue Dequeue ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # Try to dequeue from empty queue
    assert monitor.is_empty(), "Queue should be empty"
    await driver.dequeue()

    # Check underrun flag
    assert monitor.has_underrun(), "Underrun should be flagged"
    assert not monitor.is_dequeue_valid(), "No valid data on underrun"

    dut._log.info("✓ Empty queue dequeue test passed")


@cocotb.test()
async def test_simultaneous_operations(dut):
    """Test simultaneous enqueue and dequeue"""
    dut._log.info("=== Testing Simultaneous Operations ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # First fill with some data
    initial_instructions = []
    for i in range(5):
        instr = GPUInstruction(
            scalar_vector_mode=0,
            write_mem=0,
            read_mem=0,
            multi_value=0,
            opcode=i,
            dest_reg=i,
            data_field=0x100 * i,
        )
        initial_instructions.append(instr)
        await driver.enqueue(instr, 0x1000 * i, 0x2000 * i)

    initial_count = monitor.get_count()
    dut._log.info(f"Initial queue count: {initial_count}")

    # Simultaneous enqueue and dequeue
    new_instr = GPUInstruction(
        scalar_vector_mode=1,
        write_mem=0,
        read_mem=0,
        multi_value=0,
        opcode=0xFF,
        dest_reg=0xF,
        data_field=0xCAFEBABE,
    )

    await driver.enqueue_dequeue_simultaneous(new_instr, 0xAAAA, 0xBBBB)

    # Count should remain the same
    new_count = monitor.get_count()
    assert new_count == initial_count, f"Count changed: {initial_count} -> {new_count}"

    dut._log.info("✓ Simultaneous operations test passed")


@cocotb.test()
async def test_priority_levels(dut):
    """Test priority handling for different instruction types"""
    dut._log.info("=== Testing Priority Levels ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # Create instructions with different priorities
    instructions = [
        # Low priority scalar
        GPUInstruction(0, 0, 0, 0, 0x10, 1, 0x1000),
        # Medium priority vector
        GPUInstruction(1, 0, 0, 0, 0x20, 2, 0x2000),
        # High priority read
        GPUInstruction(0, 0, 1, 0, 0x30, 3, 0x3000),
        # Highest priority write
        GPUInstruction(0, 1, 0, 0, 0x40, 4, 0x4000),
    ]

    # Enqueue in reverse priority order
    for instr in instructions:
        await driver.enqueue(instr, 0x1000, 0x2000)
        dut._log.info(
            f"Enqueued: priority={instr.get_priority()}, type={instr.get_type().value}"
        )

    # Dequeue and verify FIFO order (not priority order in this simple queue)
    for i, expected_instr in enumerate(instructions):
        assert monitor.is_dequeue_valid(), f"Should have valid data at position {i}"
        dequeued = monitor.get_dequeued_instruction()
        assert dequeued == expected_instr.to_bits(), (
            f"Instruction mismatch at position {i}"
        )
        await driver.dequeue()

    dut._log.info("✓ Priority levels test passed (FIFO order maintained)")


@cocotb.test()
async def test_nearly_full_threshold(dut):
    """Test nearly full threshold detection"""
    dut._log.info("=== Testing Nearly Full Threshold ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    queue_depth = 32
    nearly_full_threshold = queue_depth - 4  # From module

    # Fill to just below threshold
    for i in range(nearly_full_threshold - 1):
        instr = create_random_instruction()
        await driver.enqueue(instr, 0x1000 + i, 0x2000 + i)

    assert not monitor.is_nearly_full(), "Should not be nearly full yet"

    # Add one more to reach threshold
    instr = create_random_instruction()
    await driver.enqueue(instr, 0x9000, 0xA000)

    assert monitor.is_nearly_full(), "Should be nearly full at threshold"
    assert not monitor.is_full(), "Should not be completely full yet"

    dut._log.info("✓ Nearly full threshold test passed")


@cocotb.test()
async def test_wrap_around(dut):
    """Test circular buffer wrap-around behavior"""
    dut._log.info("=== Testing Wrap-Around Behavior ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    queue_depth = 32

    # Multiple fill/empty cycles to test wrap-around
    for cycle in range(3):
        dut._log.info(f"Cycle {cycle + 1}")

        instructions = []

        # Fill queue
        for i in range(queue_depth):
            instr = GPUInstruction(
                scalar_vector_mode=cycle % 2,
                write_mem=0,
                read_mem=0,
                multi_value=0,
                opcode=(cycle * 100 + i) & 0xFF,
                dest_reg=i % 16,
                data_field=cycle * 0x10000 + i,
            )
            instructions.append(instr)
            await driver.enqueue(instr, 0x1000 * cycle + i, 0x2000 * cycle + i)

        assert monitor.is_full(), f"Queue should be full in cycle {cycle}"

        # Empty queue and verify data
        for i, expected_instr in enumerate(instructions):
            assert monitor.is_dequeue_valid(), f"Should have valid data at {i}"
            dequeued = monitor.get_dequeued_instruction()
            assert dequeued == expected_instr.to_bits(), f"Data mismatch at {i}"
            await driver.dequeue()

        assert monitor.is_empty(), f"Queue should be empty after cycle {cycle}"

    dut._log.info("✓ Wrap-around test passed")


@cocotb.test()
async def test_random_operations(dut):
    """Test random sequence of operations"""
    dut._log.info("=== Testing Random Operations ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # Track expected queue state
    expected_queue = []
    queue_depth = 32

    # Run random operations
    for i in range(100):
        can_enqueue = len(expected_queue) < queue_depth
        can_dequeue = len(expected_queue) > 0

        # Decide on operation
        if can_enqueue and can_dequeue:
            op = random.choice(["enqueue", "dequeue", "both", "idle"])
        elif can_enqueue:
            op = random.choice(["enqueue", "idle"])
        elif can_dequeue:
            op = random.choice(["dequeue", "idle"])
        else:
            op = "idle"

        # Execute operation
        if op == "enqueue":
            instr = create_random_instruction()
            src = random.randint(0, 0xFFFFFFFF)
            dst = random.randint(0, 0xFFFFFFFF)
            await driver.enqueue(instr, src, dst)
            expected_queue.append((instr, src, dst))

        elif op == "dequeue":
            await driver.dequeue()
            if expected_queue:
                expected_queue.pop(0)

        elif op == "both":
            instr = create_random_instruction()
            src = random.randint(0, 0xFFFFFFFF)
            dst = random.randint(0, 0xFFFFFFFF)
            await driver.enqueue_dequeue_simultaneous(instr, src, dst)
            if expected_queue:
                expected_queue.pop(0)
            expected_queue.append((instr, src, dst))

        else:  # idle
            await RisingEdge(dut.clk)

        # Verify queue state
        actual_empty = monitor.is_empty()
        expected_empty = len(expected_queue) == 0
        assert actual_empty == expected_empty, f"Empty mismatch at op {i}"

        actual_full = monitor.is_full()
        expected_full = len(expected_queue) >= queue_depth
        assert actual_full == expected_full, f"Full mismatch at op {i}"

    dut._log.info(f"✓ Random operations test passed ({100} operations)")


@cocotb.test()
async def test_instruction_types(dut):
    """Test all instruction types"""
    dut._log.info("=== Testing All Instruction Types ===")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    driver = GPUOpQueueDriver(dut)
    monitor = GPUOpQueueMonitor(dut)

    await driver.reset()

    # Test each instruction type
    test_cases = [
        ("Scalar Compute", GPUInstruction(0, 0, 0, 0, 0x01, 1, 0x1111)),
        ("Vector Compute", GPUInstruction(1, 0, 0, 0, 0x02, 2, 0x2222)),
        ("Memory Read", GPUInstruction(0, 0, 1, 0, 0x03, 3, 0x3333)),
        ("Memory Write", GPUInstruction(0, 1, 0, 0, 0x04, 4, 0x4444)),
        ("Multi-Value", GPUInstruction(0, 0, 0, 1, 0x05, 5, 0x5555)),
        ("Vector Memory Read", GPUInstruction(1, 0, 1, 0, 0x06, 6, 0x6666)),
        ("Vector Memory Write", GPUInstruction(1, 1, 0, 0, 0x07, 7, 0x7777)),
    ]

    # Enqueue all instruction types
    for name, instr in test_cases:
        await driver.enqueue(instr, 0x1000, 0x2000)
        dut._log.info(f"Enqueued: {name} (priority={instr.get_priority()})")

    # Dequeue and verify
    for name, expected_instr in test_cases:
        assert monitor.is_dequeue_valid(), f"Should have valid data for {name}"
        dequeued = monitor.get_dequeued_instruction()
        assert dequeued == expected_instr.to_bits(), f"Mismatch for {name}"
        await driver.dequeue()
        dut._log.info(f"Dequeued: {name}")

    assert monitor.is_empty(), "Queue should be empty after all dequeues"

    dut._log.info("✓ All instruction types test passed")
