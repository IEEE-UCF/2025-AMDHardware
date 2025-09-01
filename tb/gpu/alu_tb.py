# tb/alu_tb.py
import cocotb
import random
from cocotb.triggers import Timer
from cocotb.binary import BinaryValue


@cocotb.test()
async def test_alu(dut):
    data_width = int(dut.DATA_WIDTH.value)
    vector_size = int(dut.VECTOR_SIZE.value)
    MAXVAL = (1 << data_width) - 1

    def pack(vec):
        return sum((int(v) & MAXVAL) << (i * data_width) for i, v in enumerate(vec))

    def unpack(bits):
        return [ (bits >> (i * data_width)) & MAXVAL for i in range(vector_size) ]

    def add_w(a, b): return (a + b) & MAXVAL
    def sub_w(a, b): return (a - b) & MAXVAL
    def mul_w(a, b): return (a * b) & MAXVAL

    valid_opcodes = [
        0b00001, # add
        0b00010, # sub
        0b00011, # mul
        0b01001, # and
        0b01010, # or
        0b01011, # xor
        0b10001, # mov a
        0b10010, # mov b
    ]
    test_opcodes = valid_opcodes + [0b00000]

    dut._log.info("---- ALU TEST STARTS HERE ----")
    num_iterations = 10_000

    for i in range(num_iterations):
        opcode = random.choice(test_opcodes)
        op_a = [random.randint(0, MAXVAL) for _ in range(vector_size)]
        op_b = [random.randint(0, MAXVAL) for _ in range(vector_size)]

        dut.i_opcode.value = opcode
        dut.i_operand_a.value = pack(op_a)
        dut.i_operand_b.value = pack(op_b)

        await Timer(1, units="ns")

        dut_result = unpack(int(dut.o_result.value))

        expected = []
        for j in range(vector_size):
            a = op_a[j]
            b = op_b[j]
            if opcode == 0b00001: val = add_w(a, b)
            elif opcode == 0b00010: val = sub_w(a, b)
            elif opcode == 0b00011: val = mul_w(a, b)
            elif opcode == 0b01001: val = a & b
            elif opcode == 0b01010: val = a | b
            elif opcode == 0b01011: val = a ^ b
            elif opcode == 0b10001: val = a
            elif opcode == 0b10010: val = b
            else: val = 0
            expected.append(val)

        if dut_result != expected:
            for j in range(vector_size):
                if dut_result[j] != expected[j]:
                    dut._log.error(f"Mismatch in lane {j} on iteration {i+1}:")
                    dut._log.error(f" Opcode: {opcode:05b}")
                    dut._log.error(f" Operand A[{j}]: {op_a[j]}")
                    dut._log.error(f" Operand B[{j}]: {op_b[j]}")
                    dut._log.error(f" DUT Result[{j}]: {dut_result[j]}")
                    dut._log.error(f" Expected Result[{j}]: {expected[j]}")
            
            assert False, f"ALU mismatch detected on iteration {i+1}. See logs for details."

    dut._log.info(f"--- ALU TEST FINISHED: {num_iterations} vectors, all matched ---")
