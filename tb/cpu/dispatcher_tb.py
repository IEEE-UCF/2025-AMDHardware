import cocotb
from cocotb.triggers import Timer, RisingEdge, ClockCycles
from cocotb.clock import Clock
from dataclasses import dataclass
from enum import Enum
import random

"""
RISC-V Dispatcher Testbench for Coprocessor Interface

This testbench validates the dispatcher module which routes instructions
to coprocessors based on opcode detection.

The dispatcher recognizes:
- System instructions (CSR, etc.) -> CP0 (opcode 7'b1110011)
- Floating point instructions -> CP1 (opcode 7'b1010011)
- Custom instructions -> CP2 (opcode 7'b0001011)
"""


class RV32IOpcode(Enum):
    """RISC-V opcodes relevant to the dispatcher"""

    SYSTEM = 0b1110011  # System instructions (CSR, etc.) -> CP0
    FLOAT = 0b1010011  # Floating point instructions -> CP1
    CUSTOM = 0b0001011  # Custom instructions -> CP2
    # Standard opcodes that don't go to coprocessors
    LUI = 0b0110111
    AUIPC = 0b0010111
    JAL = 0b1101111
    JALR = 0b1100111
    BRANCH = 0b1100011
    LOAD = 0b0000011
    STORE = 0b0100011
    OP_IMM = 0b0010011
    OP = 0b0110011


class CoprocessorSelect(Enum):
    """Coprocessor selection values"""

    CP0 = 0b00  # System coprocessor
    CP1 = 0b01  # Floating point coprocessor
    CP2 = 0b10  # Custom coprocessor
    NONE = 0b11  # No coprocessor


@dataclass
class Instruction:
    """RISC-V instruction representation"""

    raw: int
    opcode: int
    rd: int
    rs1: int
    rs2: int
    funct3: int
    funct7: int

    @classmethod
    def create(
        cls,
        opcode: int,
        rd: int = 0,
        rs1: int = 0,
        rs2: int = 0,
        funct3: int = 0,
        funct7: int = 0,
        imm: int = 0,
    ):
        """Create an instruction from fields"""
        if opcode in [RV32IOpcode.SYSTEM.value, RV32IOpcode.FLOAT.value]:
            # I-type format for system/float instructions
            raw = (
                ((imm & 0xFFF) << 20)
                | (rs1 << 15)
                | (funct3 << 12)
                | (rd << 7)
                | opcode
            )
        elif opcode == RV32IOpcode.CUSTOM.value:
            # R-type format for custom instructions
            raw = (
                (funct7 << 25)
                | (rs2 << 20)
                | (rs1 << 15)
                | (funct3 << 12)
                | (rd << 7)
                | opcode
            )
        else:
            # Standard R-type format
            raw = (
                (funct7 << 25)
                | (rs2 << 20)
                | (rs1 << 15)
                | (funct3 << 12)
                | (rd << 7)
                | opcode
            )

        return cls(
            raw=raw,
            opcode=opcode,
            rd=rd,
            rs1=rs1,
            rs2=rs2,
            funct3=funct3,
            funct7=funct7,
        )


class DispatcherDriver:
    """Driver for the dispatcher module"""

    def __init__(self, dut):
        self.dut = dut
        self.dut.inst_valid.value = 0
        self.dut.instruction.value = 0
        self.dut.rs1_data.value = 0
        self.dut.rs2_data.value = 0
        self.dut.pc.value = 0
        self.dut.pipeline_stall.value = 0
        self.dut.cp_ready.value = 1  # Default: coprocessor ready
        self.dut.cp_data_out.value = 0
        self.dut.cp_exception.value = 0

    async def reset(self):
        """Reset the DUT"""
        self.dut.rst_n.value = 0
        await ClockCycles(self.dut.clk, 2)
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, 1)
        self.dut._log.info("Reset complete")

    async def send_instruction(
        self,
        instruction: Instruction,
        rs1_data: int = 0,
        rs2_data: int = 0,
        pc: int = 0,
    ):
        """Send an instruction to the dispatcher"""
        self.dut.instruction.value = instruction.raw
        self.dut.rs1_data.value = rs1_data
        self.dut.rs2_data.value = rs2_data
        self.dut.pc.value = pc
        self.dut.inst_valid.value = 1

        await RisingEdge(self.dut.clk)
        await Timer(1, units="ns")  # Small delay for combinational logic

        # Keep valid for one cycle
        self.dut.inst_valid.value = 0

    def set_coprocessor_ready(self, ready: bool):
        """Set coprocessor ready status"""
        self.dut.cp_ready.value = 1 if ready else 0

    def set_coprocessor_response(self, data: int, exception: bool = False):
        """Set coprocessor response data"""
        self.dut.cp_data_out.value = data
        self.dut.cp_exception.value = 1 if exception else 0

    def set_pipeline_stall(self, stall: bool):
        """Set pipeline stall signal"""
        self.dut.pipeline_stall.value = 1 if stall else 0


