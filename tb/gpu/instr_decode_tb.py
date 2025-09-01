import cocotb
from cocotb.triggers import Timer
import random

@cocotb.test()
async def test_instruction_decoder(dut):

    # Coverage tracking
    opcode_coverage = set()
    rd_coverage = set()
    rs1_coverage = set()
    rs2_coverage = set()
    imm_coverage = set()

    for _ in range(100000):
        # Generate a random instruction word
        instruction_word = random.randint(0, 0xFFFFFFFF)

        # Apply the instruction word to the DUT
        dut.i_instruction_word.value = instruction_word

        # Wait for a short time to simulate propagation delay
        await Timer(1, units="ns")

        # Decode the instruction word manually
        expected_opcode = (instruction_word >> 27) & 0x1F
        expected_rd_addr = (instruction_word >> 23) & 0xF
        expected_rs1_addr = (instruction_word >> 19) & 0xF
        expected_rs2_addr = (instruction_word >> 15) & 0xF
        expected_imm = instruction_word & 0xFFF

        # Track coverage
        opcode_coverage.add(expected_opcode)
        rd_coverage.add(expected_rd_addr)
        rs1_coverage.add(expected_rs1_addr)
        rs2_coverage.add(expected_rs2_addr)
        imm_coverage.add(expected_imm)

        # Check the outputs of the DUT
        assert dut.o_opcode.value == expected_opcode, f"Opcode mismatch: {dut.o_opcode.value} != {expected_opcode}"
        assert dut.o_rd_addr.value == expected_rd_addr, f"RD address mismatch: {dut.o_rd_addr.value} != {expected_rd_addr}"
        assert dut.o_rs1_addr.value == expected_rs1_addr, f"RS1 address mismatch: {dut.o_rs1_addr.value} != {expected_rs1_addr}"
        assert dut.o_rs2_addr.value == expected_rs2_addr, f"RS2 address mismatch: {dut.o_rs2_addr.value} != {expected_rs2_addr}"
        assert dut.o_imm.value == expected_imm, f"Immediate mismatch: {dut.o_imm.value} != {expected_imm}"

    # Log coverage results
    cocotb.log.info(f"Opcode coverage: {len(opcode_coverage)}/32")
    cocotb.log.info(f"RD address coverage: {len(rd_coverage)}/16")
    cocotb.log.info(f"RS1 address coverage: {len(rs1_coverage)}/16")
    cocotb.log.info(f"RS2 address coverage: {len(rs2_coverage)}/16")
    cocotb.log.info(f"Immediate coverage: {len(imm_coverage)}/4096")