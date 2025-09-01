import cocotb
from cocotb.triggers import Timer
from dataclasses import dataclass
from enum import Enum
from typing import List
from abc import ABC, abstractmethod

"""
RISC-V RV32I ISA Bypass/Forwarding Testbench
UML-based Object-Oriented Design

This testbench uses UML design patterns to model RISC-V pipeline 
forwarding behavior according to the ISA specification.
"""


class ForwardingSource(Enum):
    """Enumeration of possible forwarding sources"""

    REGISTER_FILE = "REG_FILE"
    EX_STAGE = "EX_STAGE"
    MEM_ALU_RESULT = "MEM_ALU"
    MEM_LOAD_DATA = "MEM_DATA"


class HazardType(Enum):
    """Types of pipeline hazards per RISC-V specification"""

    NO_HAZARD = "NONE"
    RAW_HAZARD = "READ_AFTER_WRITE"
    WAW_HAZARD = "WRITE_AFTER_WRITE"
    WAR_HAZARD = "WRITE_AFTER_READ"


@dataclass
class PipelineStage:
    """Represents a pipeline stage state"""

    register_dest: int
    writes_register: bool
    data_value: int
    is_load_instruction: bool = False

    def writes_to_register(self, reg_num: int) -> bool:
        """Check if this stage writes to specified register"""
        return (
            self.writes_register and self.register_dest == reg_num and reg_num != 0
        )  # x0 is never written in RISC-V


@dataclass
class ForwardingDecision:
    """Result of forwarding analysis"""

    source: ForwardingSource
    data_value: int
    hazard_type: HazardType
    reason: str


class IRISCVRegister(ABC):
    """Abstract interface for RISC-V register behavior"""

    @abstractmethod
    def get_value(self) -> int:
        """Get the current value of the register"""
        pass

    @abstractmethod
    def is_zero_register(self) -> bool:
        """Check if this is the special x0 register"""
        pass


class RISCVRegister(IRISCVRegister):
    """Concrete implementation of a RISC-V register"""

    def __init__(self, register_number: int, value: int = 0):
        self._reg_num = register_number
        self._value = value

    def get_value(self) -> int:
        """x0 always returns 0, others return stored value"""
        return 0 if self.is_zero_register() else self._value

    def is_zero_register(self) -> bool:
        """x0 is hardwired to zero in RISC-V"""
        return self._reg_num == 0

    def set_value(self, value: int) -> None:
        """Set register value (ignored for x0)"""
        if not self.is_zero_register():
            self._value = value


class IHazardDetector(ABC):
    """Abstract interface for pipeline hazard detection"""

    @abstractmethod
    def detect_hazard(
        self, read_reg: int, ex_stage: PipelineStage, mem_stage: PipelineStage
    ) -> HazardType:
        """Detect if there's a pipeline hazard"""
        pass


class RISCVHazardDetector(IHazardDetector):
    """RISC-V specific hazard detection implementation"""

    def detect_hazard(
        self, read_reg: int, ex_stage: PipelineStage, mem_stage: PipelineStage
    ) -> HazardType:
        """Detect RAW hazards according to RISC-V pipeline rules"""

        if read_reg == 0:
            return HazardType.NO_HAZARD  # x0 never has hazards

        ex_hazard = ex_stage.writes_to_register(read_reg)
        mem_hazard = mem_stage.writes_to_register(read_reg)

        if ex_hazard or mem_hazard:
            return HazardType.RAW_HAZARD
        else:
            return HazardType.NO_HAZARD


class IForwardingUnit(ABC):
    """Abstract interface for forwarding unit"""

    @abstractmethod
    def determine_forwarding(
        self,
        read_reg: int,
        ex_stage: PipelineStage,
        mem_stage: PipelineStage,
        reg_file_data: int,
    ) -> ForwardingDecision:
        """Determine the correct forwarding source and data"""
        pass