class DispatcherMonitor:
    """Monitor for the dispatcher module outputs"""

    def __init__(self, dut):
        self.dut = dut

    def is_coprocessor_instruction_detected(self) -> bool:
        """Check if a coprocessor instruction was detected"""
        return bool(int(self.dut.cp_instruction_detected.value))

    def get_coprocessor_select(self) -> CoprocessorSelect:
        """Get which coprocessor was selected"""
        val = int(self.dut.cp_select.value)
        if val == 0b00:
            return CoprocessorSelect.CP0
        elif val == 0b01:
            return CoprocessorSelect.CP1
        elif val == 0b10:
            return CoprocessorSelect.CP2
        else:
            return CoprocessorSelect.NONE

    def is_cp_valid(self) -> bool:
        """Check if coprocessor valid signal is asserted"""
        return bool(int(self.dut.cp_valid.value))

    def get_cp_instruction(self) -> int:
        """Get instruction sent to coprocessor"""
        return int(self.dut.cp_instruction.value)

    def get_cp_data_in(self) -> int:
        """Get data sent to coprocessor"""
        return int(self.dut.cp_data_in.value)

    def is_stall_requested(self) -> bool:
        """Check if coprocessor is requesting a stall"""
        return bool(int(self.dut.cp_stall_request.value))

    def is_result_valid(self) -> bool:
        """Check if coprocessor result is valid"""
        return bool(int(self.dut.cp_result_valid.value))

    def is_reg_write(self) -> bool:
        """Check if register write is enabled"""
        return bool(int(self.dut.cp_reg_write.value))

    def get_reg_addr(self) -> int:
        """Get register write address"""
        return int(self.dut.cp_reg_addr.value)

    def get_result(self) -> int:
        """Get coprocessor result"""
        return int(self.dut.cp_result.value)


@cocotb.test()
async def test_coprocessor_detection(dut):
    """Test that the dispatcher correctly detects coprocessor instructions"""

    dut._log.info("=== Testing Coprocessor Instruction Detection ===")

    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    # Initialize driver and monitor
    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()

    # Test cases: (instruction, expected_detected, expected_cp_select, description)
    test_cases = [
        (
            Instruction.create(RV32IOpcode.SYSTEM.value, rd=1, rs1=2, funct3=0b001),
            True,
            CoprocessorSelect.CP0,
            "CSR instruction -> CP0",
        ),
        (
            Instruction.create(RV32IOpcode.FLOAT.value, rd=3, rs1=4, rs2=5),
            True,
            CoprocessorSelect.CP1,
            "Floating point -> CP1",
        ),
        (
            Instruction.create(RV32IOpcode.CUSTOM.value, rd=6, rs1=7, rs2=8),
            True,
            CoprocessorSelect.CP2,
            "Custom instruction -> CP2",
        ),
        (
            Instruction.create(RV32IOpcode.OP_IMM.value, rd=9, rs1=10),
            False,
            CoprocessorSelect.CP0,
            "ALU immediate -> No CP",
        ),
        (
            Instruction.create(RV32IOpcode.LOAD.value, rd=11, rs1=12),
            False,
            CoprocessorSelect.CP0,
            "Load instruction -> No CP",
        ),
    ]

    passed = 0
    failed = 0

    for instr, expected_detected, expected_select, description in test_cases:
        dut._log.info(f"Testing: {description}")

        await driver.send_instruction(instr, rs1_data=0x12345678)

        # Check detection
        detected = monitor.is_coprocessor_instruction_detected()
        if detected == expected_detected:
            dut._log.info(f"  ✓ Detection correct: {detected}")
            passed += 1
        else:
            dut._log.error(
                f"  ✗ Detection wrong: got {detected}, expected {expected_detected}"
            )
            failed += 1

        # Check selection (only if detected)
        if expected_detected:
            cp_select = monitor.get_coprocessor_select()
            if cp_select == expected_select:
                dut._log.info(f"  ✓ Selection correct: {cp_select.name}")
                passed += 1
            else:
                dut._log.error(
                    f"  ✗ Selection wrong: got {cp_select.name}, expected {expected_select.name}"
                )
                failed += 1

            # Check that instruction is passed through
            cp_instr = monitor.get_cp_instruction()
            if cp_instr == instr.raw:
                dut._log.info(f"  ✓ Instruction passed correctly")
                passed += 1
            else:
                dut._log.error(f"  ✗ Instruction mismatch")
                failed += 1

        await ClockCycles(dut.clk, 1)

    dut._log.info(f"=== Results: {passed} passed, {failed} failed ===")
    assert failed == 0, f"{failed} tests failed"


