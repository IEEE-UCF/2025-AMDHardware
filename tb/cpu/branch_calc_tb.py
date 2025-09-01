import cocotb
import random
from cocotb.triggers import Timer

# RISC-V RV32I ISA Specification-based Branch Calculation Test
# Tests branch address calculation according to RISC-V ISA specification


class RV32IBranchSpec:
    """RISC-V RV32I Branch and Jump Address Calculation Specification"""

    # RISC-V RV32I Opcodes for control flow instructions
    OP_JAL = 0b1101111  # Jump and Link
    OP_JALR = 0b1100111  # Jump and Link Register
    OP_BRANCH = 0b1100011  # Branch instructions

    @staticmethod
    def encode_b_type(opcode, funct3, rs1, rs2, imm):
        """Encode B-type instruction (branches) per RISC-V ISA"""
        return (
            (((imm >> 12) & 1) << 31)
            | (((imm >> 5) & 0x3F) << 25)
            | (rs2 << 20)
            | (rs1 << 15)
            | (funct3 << 12)
            | (((imm >> 1) & 0xF) << 8)
            | (((imm >> 11) & 1) << 7)
            | opcode
        )

    @staticmethod
    def encode_j_type(opcode, rd, imm):
        """Encode J-type instruction (JAL) per RISC-V ISA"""
        return (
            (((imm >> 20) & 1) << 31)
            | (((imm >> 1) & 0x3FF) << 21)
            | (((imm >> 11) & 1) << 20)
            | (((imm >> 12) & 0xFF) << 12)
            | (rd << 7)
            | opcode
        )

    @staticmethod
    def encode_i_type(opcode, rd, funct3, rs1, imm):
        """Encode I-type instruction (JALR) per RISC-V ISA"""
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

    @staticmethod
    def extract_b_immediate(instruction):
        """Extract B-type immediate from instruction per RISC-V ISA"""
        imm = (
            (((instruction >> 31) & 1) << 12)
            | (((instruction >> 7) & 1) << 11)
            | (((instruction >> 25) & 0x3F) << 5)
            | (((instruction >> 8) & 0xF) << 1)
        )
        # Sign extend from 13 bits to 32 bits
        if imm & 0x1000:  # Check bit 12 (sign bit)
            imm |= 0xFFFFF000
        return imm & 0xFFFFFFFF

    @staticmethod
    def extract_j_immediate(instruction):
        """Extract J-type immediate from instruction per RISC-V ISA"""
        imm = (
            (((instruction >> 31) & 1) << 20)
            | (((instruction >> 12) & 0xFF) << 12)
            | (((instruction >> 20) & 1) << 11)
            | (((instruction >> 21) & 0x3FF) << 1)
        )
        # Sign extend from 21 bits to 32 bits
        if imm & 0x100000:  # Check bit 20 (sign bit)
            imm |= 0xFFE00000
        return imm & 0xFFFFFFFF

    @staticmethod
    def extract_i_immediate(instruction):
        """Extract I-type immediate from instruction per RISC-V ISA"""
        imm = (instruction >> 20) & 0xFFF
        # Sign extend from 12 bits to 32 bits
        if imm & 0x800:  # Check bit 11 (sign bit)
            imm |= 0xFFFFF000
        return imm & 0xFFFFFFFF

    @staticmethod
    def calculate_branch_address(pc, instruction):
        """Calculate branch target address per RISC-V ISA"""
        imm = RV32IBranchSpec.extract_b_immediate(instruction)
        return (pc + imm) & 0xFFFFFFFF

    @staticmethod
    def calculate_jal_address(pc, instruction):
        """Calculate JAL target address per RISC-V ISA"""
        imm = RV32IBranchSpec.extract_j_immediate(instruction)
        return (pc + imm) & 0xFFFFFFFF

    @staticmethod
    def calculate_jalr_address(data_a, instruction):
        """Calculate JALR target address per RISC-V ISA"""
        imm = RV32IBranchSpec.extract_i_immediate(instruction)
        # JALR sets LSB to 0 per ISA specification
        target = (data_a + imm) & 0xFFFFFFFE
        return target & 0xFFFFFFFF


