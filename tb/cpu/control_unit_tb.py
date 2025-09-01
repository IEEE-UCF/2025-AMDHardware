import cocotb
import random
from cocotb.triggers import Timer

# RISC-V RV32I ISA Specification-based Control Unit Test
# This testbench is based on the official RISC-V ISA specification, not implementation details


class RV32IInstruction:
    OP_LUI = 0b0110111  # Load Upper Immediate
    OP_AUIPC = 0b0010111  # Add Upper Immediate to PC
    OP_JAL = 0b1101111  # Jump and Link
    OP_JALR = 0b1100111  # Jump and Link Register
    OP_BRANCH = 0b1100011  # Branch instructions
    OP_LOAD = 0b0000011  # Load instructions
    OP_STORE = 0b0100011  # Store instructions
    OP_OP_IMM = 0b0010011  # Integer Register-Immediate instructions
    OP_OP = 0b0110011  # Integer Register-Register instructions
    OP_FENCE = 0b0001111  # Memory ordering
    OP_SYSTEM = 0b1110011  # Environment call and breakpoints
    FMT_R = "R"  # Register-Register
    FMT_I = "I"  # Register-Immediate
    FMT_S = "S"  # Store
    FMT_B = "B"  # Branch
    FMT_U = "U"  # Upper Immediate
    FMT_J = "J"  # Jump
    IMM_I = 0b00
    IMM_S = 0b01
    IMM_B = 0b10
    IMM_U = 0b11
    IMM_J = 0b11  # J-type often uses U-type immediate path

    @staticmethod
    def encode_r_type(opcode, rd, funct3, rs1, rs2, funct7):
        return (
            (funct7 << 25)
            | (rs2 << 20)
            | (rs1 << 15)
            | (funct3 << 12)
            | (rd << 7)
            | opcode
        )

    @staticmethod
    def encode_i_type(opcode, rd, funct3, rs1, imm):
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

    @staticmethod
    def encode_s_type(opcode, funct3, rs1, rs2, imm):
        return (
            (((imm >> 5) & 0x7F) << 25)
            | (rs2 << 20)
            | (rs1 << 15)
            | (funct3 << 12)
            | ((imm & 0x1F) << 7)
            | opcode
        )

    @staticmethod
    def encode_b_type(opcode, funct3, rs1, rs2, imm):
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
    def encode_u_type(opcode, rd, imm):
        return (imm & 0xFFFFF000) | (rd << 7) | opcode

    @staticmethod
    def encode_j_type(opcode, rd, imm):
        return (
            (((imm >> 20) & 1) << 31)
            | (((imm >> 1) & 0x3FF) << 21)
            | (((imm >> 11) & 1) << 20)
            | (((imm >> 12) & 0xFF) << 12)
            | (rd << 7)
            | opcode
        )