class RISCVForwardingUnit(IForwardingUnit):
    """RISC-V specific forwarding unit implementation"""

    def __init__(self, hazard_detector: IHazardDetector):
        self._hazard_detector = hazard_detector

    def determine_forwarding(
        self,
        read_reg: int,
        ex_stage: PipelineStage,
        mem_stage: PipelineStage,
        reg_file_data: int,
    ) -> ForwardingDecision:
        """
        Implement RISC-V forwarding priority matching your SystemVerilog implementation:
        1. EX stage (highest priority - most recent)
        2. MEM stage (medium priority - older)
        3. Register file (lowest priority - potentially stale)

        Note: Your SystemVerilog doesn't handle x0 specially - it expects
        the register file to provide 0 for x0 reads.
        """

        hazard = self._hazard_detector.detect_hazard(read_reg, ex_stage, mem_stage)

        # Check EX stage forwarding (highest priority)
        # Matches: if (file_out_rs == ex_rd && ex_wr_reg_en && file_out_rs != '0)
        if ex_stage.writes_to_register(read_reg) and read_reg != 0:
            return ForwardingDecision(
                source=ForwardingSource.EX_STAGE,
                data_value=ex_stage.data_value,
                hazard_type=HazardType.RAW_HAZARD,
                reason="RAW hazard resolved by EX stage forwarding",
            )

        # Check MEM stage forwarding (medium priority)
        # Matches: else if (file_out_rs == mm_rd && mm_wr_reg_en && file_out_rs != '0)
        elif mem_stage.writes_to_register(read_reg) and read_reg != 0:
            if mem_stage.is_load_instruction:
                return ForwardingDecision(
                    source=ForwardingSource.MEM_LOAD_DATA,
                    data_value=mem_stage.data_value,
                    hazard_type=HazardType.RAW_HAZARD,
                    reason="RAW hazard resolved by MEM load data forwarding",
                )
            else:
                return ForwardingDecision(
                    source=ForwardingSource.MEM_ALU_RESULT,
                    data_value=mem_stage.data_value,
                    hazard_type=HazardType.RAW_HAZARD,
                    reason="RAW hazard resolved by MEM ALU result forwarding",
                )

        # No hazard or reading from x0 - use register file
        # Your SystemVerilog expects register file to handle x0 correctly
        return ForwardingDecision(
            source=ForwardingSource.REGISTER_FILE,
            data_value=reg_file_data,
            hazard_type=HazardType.NO_HAZARD,
            reason="No hazard detected, using register file data",
        )


class RISCVPipelineSimulator:
    """Simulates RISC-V pipeline for testing bypass logic"""

    def __init__(self):
        self._forwarding_unit = RISCVForwardingUnit(RISCVHazardDetector())

    def simulate_bypass(
        self,
        read_register: int,
        ex_stage: PipelineStage,
        mem_stage: PipelineStage,
        register_file_data: int,
    ) -> ForwardingDecision:
        """Simulate the bypass/forwarding decision"""
        return self._forwarding_unit.determine_forwarding(
            read_register, ex_stage, mem_stage, register_file_data
        )


class RISCVTestCase:
    """Represents a single test case for RISC-V forwarding"""

    def __init__(
        self,
        name: str,
        description: str,
        read_reg: int,
        ex_stage: PipelineStage,
        mem_stage: PipelineStage,
        reg_file_data: int,
        expected_source: ForwardingSource,
        expected_data: int,
    ):
        self.name = name
        self.description = description
        self.read_reg = read_reg
        self.ex_stage = ex_stage
        self.mem_stage = mem_stage
        self.reg_file_data = reg_file_data
        self.expected_source = expected_source
        self.expected_data = expected_data