@cocotb.test()
async def test_risc_v_branch_address_calculation(dut):
    """Test branch address calculation compliance with RISC-V RV32I ISA"""

    spec = RV32IBranchSpec()
    dut._log.info("=== Testing RISC-V RV32I Branch Address Calculation ===")

    # Test parameters
    num_tests_per_type = 100
    total_tests = 0
    passed_tests = 0

    # Test B-type branch instructions
    dut._log.info("Testing B-type branch address calculation...")

    branch_ops = [
        (0b000, "BEQ"),  # Branch if Equal
        (0b001, "BNE"),  # Branch if Not Equal
        (0b100, "BLT"),  # Branch if Less Than
        (0b101, "BGE"),  # Branch if Greater or Equal
        (0b110, "BLTU"),  # Branch if Less Than Unsigned
        (0b111, "BGEU"),  # Branch if Greater or Equal Unsigned
    ]

    for funct3, name in branch_ops:
        for i in range(num_tests_per_type):
            # Generate random test values
            pc = random.randint(0, 0xFFFFFFFF) & ~3  # Word-aligned PC
            rs1 = random.randint(0, 31)
            rs2 = random.randint(0, 31)

            # Generate valid branch offset (must be even, ±4KB range for reasonable testing)
            imm = random.randint(-2048, 2047) & ~1  # Even offsets only

            # Encode B-type instruction
            instruction = spec.encode_b_type(spec.OP_BRANCH, funct3, rs1, rs2, imm)

            # Calculate expected branch address per RISC-V ISA
            expected_bra_addr = spec.calculate_branch_address(pc, instruction)

            # Set DUT inputs
            dut.pc.value = pc
            dut.inst.value = instruction
            dut.data_a.value = 0  # Not used for branch calculation

            await Timer(1, units="ns")

            # Check branch address calculation
            dut_bra_addr = int(dut.bra_addr.value) & 0xFFFFFFFF

            total_tests += 1
            if dut_bra_addr == expected_bra_addr:
                passed_tests += 1
            else:
                dut._log.error(f"BRANCH FAIL: {name} rs{rs1}, rs{rs2}, {imm}")
                dut._log.error(f"  PC: 0x{pc:08x}")
                dut._log.error(f"  Instruction: 0x{instruction:08x}")
                dut._log.error(f"  Expected bra_addr: 0x{expected_bra_addr:08x}")
                dut._log.error(f"  Got bra_addr:      0x{dut_bra_addr:08x}")
                dut._log.error(f"  Immediate: {imm} (0x{imm & 0xFFFF:04x})")

                if total_tests - passed_tests >= 10:  # Limit error spam
                    break

        if total_tests - passed_tests >= 10:
            break

    # Test J-type JAL instructions
    dut._log.info("Testing J-type JAL address calculation...")

    for i in range(num_tests_per_type):
        # Generate random test values
        pc = random.randint(0, 0xFFFFFFFF) & ~3  # Word-aligned PC
        rd = random.randint(0, 31)

        # Generate valid JAL offset (must be even, ±1MB range for testing)
        imm = random.randint(-524288, 524287) & ~1  # Even offsets only

        # Encode J-type instruction
        instruction = spec.encode_j_type(spec.OP_JAL, rd, imm)

        # Calculate expected JAL address per RISC-V ISA
        expected_jal_addr = spec.calculate_jal_address(pc, instruction)

        # Set DUT inputs
        dut.pc.value = pc
        dut.inst.value = instruction
        dut.data_a.value = 0  # Not used for JAL calculation

        await Timer(1, units="ns")

        # Check JAL address calculation
        dut_jal_addr = int(dut.jal_addr.value) & 0xFFFFFFFF

        total_tests += 1
        if dut_jal_addr == expected_jal_addr:
            passed_tests += 1
        else:
            dut._log.error(f"JAL FAIL: JAL x{rd}, {imm}")
            dut._log.error(f"  PC: 0x{pc:08x}")
            dut._log.error(f"  Instruction: 0x{instruction:08x}")
            dut._log.error(f"  Expected jal_addr: 0x{expected_jal_addr:08x}")
            dut._log.error(f"  Got jal_addr:      0x{dut_jal_addr:08x}")
            dut._log.error(f"  Immediate: {imm} (0x{imm & 0xFFFFF:05x})")

            if total_tests - passed_tests >= 10:
                break

    # Test I-type JALR instructions
    dut._log.info("Testing I-type JALR address calculation...")

    for i in range(num_tests_per_type):
        # Generate random test values
        pc = random.randint(0, 0xFFFFFFFF) & ~3  # Word-aligned PC (not used for JALR)
        rd = random.randint(0, 31)
        rs1 = random.randint(0, 31)
        data_a = random.randint(0, 0xFFFFFFFF)  # Base register value

        # Generate valid JALR offset (12-bit signed immediate)
        imm = random.randint(-2048, 2047)

        # Encode I-type JALR instruction
        instruction = spec.encode_i_type(spec.OP_JALR, rd, 0b000, rs1, imm)

        # Calculate expected JALR address per RISC-V ISA
        expected_jalr_addr = spec.calculate_jalr_address(data_a, instruction)

        # Set DUT inputs
        dut.pc.value = pc
        dut.inst.value = instruction
        dut.data_a.value = data_a  # Base address for JALR

        await Timer(1, units="ns")

        # Check JALR address calculation
        dut_jalr_addr = int(dut.jalr_addr.value) & 0xFFFFFFFF

        total_tests += 1
        if dut_jalr_addr == expected_jalr_addr:
            passed_tests += 1
        else:
            dut._log.error(f"JALR FAIL: JALR x{rd}, x{rs1}, {imm}")
            dut._log.error(f"  PC: 0x{pc:08x}")
            dut._log.error(f"  Instruction: 0x{instruction:08x}")
            dut._log.error(f"  data_a: 0x{data_a:08x}")
            dut._log.error(f"  Expected jalr_addr: 0x{expected_jalr_addr:08x}")
            dut._log.error(f"  Got jalr_addr:      0x{dut_jalr_addr:08x}")
            dut._log.error(f"  Immediate: {imm} (0x{imm & 0xFFF:03x})")
            dut._log.error(
                f"  Raw calculation: 0x{(data_a + imm):08x} -> 0x{expected_jalr_addr:0x}"
            )

            if total_tests - passed_tests >= 10:
                break

    # Test results
    failed_tests = total_tests - passed_tests

    dut._log.info("=== RISC-V Branch Calculation Results ===")
    dut._log.info(f"Total tests: {total_tests}")
    dut._log.info(f"Passed: {passed_tests}")
    dut._log.info(f"Failed: {failed_tests}")

    if failed_tests == 0:
        dut._log.info("✓ Branch calculation module is RISC-V RV32I ISA compliant!")
    else:
        dut._log.error("✗ Branch calculation module has ISA compliance issues")
        assert False, f"Branch calculation failed {failed_tests} ISA compliance tests"