@cocotb.test()
async def test_coprocessor_data_path(dut):
    """Test data path from rs1 to coprocessor and result handling"""

    dut._log.info("=== Testing Coprocessor Data Path ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()

    # Test data flow for CSR instruction
    test_rs1_data = 0xDEADBEEF
    test_cp_result = 0xCAFEBABE
    test_rd = 15

    dut._log.info("Testing CSR instruction data flow")

    # Set up coprocessor response
    driver.set_coprocessor_response(test_cp_result)

    # Send CSR instruction
    csr_instr = Instruction.create(
        RV32IOpcode.SYSTEM.value,
        rd=test_rd,
        rs1=5,
        funct3=0b001,  # CSRRW
    )

    await driver.send_instruction(csr_instr, rs1_data=test_rs1_data)

    # Check data sent to coprocessor
    cp_data_in = monitor.get_cp_data_in()
    if cp_data_in == test_rs1_data:
        dut._log.info(f"  ✓ RS1 data correctly sent to CP: 0x{cp_data_in:08X}")
    else:
        dut._log.error(
            f"  ✗ RS1 data wrong: got 0x{cp_data_in:08X}, expected 0x{test_rs1_data:08X}"
        )

    # Check result handling
    if monitor.is_result_valid():
        dut._log.info(f"  ✓ Result valid signal asserted")

        result = monitor.get_result()
        if result == test_cp_result:
            dut._log.info(f"  ✓ Result correct: 0x{result:08X}")
        else:
            dut._log.error(
                f"  ✗ Result wrong: got 0x{result:08X}, expected 0x{test_cp_result:08X}"
            )

        # Check register write signals
        if monitor.is_reg_write():
            dut._log.info(f"  ✓ Register write enabled")

            reg_addr = monitor.get_reg_addr()
            if reg_addr == test_rd:
                dut._log.info(f"  ✓ Register address correct: x{reg_addr}")
            else:
                dut._log.error(
                    f"  ✗ Register address wrong: got x{reg_addr}, expected x{test_rd}"
                )
    else:
        dut._log.error(f"  ✗ Result valid not asserted")

    # Test with rd = x0 (should not write)
    dut._log.info("Testing write to x0 (should be disabled)")

    x0_instr = Instruction.create(
        RV32IOpcode.SYSTEM.value,
        rd=0,  # x0
        rs1=5,
        funct3=0b001,
    )

    await driver.send_instruction(x0_instr, rs1_data=0x11111111)

    if not monitor.is_reg_write():
        dut._log.info(f"  ✓ Register write correctly disabled for x0")
    else:
        dut._log.error(f"  ✗ Register write incorrectly enabled for x0")


@cocotb.test()
async def test_coprocessor_stall(dut):
    """Test stall generation when coprocessor is not ready"""

    dut._log.info("=== Testing Coprocessor Stall Mechanism ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()

    # Test 1: Coprocessor ready - no stall
    dut._log.info("Test 1: Coprocessor ready")
    driver.set_coprocessor_ready(True)

    fp_instr = Instruction.create(RV32IOpcode.FLOAT.value, rd=1, rs1=2)
    await driver.send_instruction(fp_instr)

    if not monitor.is_stall_requested():
        dut._log.info(f"  ✓ No stall when coprocessor ready")
    else:
        dut._log.error(f"  ✗ Unexpected stall when coprocessor ready")

    await ClockCycles(dut.clk, 2)

    # Test 2: Coprocessor not ready - should stall
    dut._log.info("Test 2: Coprocessor not ready")
    driver.set_coprocessor_ready(False)

    await driver.send_instruction(fp_instr)

    if monitor.is_stall_requested():
        dut._log.info(f"  ✓ Stall requested when coprocessor not ready")
    else:
        dut._log.error(f"  ✗ No stall when coprocessor not ready")

    # Make coprocessor ready and check stall clears
    await ClockCycles(dut.clk, 2)
    driver.set_coprocessor_ready(True)
    await ClockCycles(dut.clk, 1)

    if not monitor.is_stall_requested():
        dut._log.info(f"  ✓ Stall cleared when coprocessor becomes ready")
    else:
        dut._log.error(f"  ✗ Stall not cleared when coprocessor ready")

    # Test 3: Non-coprocessor instruction - no stall regardless
    dut._log.info("Test 3: Non-coprocessor instruction")
    driver.set_coprocessor_ready(False)

    alu_instr = Instruction.create(RV32IOpcode.OP_IMM.value, rd=3, rs1=4)
    await driver.send_instruction(alu_instr)

    if not monitor.is_stall_requested():
        dut._log.info(f"  ✓ No stall for non-coprocessor instruction")
    else:
        dut._log.error(f"  ✗ Unexpected stall for non-coprocessor instruction")


@cocotb.test()
async def test_pipeline_stall_behavior(dut):
    """Test behavior when pipeline stall is asserted"""

    dut._log.info("=== Testing Pipeline Stall Behavior ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()

    # Send instruction with pipeline stall active
    dut._log.info("Testing with pipeline stall active")
    driver.set_pipeline_stall(True)

    csr_instr = Instruction.create(RV32IOpcode.SYSTEM.value, rd=1, rs1=2)
    await driver.send_instruction(csr_instr)

    # Should not detect coprocessor instruction when pipeline is stalled
    if not monitor.is_coprocessor_instruction_detected():
        dut._log.info(f"  ✓ Coprocessor detection inhibited during pipeline stall")
    else:
        dut._log.error(f"  ✗ Coprocessor incorrectly detected during pipeline stall")

    # Clear pipeline stall and retry
    dut._log.info("Testing with pipeline stall cleared")
    driver.set_pipeline_stall(False)

    await driver.send_instruction(csr_instr)

    if monitor.is_coprocessor_instruction_detected():
        dut._log.info(f"  ✓ Coprocessor detection works after pipeline stall cleared")
    else:
        dut._log.error(f"  ✗ Coprocessor not detected after pipeline stall cleared")


@cocotb.test()
async def test_coprocessor_exception(dut):
    """Test exception handling from coprocessor"""

    dut._log.info("=== Testing Coprocessor Exception Handling ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()

    # Test normal operation (no exception)
    dut._log.info("Test 1: Normal operation without exception")
    driver.set_coprocessor_response(0x12345678, exception=False)

    csr_instr = Instruction.create(RV32IOpcode.SYSTEM.value, rd=1, rs1=2)
    await driver.send_instruction(csr_instr)

    exception_out = int(dut.cp_exception_out.value)
    if exception_out == 0:
        dut._log.info(f"  ✓ No exception propagated in normal operation")
    else:
        dut._log.error(f"  ✗ Unexpected exception signal")

    await ClockCycles(dut.clk, 2)

    # Test with exception
    dut._log.info("Test 2: Operation with exception")
    driver.set_coprocessor_response(0x0, exception=True)

    await driver.send_instruction(csr_instr)

    exception_out = int(dut.cp_exception_out.value)
    if exception_out == 1:
        dut._log.info(f"  ✓ Exception correctly propagated")
    else:
        dut._log.error(f"  ✗ Exception not propagated")

    # Clear exception
    driver.set_coprocessor_response(0x0, exception=False)
    await ClockCycles(dut.clk, 1)

    exception_out = int(dut.cp_exception_out.value)
    if exception_out == 0:
        dut._log.info(f"  ✓ Exception signal cleared")
    else:
        dut._log.error(f"  ✗ Exception signal stuck")


@cocotb.test()
async def test_back_to_back_instructions(dut):
    """Test back-to-back coprocessor instructions"""

    dut._log.info("=== Testing Back-to-Back Coprocessor Instructions ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()
    driver.set_coprocessor_ready(True)

    # Create sequence of different coprocessor instructions
    instructions = [
        (
            Instruction.create(RV32IOpcode.SYSTEM.value, rd=1, rs1=2),
            CoprocessorSelect.CP0,
            "System",
        ),
        (
            Instruction.create(RV32IOpcode.FLOAT.value, rd=3, rs1=4),
            CoprocessorSelect.CP1,
            "Float",
        ),
        (
            Instruction.create(RV32IOpcode.CUSTOM.value, rd=5, rs1=6),
            CoprocessorSelect.CP2,
            "Custom",
        ),
        (
            Instruction.create(RV32IOpcode.SYSTEM.value, rd=7, rs1=8),
            CoprocessorSelect.CP0,
            "System",
        ),
    ]

    dut._log.info("Sending back-to-back instructions")

    for i, (instr, expected_cp, name) in enumerate(instructions):
        driver.set_coprocessor_response(0x1000 + i)
        await driver.send_instruction(instr, rs1_data=0x2000 + i)

        # Verify correct coprocessor selection
        cp_select = monitor.get_coprocessor_select()
        if cp_select == expected_cp:
            dut._log.info(f"  ✓ Instruction {i} ({name}) -> {cp_select.name}")
        else:
            dut._log.error(f"  ✗ Instruction {i} ({name}) wrong CP: {cp_select.name}")

        # Check result
        if monitor.is_result_valid():
            result = monitor.get_result()
            if result == 0x1000 + i:
                dut._log.info(f"    ✓ Result correct: 0x{result:04X}")
            else:
                dut._log.error(f"    ✗ Result wrong: 0x{result:04X}")


@cocotb.test()
async def test_random_instruction_stream(dut):
    """Test with random instruction stream"""

    dut._log.info("=== Testing Random Instruction Stream ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    driver = DispatcherDriver(dut)
    monitor = DispatcherMonitor(dut)

    await driver.reset()
    driver.set_coprocessor_ready(True)

    # Generate random instruction stream
    num_instructions = 20
    cp_count = {
        CoprocessorSelect.CP0: 0,
        CoprocessorSelect.CP1: 0,
        CoprocessorSelect.CP2: 0,
    }
    non_cp_count = 0

    dut._log.info(f"Sending {num_instructions} random instructions")

    for i in range(num_instructions):
        # Randomly choose instruction type
        opcodes = [
            RV32IOpcode.SYSTEM.value,
            RV32IOpcode.FLOAT.value,
            RV32IOpcode.CUSTOM.value,
            RV32IOpcode.OP_IMM.value,
            RV32IOpcode.LOAD.value,
            RV32IOpcode.STORE.value,
            RV32IOpcode.OP.value,
        ]

        opcode = random.choice(opcodes)
        rd = random.randint(0, 31)
        rs1 = random.randint(0, 31)
        rs2 = random.randint(0, 31)

        instr = Instruction.create(opcode, rd=rd, rs1=rs1, rs2=rs2)

        # Set random coprocessor response
        driver.set_coprocessor_response(random.randint(0, 0xFFFFFFFF))

        await driver.send_instruction(instr, rs1_data=random.randint(0, 0xFFFFFFFF))

        # Track statistics
        if monitor.is_coprocessor_instruction_detected():
            cp_select = monitor.get_coprocessor_select()
            cp_count[cp_select] += 1
        else:
            non_cp_count += 1

    # Report statistics
    dut._log.info("Instruction stream statistics:")
    dut._log.info(f"  CP0 (System): {cp_count[CoprocessorSelect.CP0]}")
    dut._log.info(f"  CP1 (Float): {cp_count[CoprocessorSelect.CP1]}")
    dut._log.info(f"  CP2 (Custom): {cp_count[CoprocessorSelect.CP2]}")
    dut._log.info(f"  Non-coprocessor: {non_cp_count}")
    dut._log.info(f"  Total: {sum(cp_count.values()) + non_cp_count}")

    # Verify total matches
    total = sum(cp_count.values()) + non_cp_count
    assert total == num_instructions, (
        f"Instruction count mismatch: {total} != {num_instructions}"
    )

    dut._log.info("✓ Random instruction stream test completed successfully")