class RISCVTestSuite:
    """Test suite generator for RISC-V forwarding scenarios"""

    @staticmethod
    def generate_no_hazard_cases() -> List[RISCVTestCase]:
        """Generate test cases with no forwarding needed"""
        cases = []

        # Case 1: Different registers
        cases.append(
            RISCVTestCase(
                name="no_hazard_different_regs",
                description="Different source and destination registers",
                read_reg=5,
                ex_stage=PipelineStage(
                    register_dest=10, writes_register=True, data_value=0x1000
                ),
                mem_stage=PipelineStage(
                    register_dest=15, writes_register=True, data_value=0x2000
                ),
                reg_file_data=0x3000,
                expected_source=ForwardingSource.REGISTER_FILE,
                expected_data=0x3000,
            )
        )

        # Case 2: No writes happening
        cases.append(
            RISCVTestCase(
                name="no_hazard_no_writes",
                description="No pipeline stages writing to registers",
                read_reg=7,
                ex_stage=PipelineStage(
                    register_dest=7, writes_register=False, data_value=0x1000
                ),
                mem_stage=PipelineStage(
                    register_dest=7, writes_register=False, data_value=0x2000
                ),
                reg_file_data=0x4000,
                expected_source=ForwardingSource.REGISTER_FILE,
                expected_data=0x4000,
            )
        )

        # Case 3: Reading from x0 - Your SystemVerilog doesn't handle x0 specially
        # It expects the register file to provide 0 for x0
        cases.append(
            RISCVTestCase(
                name="x0_register_read",
                description="Reading from x0 (register file should provide 0)",
                read_reg=0,
                ex_stage=PipelineStage(
                    register_dest=1, writes_register=True, data_value=0xFFFF
                ),
                mem_stage=PipelineStage(
                    register_dest=2, writes_register=True, data_value=0xAAAA
                ),
                reg_file_data=0,  # Register file should provide 0 for x0
                expected_source=ForwardingSource.REGISTER_FILE,
                expected_data=0,  # Should get 0 from register file
            )
        )

        return cases

    @staticmethod
    def generate_ex_forwarding_cases() -> List[RISCVTestCase]:
        """Generate test cases requiring EX stage forwarding"""
        cases = []

        for reg in [1, 5, 10, 31]:  # Test various registers
            cases.append(
                RISCVTestCase(
                    name=f"ex_forwarding_x{reg}",
                    description=f"EX stage forwarding for register x{reg}",
                    read_reg=reg,
                    ex_stage=PipelineStage(
                        register_dest=reg, writes_register=True, data_value=0x5000 + reg
                    ),
                    mem_stage=PipelineStage(
                        register_dest=min(reg + 1, 31),
                        writes_register=False,
                        data_value=0x6000,
                    ),
                    reg_file_data=0x7000,
                    expected_source=ForwardingSource.EX_STAGE,
                    expected_data=0x5000 + reg,
                )
            )

        return cases

    @staticmethod
    def generate_mem_alu_forwarding_cases() -> List[RISCVTestCase]:
        """Generate test cases requiring MEM ALU forwarding"""
        cases = []

        for reg in [2, 8, 16]:
            cases.append(
                RISCVTestCase(
                    name=f"mem_alu_forwarding_x{reg}",
                    description=f"MEM ALU forwarding for register x{reg}",
                    read_reg=reg,
                    ex_stage=PipelineStage(
                        register_dest=min(reg + 5, 31),
                        writes_register=True,
                        data_value=0x8000,
                    ),
                    mem_stage=PipelineStage(
                        register_dest=reg,
                        writes_register=True,
                        data_value=0x9000 + reg,
                        is_load_instruction=False,
                    ),
                    reg_file_data=0xA000,
                    expected_source=ForwardingSource.MEM_ALU_RESULT,
                    expected_data=0x9000 + reg,
                )
            )

        return cases

    @staticmethod
    def generate_mem_load_forwarding_cases() -> List[RISCVTestCase]:
        """Generate test cases requiring MEM load data forwarding"""
        cases = []

        for reg in [3, 12, 25]:
            cases.append(
                RISCVTestCase(
                    name=f"mem_load_forwarding_x{reg}",
                    description=f"MEM load data forwarding for register x{reg}",
                    read_reg=reg,
                    ex_stage=PipelineStage(
                        register_dest=min(reg + 10, 31),
                        writes_register=True,
                        data_value=0xB000,
                    ),
                    mem_stage=PipelineStage(
                        register_dest=reg,
                        writes_register=True,
                        data_value=0xC000 + reg,
                        is_load_instruction=True,
                    ),
                    reg_file_data=0xD000,
                    expected_source=ForwardingSource.MEM_LOAD_DATA,
                    expected_data=0xC000 + reg,
                )
            )

        return cases

    @staticmethod
    def generate_priority_test_cases() -> List[RISCVTestCase]:
        """Generate test cases for forwarding priority (EX beats MEM)"""
        cases = []

        for reg in [4, 18]:
            cases.append(
                RISCVTestCase(
                    name=f"priority_test_x{reg}",
                    description=f"EX priority over MEM for register x{reg}",
                    read_reg=reg,
                    ex_stage=PipelineStage(
                        register_dest=reg, writes_register=True, data_value=0xE000 + reg
                    ),
                    mem_stage=PipelineStage(
                        register_dest=reg,
                        writes_register=True,
                        data_value=0xF000 + reg,
                        is_load_instruction=False,
                    ),
                    reg_file_data=0x1111,
                    expected_source=ForwardingSource.EX_STAGE,  # EX should win
                    expected_data=0xE000 + reg,
                )
            )

        return cases