@cocotb.test()
async def test_specific_risc_v_cases(dut):
    """Test specific RISC-V branch calculation cases from ISA examples"""

    spec = RV32IBranchSpec()
    dut._log.info("=== Testing Specific RISC-V Cases ===")

    # Test case 1: Simple forward branch
    # BEQ x1, x2, 8  (branch forward 8 bytes = 2 instructions)
    pc = 0x1000
    instruction = spec.encode_b_type(spec.OP_BRANCH, 0b000, 1, 2, 8)
    expected_addr = pc + 8

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.bra_addr.value) == expected_addr, (
        f"BEQ forward branch: expected 0x{expected_addr:08x}, got 0x{int(dut.bra_addr.value):08x}"
    )

    # Test case 2: Backward branch
    # BNE x3, x4, -12  (branch backward 12 bytes = 3 instructions)
    pc = 0x2000
    instruction = spec.encode_b_type(spec.OP_BRANCH, 0b001, 3, 4, -12)
    expected_addr = (pc - 12) & 0xFFFFFFFF

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.bra_addr.value) == expected_addr, (
        f"BNE backward branch: expected 0x{expected_addr:08x}, got 0x{int(dut.bra_addr.value):08x}"
    )

    # Test case 3: JAL forward jump
    # JAL x1, 1024  (jump forward 1024 bytes)
    pc = 0x3000
    instruction = spec.encode_j_type(spec.OP_JAL, 1, 1024)
    expected_addr = pc + 1024

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.jal_addr.value) == expected_addr, (
        f"JAL forward jump: expected 0x{expected_addr:08x}, got 0x{int(dut.jal_addr.value):08x}"
    )

    # Test case 4: JAL backward jump
    # JAL x5, -2048  (jump backward 2048 bytes)
    pc = 0x4000
    instruction = spec.encode_j_type(spec.OP_JAL, 5, -2048)
    expected_addr = (pc - 2048) & 0xFFFFFFFF

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.jal_addr.value) == expected_addr, (
        f"JAL backward jump: expected 0x{expected_addr:08x}, got 0x{int(dut.jal_addr.value):08x}"
    )

    # Test case 5: JALR with positive offset
    # JALR x2, x10, 100  (jump to x10 + 100, clear LSB)
    pc = 0x5000
    base_addr = 0x12345678
    instruction = spec.encode_i_type(spec.OP_JALR, 2, 0b000, 10, 100)
    expected_addr = (base_addr + 100) & 0xFFFFFFFE  # Clear LSB per RISC-V spec

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = base_addr
    await Timer(1, units="ns")

    assert int(dut.jalr_addr.value) == expected_addr, (
        f"JALR positive offset: expected 0x{expected_addr:08x}, got 0x{int(dut.jalr_addr.value):08x}"
    )

    # Test case 6: JALR with negative offset
    # JALR x7, x15, -500  (jump to x15 - 500, clear LSB)
    pc = 0x6000
    base_addr = 0xABCDEF00
    instruction = spec.encode_i_type(spec.OP_JALR, 7, 0b000, 15, -500)
    expected_addr = ((base_addr - 500) & 0xFFFFFFFF) & 0xFFFFFFFE

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = base_addr
    await Timer(1, units="ns")

    assert int(dut.jalr_addr.value) == expected_addr, (
        f"JALR negative offset: expected 0x{expected_addr:08x}, got 0x{int(dut.jalr_addr.value):08x}"
    )

    # Test case 7: JALR LSB clearing (RISC-V spec requirement)
    # Ensure JALR always clears the LSB
    pc = 0x7000
    base_addr = 0x12345679  # Odd address
    instruction = spec.encode_i_type(spec.OP_JALR, 3, 0b000, 20, 0)
    expected_addr = base_addr & 0xFFFFFFFE  # Should clear LSB

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = base_addr
    await Timer(1, units="ns")

    assert int(dut.jalr_addr.value) == expected_addr, (
        f"JALR LSB clearing: expected 0x{expected_addr:08x}, got 0x{int(dut.jalr_addr.value):08x}"
    )

    dut._log.info("✓ All specific RISC-V test cases passed!")