class RV32IControlUnitSpec:
    def __init__(self):
        self.instr = RV32IInstruction()

    def get_expected_controls(self, opcode, funct3=0, funct7=0):
        expected = {
            "reg_write": 0,  # Does instruction write to register?
            "mem_read": 0,  # Does instruction read from memory?
            "mem_write": 0,  # Does instruction write to memory?
            "alu_src": 0,  # ALU source: 0=register, 1=immediate
            "branch": 0,  # Is this a branch instruction?
            "jump": 0,  # Is this a jump instruction?
            "jalr": 0,  # Is this JALR specifically?
            "lui": 0,  # Is this LUI instruction?
            "auipc": 0,  # Is this AUIPC instruction?
            "system": 0,  # Is this a system instruction?
            "imm_type": self.instr.IMM_I,  # What type of immediate?
        }

        if opcode == self.instr.OP_LUI:
            # LUI: Load Upper Immediate
            expected.update(
                {"reg_write": 1, "alu_src": 1, "lui": 1, "imm_type": self.instr.IMM_U}
            )

        elif opcode == self.instr.OP_AUIPC:
            # AUIPC: Add Upper Immediate to PC
            expected.update(
                {"reg_write": 1, "alu_src": 1, "auipc": 1, "imm_type": self.instr.IMM_U}
            )

        elif opcode == self.instr.OP_JAL:
            # JAL: Jump and Link
            expected.update({"reg_write": 1, "jump": 1, "imm_type": self.instr.IMM_J})

        elif opcode == self.instr.OP_JALR:
            # JALR: Jump and Link Register
            expected.update(
                {"reg_write": 1, "jalr": 1, "alu_src": 1, "imm_type": self.instr.IMM_I}
            )

        elif opcode == self.instr.OP_BRANCH:
            # Branch instructions (BEQ, BNE, BLT, BGE, BLTU, BGEU)
            expected.update({"branch": 1, "imm_type": self.instr.IMM_B})
            # Note: ALU operation depends on funct3, but that's implementation-specific

        elif opcode == self.instr.OP_LOAD:
            # Load instructions (LB, LH, LW, LD, LBU, LHU, LWU)
            expected.update(
                {
                    "reg_write": 1,
                    "mem_read": 1,
                    "alu_src": 1,
                    "imm_type": self.instr.IMM_I,
                }
            )

        elif opcode == self.instr.OP_STORE:
            # Store instructions (SB, SH, SW, SD)
            expected.update(
                {"mem_write": 1, "alu_src": 1, "imm_type": self.instr.IMM_S}
            )

        elif opcode == self.instr.OP_OP_IMM:
            # Immediate arithmetic (ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI)
            expected.update(
                {"reg_write": 1, "alu_src": 1, "imm_type": self.instr.IMM_I}
            )

        elif opcode == self.instr.OP_OP:
            # Register-Register arithmetic (ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND)
            expected.update(
                {
                    "reg_write": 1,
                    "alu_src": 0,  # Uses register, not immediate
                }
            )

        elif opcode == self.instr.OP_FENCE:
            # FENCE: Memory ordering - typically treated as NOP in simple implementations
            pass

        elif opcode == self.instr.OP_SYSTEM:
            # System instructions (ECALL, EBREAK, CSR instructions)
            expected.update({"system": 1})
            # CSR instructions write to registers
            if funct3 != 0b000:  # Not ECALL/EBREAK
                expected["reg_write"] = 1

        return expected