@cocotb.test()
async def test_risc_v_uml_bypass_compliance(dut):
    """UML-based test for RISC-V bypass multiplexer compliance"""

    dut._log.info("=== UML-based RISC-V RV32I Bypass Multiplexer Test ===")

    # Initialize UML components
    simulator = RISCVPipelineSimulator()
    test_suite = RISCVTestSuite()

    # Collect all test cases
    all_test_cases = []
    all_test_cases.extend(test_suite.generate_no_hazard_cases())
    all_test_cases.extend(test_suite.generate_ex_forwarding_cases())
    all_test_cases.extend(test_suite.generate_mem_alu_forwarding_cases())
    all_test_cases.extend(test_suite.generate_mem_load_forwarding_cases())
    all_test_cases.extend(test_suite.generate_priority_test_cases())

    dut._log.info(f"Generated {len(all_test_cases)} UML-based test cases")

    passed_tests = 0
    failed_tests = 0

    for test_case in all_test_cases:
        dut._log.info(f"Running: {test_case.name} - {test_case.description}")

        # Use UML simulator to determine expected behavior
        expected_decision = simulator.simulate_bypass(
            test_case.read_reg,
            test_case.ex_stage,
            test_case.mem_stage,
            test_case.reg_file_data,
        )

        # Set up DUT inputs based on test case
        dut.file_out.value = test_case.reg_file_data
        dut.ex_pro.value = test_case.ex_stage.data_value

        # Handle MEM stage data routing
        if test_case.mem_stage.is_load_instruction:
            dut.mm_pro.value = 0  # ALU result not used for loads
            dut.mm_mem.value = test_case.mem_stage.data_value  # Use load data
        else:
            dut.mm_pro.value = test_case.mem_stage.data_value  # Use ALU result
            dut.mm_mem.value = 0  # Memory data not used

        dut.file_out_rs.value = test_case.read_reg
        dut.ex_rd.value = test_case.ex_stage.register_dest
        dut.mm_rd.value = test_case.mem_stage.register_dest
        dut.ex_wr_reg_en.value = test_case.ex_stage.writes_register
        dut.mm_wr_reg_en.value = test_case.mem_stage.writes_register
        dut.mm_is_load.value = test_case.mem_stage.is_load_instruction

        await Timer(1, units="ns")

        # Check DUT output against UML model prediction
        actual_output = int(dut.bypass_out.value)
        expected_output = expected_decision.data_value

        if actual_output == expected_output:
            passed_tests += 1
            dut._log.info(f"  ✓ PASS: {expected_decision.reason}")
        else:
            failed_tests += 1
            dut._log.error(f"  ✗ FAIL: {test_case.name}")
            dut._log.error(
                f"    Expected: 0x{expected_output:016x} ({expected_decision.source.value})"
            )
            dut._log.error(f"    Actual:   0x{actual_output:016x}")
            dut._log.error(f"    Reason:   {expected_decision.reason}")

            # Stop after too many failures to avoid spam
            if failed_tests >= 5:
                dut._log.error("Too many failures, stopping test")
                break

    # Test results summary
    total_tests = passed_tests + failed_tests

    dut._log.info("=== UML-based RISC-V Bypass Test Results ===")
    dut._log.info(f"Total tests: {total_tests}")
    dut._log.info(f"Passed: {passed_tests}")
    dut._log.info(f"Failed: {failed_tests}")
    dut._log.info(f"Success rate: {(passed_tests / total_tests * 100):.1f}%")

    if failed_tests == 0:
        dut._log.info("✓ Bypass multiplexer is RISC-V RV32UML-model compliant!")
    else:
        dut._log.error("✗ Bypass multiplexer failed UML-based compliance tests")
        assert False, (
            f"UML-based bypass test failed {failed_tests} out of {total_tests} tests"
        )


