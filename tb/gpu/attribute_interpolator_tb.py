# tb/attribute_interpolator_tb.py
import os
import random
import cocotb
from cocotb.triggers import Timer

def to_signed32(n: int) -> int:
    n &= 0xFFFFFFFF
    return n - (1 << 32) if (n & (1 << 31)) else n

@cocotb.test()
async def test_attribute_interpolator(dut):
    num_iters = int(os.getenv("ATTR_NUM", "100000"))

    attr_width = int(dut.ATTR_WIDTH.value)
    weight_width = int(dut.WEIGHT_WIDTH.value)

    max_attr = (1 << (attr_width - 1)) - 1
    min_attr = -(1 << (attr_width - 1))
    max_weight = (1 << (weight_width - 1)) - 1
    min_weight = -(1 << (weight_width - 1))

    dut._log.info(f"Starting {num_iters} random vectors")

    for i in range(num_iters):
        a0 = random.randint(min_attr, max_attr)
        a1 = random.randint(min_attr, max_attr)
        a2 = random.randint(min_attr, max_attr)

        l0 = random.randint(min_weight, max_weight)
        l1 = random.randint(min_weight, max_weight)
        l2 = random.randint(min_weight, max_weight)

        full_sum = a0*l0 + a1*l1 + a2*l2
        shifted_sum = full_sum // (2 ** weight_width)
        expected = to_signed32(shifted_sum)

        dut.i_attr0.value = a0
        dut.i_attr1.value = a1
        dut.i_attr2.value = a2
        dut.i_lambda0.value = l0
        dut.i_lambda1.value = l1
        dut.i_lambda2.value = l2

        await Timer(1, units="ns")

        val = dut.o_interpolated_attr.value
        assert val.is_resolvable, f"X/Z on o_interpolated_attr at iter {i+1}: {val}"
        got = val.signed_integer

        if got != expected:
            dut._log.error(
                "Mismatch @ iter %d\n"
                " attrs = [%d, %d, %d]\n"
                " lambdas = [%d, %d, %d]\n"
                " dut = %d\n"
                " expected= %d",
                i+1, a0, a1, a2, l0, l1, l2, got, expected
            )
            assert False, "Attribute interpolator mismatch"

    dut._log.info(f"PASS — {num_iters} vectors matched")