@cocotb.test()
async def test_risc_v_control_unit_compliance(dut):
    instr = RV32IInstruction()
    spec = RV32IControlUnitSpec()

    # Test instruction valid = 0
    dut.inst_valid.value = 0
    dut.instruction.value = 0
    await Timer(2, units="ns")

    # When inst_valid is 0, all control outputs should be 0 (ISA requirement)
    assert int(dut.reg_write.value) == 0, "reg_write should be 0 when inst_valid is 0"
    assert int(dut.mem_read.value) == 0, "mem_read should be 0 when inst_valid is 0"
    assert int(dut.mem_write.value) == 0, "mem_write should be 0 when inst_valid is 0"

    dut._log.info("=== Testing RISC-V RV32I Control Unit ISA Compliance ===")

    # Test each instruction type systematically
    test_cases = []

    # LUI instructions
    for i in range(20):
        rd = random.randint(0, 31)
        imm = random.randint(-524288, 524287) << 12  # 20-bit immediate
        instruction = instr.encode_u_type(instr.OP_LUI, rd, imm)
        expected = spec.get_expected_controls(instr.OP_LUI)
        test_cases.append((instruction, expected, f"LUI x{rd}, {imm >> 12}"))

    # AUIPC instructions
    for i in range(20):
        rd = random.randint(0, 31)
        imm = random.randint(-524288, 524287) << 12
        instruction = instr.encode_u_type(instr.OP_AUIPC, rd, imm)
        expected = spec.get_expected_controls(instr.OP_AUIPC)
        test_cases.append((instruction, expected, f"AUIPC x{rd}, {imm >> 12}"))

    # JAL instructions
    for i in range(20):
        rd = random.randint(0, 31)
        imm = random.randint(-524288, 524287) & ~1  # Even offsets only
        instruction = instr.encode_j_type(instr.OP_JAL, rd, imm)
        expected = spec.get_expected_controls(instr.OP_JAL)
        test_cases.append((instruction, expected, f"JAL x{rd}, {imm}"))

    # JALR instructions
    for i in range(20):
        rd = random.randint(0, 31)
        rs1 = random.randint(0, 31)
        imm = random.randint(-2048, 2047)
        instruction = instr.encode_i_type(instr.OP_JALR, rd, 0, rs1, imm)
        expected = spec.get_expected_controls(instr.OP_JALR)
        test_cases.append((instruction, expected, f"JALR x{rd}, x{rs1}, {imm}"))

    # Branch instructions
    branch_ops = [
        (0b000, "BEQ"),
        (0b001, "BNE"),
        (0b100, "BLT"),
        (0b101, "BGE"),
        (0b110, "BLTU"),
        (0b111, "BGEU"),
    ]
    for funct3, name in branch_ops:
        for i in range(10):
            rs1 = random.randint(0, 31)
            rs2 = random.randint(0, 31)
            imm = random.randint(-2048, 2047) & ~1  # Even offsets
            instruction = instr.encode_b_type(instr.OP_BRANCH, funct3, rs1, rs2, imm)
            expected = spec.get_expected_controls(instr.OP_BRANCH, funct3)
            test_cases.append((instruction, expected, f"{name} x{rs1}, x{rs2}, {imm}"))

    # Load instructions
    load_ops = [
        (0b000, "LB"),
        (0b001, "LH"),
        (0b010, "LW"),
        (0b011, "LD"),
        (0b100, "LBU"),
        (0b101, "LHU"),
        (0b110, "LWU"),
    ]
    for funct3, name in load_ops:
        for i in range(10):
            rd = random.randint(0, 31)
            rs1 = random.randint(0, 31)
            imm = random.randint(-2048, 2047)
            instruction = instr.encode_i_type(instr.OP_LOAD, rd, funct3, rs1, imm)
            expected = spec.get_expected_controls(instr.OP_LOAD, funct3)
            test_cases.append((instruction, expected, f"{name} x{rd}, {imm}(x{rs1})"))

    # Store instructions
    store_ops = [(0b000, "SB"), (0b001, "SH"), (0b010, "SW"), (0b011, "SD")]
    for funct3, name in store_ops:
        for i in range(10):
            rs1 = random.randint(0, 31)
            rs2 = random.randint(0, 31)
            imm = random.randint(-2048, 2047)
            instruction = instr.encode_s_type(instr.OP_STORE, funct3, rs1, rs2, imm)
            expected = spec.get_expected_controls(instr.OP_STORE, funct3)
            test_cases.append((instruction, expected, f"{name} x{rs2}, {imm}(x{rs1})"))

    # Immediate arithmetic instructions
    imm_ops = [
        (0b000, "ADDI"),
        (0b010, "SLTI"),
        (0b011, "SLTIU"),
        (0b100, "XORI"),
        (0b110, "ORI"),
        (0b111, "ANDI"),
        (0b001, "SLLI"),
        (0b101, "SRLI/SRAI"),
    ]
    for funct3, name in imm_ops:
        for i in range(10):
            rd = random.randint(0, 31)
            rs1 = random.randint(0, 31)
            if funct3 in [0b001, 0b101]:  # Shift instructions
                imm = random.randint(0, 31)  # 6-bit shift amount for RV32
            else:
                imm = random.randint(-2048, 2047)
            instruction = instr.encode_i_type(instr.OP_OP_IMM, rd, funct3, rs1, imm)
            expected = spec.get_expected_controls(instr.OP_OP_IMM, funct3)
            test_cases.append((instruction, expected, f"{name} x{rd}, x{rs1}, {imm}"))

    # Register-Register arithmetic
    reg_ops = [
        (0b000, 0b0000000, "ADD"),
        (0b000, 0b0100000, "SUB"),
        (0b001, 0b0000000, "SLL"),
        (0b010, 0b0000000, "SLT"),
        (0b011, 0b0000000, "SLTU"),
        (0b100, 0b0000000, "XOR"),
        (0b101, 0b0000000, "SRL"),
        (0b101, 0b0100000, "SRA"),
        (0b110, 0b0000000, "OR"),
        (0b111, 0b0000000, "AND"),
    ]
    for funct3, funct7, name in reg_ops:
        for i in range(10):
            rd = random.randint(0, 31)
            rs1 = random.randint(0, 31)
            rs2 = random.randint(0, 31)
            instruction = instr.encode_r_type(instr.OP_OP, rd, funct3, rs1, rs2, funct7)
            expected = spec.get_expected_controls(instr.OP_OP, funct3, funct7)
            test_cases.append((instruction, expected, f"{name} x{rd}, x{rs1}, x{rs2}"))

    # System instructions
    system_cases = [
        (instr.encode_i_type(instr.OP_SYSTEM, 0, 0b000, 0, 0b000000000000), "ECALL"),
        (instr.encode_i_type(instr.OP_SYSTEM, 0, 0b000, 0, 0b000000000001), "EBREAK"),
    ]
    for instruction, name in system_cases:
        expected = spec.get_expected_controls(instr.OP_SYSTEM, 0b000)
        test_cases.append((instruction, expected, name))

    # CSR instructions
    csr_ops = [(0b001, "CSRRW"), (0b010, "CSRRS"), (0b011, "CSRRC")]
    for funct3, name in csr_ops:
        for i in range(5):
            rd = random.randint(0, 31)
            rs1 = random.randint(0, 31)
            csr = random.randint(0, 4095)
            instruction = instr.encode_i_type(instr.OP_SYSTEM, rd, funct3, rs1, csr)
            expected = spec.get_expected_controls(instr.OP_SYSTEM, funct3)
            test_cases.append((instruction, expected, f"{name} x{rd}, x{rs1}, {csr}"))

    dut._log.info(f"Testing {len(test_cases)} RISC-V instructions...")

    # Run all test cases
    failures = 0
    for i, (instruction, expected, desc) in enumerate(test_cases):
        dut.instruction.value = instruction
        dut.inst_valid.value = 1
        await Timer(1, units="ns")

        # Read DUT outputs (only the signals we care about for ISA compliance)
        dut_outputs = {}
        isa_signals = [
            "reg_write",
            "mem_read",
            "mem_write",
            "alu_src",
            "branch",
            "jump",
            "jalr",
            "lui",
            "auipc",
            "system",
            "imm_type",
        ]

        for signal in isa_signals:
            if hasattr(dut, signal):
                dut_outputs[signal] = int(getattr(dut, signal).value)

        # Check ISA-required control signals
        mismatch = False
        for signal in expected:
            if signal in dut_outputs and expected[signal] != dut_outputs[signal]:
                mismatch = True
                break

        if mismatch:
            failures += 1
            dut._log.error(f"FAIL [{i + 1}]: {desc}")
            dut._log.error(f"  Instruction: 0x{instruction:08x}")
            dut._log.error(f"  Expected: {expected}")
            dut._log.error(f"  Got:      {dut_outputs}")

            if failures >= 10:  # Limit error spam
                dut._log.error("Too many failures, stopping test")
                break

        dut.inst_valid.value = 0

    success_count = len(test_cases) - failures
    dut._log.info(f"=== RISC-V ISA Compliance Results ===")
    dut._log.info(f"Total tests: {len(test_cases)}")
    dut._log.info(f"Passed: {success_count}")
    dut._log.info(f"Failed: {failures}")

    if failures == 0:
        dut._log.info("✓ Control Unit is RISC-V RV32I ISA compliant!")
    else:
        dut._log.error("✗ Control Unit has ISA compliance issues")
        assert False, f"Control unit failed {failures} ISA compliance tests"


@cocotb.test()
async def test_nop_instruction(dut):
    # NOP = ADDI x0, x0, 0 = 0x00000013
    nop_instruction = 0x00000013

    dut.instruction.value = nop_instruction
    dut.inst_valid.value = 1
    await Timer(1, units="ns")

    # NOP should have reg_write=1, alu_src=1, but writes to x0 (which is ignored)
    assert int(dut.reg_write.value) == 1, (
        "NOP should set reg_write (even though x0 is ignored)"
    )
    assert int(dut.alu_src.value) == 1, "NOP should use immediate source"
    assert int(dut.mem_read.value) == 0, "NOP should not read memory"
    assert int(dut.mem_write.value) == 0, "NOP should not write memory"
    assert int(dut.opcode.value) == 0x13, "NOP opcode should be OP_IMM"
    assert int(dut.rd.value) == 0, "NOP should target x0"
    assert int(dut.rs1.value) == 0, "NOP should use x0 as source"

    dut._log.info("✓ NOP instruction test passed")