@cocotb.test()
async def test_uml_pipeline_scenarios(dut):
    """Test realistic RISC-V pipeline scenarios using UML models"""

    dut._log.info("=== UML-based RISC-V Pipeline Scenario Testing ===")

    simulator = RISCVPipelineSimulator()
    scenarios_passed = 0
    scenarios_failed = 0

    # Scenario 1: Classic ADD-SUB RAW hazard
    scenario_name = "Classic ADD-SUB RAW Hazard"
    dut._log.info(f"Testing: {scenario_name}")

    # ADD x3, x1, x2 (in EX stage)
    # SUB x4, x3, x5 (in ID stage, reads x3)
    ex_add = PipelineStage(register_dest=3, writes_register=True, data_value=0x12345678)
    mem_nop = PipelineStage(register_dest=0, writes_register=False, data_value=0)
    reg_file_stale = 0xDEADBEEF

    decision = simulator.simulate_bypass(3, ex_add, mem_nop, reg_file_stale)

    # Apply to DUT
    dut.file_out.value = reg_file_stale
    dut.ex_pro.value = ex_add.data_value
    dut.mm_pro.value = 0
    dut.mm_mem.value = 0
    dut.file_out_rs.value = 3
    dut.ex_rd.value = 3
    dut.mm_rd.value = 0
    dut.ex_wr_reg_en.value = 1
    dut.mm_wr_reg_en.value = 0
    dut.mm_is_load.value = 0

    await Timer(1, units="ns")

    if int(dut.bypass_out.value) == decision.data_value:
        scenarios_passed += 1
        dut._log.info(f"  ✓ {scenario_name} passed")
    else:
        scenarios_failed += 1
        dut._log.error(f"  ✗ {scenario_name} failed")

    # Scenario 2: Load-Use hazard with memory forwarding
    scenario_name = "Load-Use Hazard"
    dut._log.info(f"Testing: {scenario_name}")

    # LW x7, 100(x8) (in MEM stage)
    # ADD x9, x7, x10 (in ID stage, reads x7)
    ex_nop = PipelineStage(register_dest=0, writes_register=False, data_value=0)
    mem_load = PipelineStage(
        register_dest=7,
        writes_register=True,
        data_value=0x87654321,
        is_load_instruction=True,
    )
    reg_file_old = 0xBADF000D

    decision = simulator.simulate_bypass(7, ex_nop, mem_load, reg_file_old)

    # Apply to DUT
    dut.file_out.value = reg_file_old
    dut.ex_pro.value = 0
    dut.mm_pro.value = 0  # Not used for loads
    dut.mm_mem.value = mem_load.data_value
    dut.file_out_rs.value = 7
    dut.ex_rd.value = 0
    dut.mm_rd.value = 7
    dut.ex_wr_reg_en.value = 0
    dut.mm_wr_reg_en.value = 1
    dut.mm_is_load.value = 1

    await Timer(1, units="ns")

    if int(dut.bypass_out.value) == decision.data_value:
        scenarios_passed += 1
        dut._log.info(f"  ✓ {scenario_name} passed")
    else:
        scenarios_failed += 1
        dut._log.error(f"  ✗ {scenario_name} failed")

    # Scenario 3: EX vs MEM priority test
    scenario_name = "EX vs MEM Priority"
    dut._log.info(f"Testing: {scenario_name}")

    # Both EX and MEM write to x15, EX should win
    ex_newer = PipelineStage(
        register_dest=15, writes_register=True, data_value=0x0000BEEF
    )
    mem_older = PipelineStage(
        register_dest=15, writes_register=True, data_value=0x00000000
    )

    decision = simulator.simulate_bypass(15, ex_newer, mem_older, 0x0000DEAD)

    # Apply to DUT
    dut.file_out.value = 0x0000DEAD
    dut.ex_pro.value = ex_newer.data_value
    dut.mm_pro.value = mem_older.data_value
    dut.mm_mem.value = mem_older.data_value
    dut.file_out_rs.value = 15
    dut.ex_rd.value = 15
    dut.mm_rd.value = 15
    dut.ex_wr_reg_en.value = 1
    dut.mm_wr_reg_en.value = 1
    dut.mm_is_load.value = 0

    await Timer(1, units="ns")

    if int(dut.bypass_out.value) == decision.data_value:
        scenarios_passed += 1
        dut._log.info(f"  ✓ {scenario_name} passed (EX priority correct)")
    else:
        scenarios_failed += 1
        dut._log.error(f"  ✗ {scenario_name} failed (priority error)")

    # Results
    total_scenarios = scenarios_passed + scenarios_failed
    dut._log.info(f"=== UML Pipeline Scenario Results ===")
    dut._log.info(f"Scenarios passed: {scenarios_passed}/{total_scenarios}")

    if scenarios_failed == 0:
        dut._log.info("✓ All UML pipeline scenarios passed!")
    else:
        assert False, (
            f"UML pipeline scenarios failed: {scenarios_failed}/{total_scenarios}"
        )