@cocotb.test()
async def test_edge_cases(dut):
    """Test edge cases for branch address calculation"""

    spec = RV32IBranchSpec()
    dut._log.info("=== Testing Edge Cases ===")

    # Test maximum positive branch offset
    pc = 0x1000
    max_branch_offset = 4094  # Maximum B-type offset (±4KB)
    instruction = spec.encode_b_type(spec.OP_BRANCH, 0b000, 0, 0, max_branch_offset)
    expected_addr = pc + max_branch_offset

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.bra_addr.value) == expected_addr, (
        f"Max positive branch: expected 0x{expected_addr:08x}, got 0x{int(dut.bra_addr.value):08x}"
    )

    # Test maximum negative branch offset
    pc = 0x2000
    min_branch_offset = -4096  # Minimum B-type offset
    instruction = spec.encode_b_type(spec.OP_BRANCH, 0b000, 0, 0, min_branch_offset)
    expected_addr = (pc + min_branch_offset) & 0xFFFFFFFF

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.bra_addr.value) == expected_addr, (
        f"Max negative branch: expected 0x{expected_addr:08x}, got 0x{int(dut.bra_addr.value):08x}"
    )

    # Test JAL maximum positive offset
    pc = 0x3000
    max_jal_offset = 1048574  # Maximum J-type offset (±1MB)
    instruction = spec.encode_j_type(spec.OP_JAL, 0, max_jal_offset)
    expected_addr = pc + max_jal_offset

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.jal_addr.value) == expected_addr, (
        f"Max positive JAL: expected 0x{expected_addr:08x}, got 0x{int(dut.jal_addr.value):08x}"
    )

    # Test JAL maximum negative offset
    pc = 0x100000  # Start high enough to avoid underflow
    min_jal_offset = -1048576  # Minimum J-type offset
    instruction = spec.encode_j_type(spec.OP_JAL, 0, min_jal_offset)
    expected_addr = (pc + min_jal_offset) & 0xFFFFFFFF

    dut.pc.value = pc
    dut.inst.value = instruction
    dut.data_a.value = 0
    await Timer(1, units="ns")

    assert int(dut.jal_addr.value) == expected_addr, (
        f"Max negative JAL: expected 0x{expected_addr:08x}, got 0x{int(dut.jal_addr.value):08x}"
    )

    dut._log.info("✓ All edge case tests passed!")