@cocotb.test()
async def test_uml_architectural_compliance(dut):
    """Test architectural compliance using UML behavioral model"""

    dut._log.info("=== UML Architectural Compliance Test ===")

    # Test RISC-V x0 register behavior using UML model
    zero_reg = RISCVRegister(0, 0xFFFFFFFFFFFFFFFF)  # Try to set x0 to non-zero

    assert zero_reg.is_zero_register() == True
    assert zero_reg.get_value() == 0  # Should always be zero

    # Test normal register behavior
    normal_reg = RISCVRegister(5, 0x123456789ABCDEF0)

    assert normal_reg.is_zero_register() == False
    assert normal_reg.get_value() == 0x123456789ABCDEF0

    # Test hazard detector
    hazard_detector = RISCVHazardDetector()

    # Test RAW hazard detection
    ex_writes_x5 = PipelineStage(5, True, 0x1000)
    mem_idle = PipelineStage(0, False, 0)

    hazard = hazard_detector.detect_hazard(5, ex_writes_x5, mem_idle)
    assert hazard == HazardType.RAW_HAZARD

    # Test no hazard case
    hazard = hazard_detector.detect_hazard(10, ex_writes_x5, mem_idle)
    assert hazard == HazardType.NO_HAZARD

    # Apply x0 register test to DUT - your SystemVerilog expects reg file to provide 0
    dut.file_out.value = 0  # Register file should provide 0 for x0
    dut.ex_pro.value = 0xEEEEEEEE
    dut.mm_pro.value = 0xDDDDDDDD
    dut.mm_mem.value = 0xCCCCCCCC
    dut.file_out_rs.value = 0  # Read from x0
    dut.ex_rd.value = 1  # EX writes to different register
    dut.mm_rd.value = 2  # MEM writes to different register
    dut.ex_wr_reg_en.value = 1
    dut.mm_wr_reg_en.value = 1
    dut.mm_is_load.value = 0

    await Timer(1, units="ns")

    # Should get 0 from register file (no forwarding for x0)
    assert int(dut.bypass_out.value) == 0, (
        "x0 register should read 0 from register file"
    )

    dut._log.info("✓ UML architectural compliance verified!")
