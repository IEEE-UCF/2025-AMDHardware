SIM ?= verilator # Verilator for complex use


# Core CPU modules
VERILOG_SOURCES += ../../src/cpu/branch_calc.sv
VERILOG_SOURCES += ../../src/cpu/bypass_mux.sv
VERILOG_SOURCES += ../../src/cpu/control_unit.sv
VERILOG_SOURCES += ../../src/cpu/equ.sv
VERILOG_SOURCES += ../../src/cpu/imme.sv
VERILOG_SOURCES += ../../src/cpu/instruction_buffer.sv
VERILOG_SOURCES += ../../src/cpu/mux_n.sv

# Memory and interconnect
VERILOG_SOURCES += ../../src/cpu/_interconnect.sv
VERILOG_SOURCES += ../../src/cpu/memory_system.sv
VERILOG_SOURCES += ../../src/cpu/mmu.sv

# Coprocessor system
VERILOG_SOURCES += ../../src/cpu/coprocessor_system.sv
VERILOG_SOURCES += ../../src/cpu/dispatcher.sv

# GPU modules
VERILOG_SOURCES += ../../src/cpu/gpu_op_queue.sv
VERILOG_SOURCES += ../../src/cpu/gpu_result_buffer.sv
VERILOG_SOURCES += ../../src/cpu/gpu_result_wb.sv

# Pipeline stages
VERILOG_SOURCES += ../../src/cpu/pipeline_stages.sv

# Register files
VERILOG_SOURCES += ../../src/cpu/register_file_system.sv

# Offload logic
VERILOG_SOURCES += ../../src/cpu/offload_logic.sv

# Clock management
VERILOG_SOURCES += ../../src/cpu/clock_divider.sv

# Top-level modules
VERILOG_SOURCES += ../../src/cpu/cpu_top.sv
VERILOG_SOURCES += ../../src/cpu/cpu_axi_wrapper.sv
VERILOG_SOURCES += ../../src/cpu/red_pitaya_cpu_wrapper.sv

# RTL Utils
VERILOG_SOURCES += ../../src/cpu/rtl_utils/rv32a_atomic.sv
VERILOG_SOURCES += ../../src/cpu/rtl_utils/rv32m_muldiv.sv

TOPLEVEL_LANG = verilog

include $(shell cocotb-config --makefiles)/Makefile.sim

# Make 'all_tests' the default target when no target is specified
.DEFAULT_GOAL := all_tests

# Define all testbenches with their corresponding modules
TESTBENCHES = \
	mux_n:mux_n_tb \
	branch_calc:branch_calc_tb \
	bypass_mux:bypass_mux_tb \
	control_unit:control_unit_tb \
	equ:equ_tb \
	imme:imme_tb \
	instruction_buffer:instruction_buffer_tb \
	_interconnect:interconnect_tb \
	coprocessor_system:coprocessor_system_tb \
	cpu_top:cpu_top_tb \
	dispatcher:dispatcher_tb \
	memory_system:memory_system_tb \
	mmu:mmu_tb \
	red_pitaya_cpu_wrapper:red_pitaya_cpu_wrapper_tb \
	gpu_op_queue:gpu_op_queue_tb \
	gpu_result_buffer:gpu_result_buffer_tb \
	gpu_result_wb:gpu_result_wb_tb \
	pipeline_stages:pipeline_stages_tb \
	register_file_system:register_file_system_tb \
	offload_logic:offload_logic_tb \
	clock_divider:clock_divider_tb \
	cpu_axi_wrapper:cpu_axi_wrapper_tb

.PHONY: all_tests
all_tests:
	@echo "Running all testbenches..."
	@for tb in $(TESTBENCHES); do \
		toplevel=$$(echo $$tb | cut -d: -f1); \
		module=$$(echo $$tb | cut -d: -f2); \
		echo "========================================"; \
		echo "Running $$module ($$toplevel)..."; \
		echo "========================================"; \
		if $(MAKE) sim TOPLEVEL=$$toplevel MODULE=$$module SIM_BUILD=sim_build_$$module; then \
			echo "✓ $$module PASSED"; \
		else \
			echo "✗ $$module FAILED"; \
		fi; \
		echo ""; \
	done

.PHONY: basic_tests
basic_tests:
	@echo "Running basic testbenches compatible with Icarus Verilog..."
	@for tb in mux_n:mux_n_tb branch_calc:branch_calc_tb bypass_mux:bypass_mux_tb control_unit:control_unit_tb equ:equ_tb imme:imme_tb instruction_buffer:instruction_buffer_tb memory_system:memory_system_tb; do \
		toplevel=$$(echo $$tb | cut -d: -f1); \
		module=$$(echo $$tb | cut -d: -f2); \
		echo "========================================"; \
		echo "Running $$module ($$toplevel)..."; \
		echo "========================================"; \
		if $(MAKE) sim TOPLEVEL=$$toplevel MODULE=$$module SIM_BUILD=sim_build_$$module; then \
			echo "✓ $$module PASSED"; \
		else \
			echo "✗ $$module FAILED"; \
		fi; \
		echo ""; \
	done

.PHONY: clean_logs
clean_logs:
	rm -f *_tb.log *.log
	rm -rf sim_*
	rm -rf sim_build_*
	rm -rf __pycache__
	rm -f results.xml
	rm -f *.vcd
	rm -f dump.vcd

.PHONY: help
help:
	@echo "Available targets:"
	@echo "  all_tests                - Run all testbenches (Verilator required)"
	@echo "  basic_tests              - Run basic testbenches (Icarus Verilog compatible)"
	@echo "  clean_logs               - Clean test log files and build directories"
	@echo "  <module_name>            - Run specific testbench"
	@echo ""
	@echo "Available individual test targets:"
	@echo "  mux_n                    - Test N-input multiplexer"
	@echo "  branch_calc              - Test branch calculation unit"
	@echo "  bypass_mux               - Test bypass multiplexer"
	@echo "  control_unit             - Test control unit"
	@echo "  equ                      - Test equality comparator"
	@echo "  imme                     - Test immediate generator"
	@echo "  instruction_buffer       - Test instruction buffer"
	@echo "  interconnect             - Test interconnect (_interconnect module)"
	@echo "  coprocessor_system       - Test coprocessor system"
	@echo "  cpu_top                  - Test CPU top module"
	@echo "  dispatcher               - Test instruction dispatcher"
	@echo "  memory_system            - Test memory system"
	@echo "  mmu                      - Test memory management unit"
	@echo "  gpu_op_queue             - Test GPU operation queue"
	@echo "  gpu_result_buffer        - Test GPU result buffer"
	@echo "  gpu_result_wb            - Test GPU result writeback"
	@echo "  pipeline_stages          - Test pipeline stages"
	@echo "  register_file_system     - Test register file system"
	@echo "  offload_logic            - Test offload logic"
	@echo "  clock_divider            - Test clock divider"
	@echo "  cpu_axi_wrapper          - Test CPU AXI wrapper"
	@echo "  red_pitaya_cpu_wrapper   - Test Red Pitaya CPU wrapper"
	@echo ""
	@echo "  help                     - Show this help message"

# Individual test targets
.PHONY: mux_n 
mux_n:
	$(MAKE) sim TOPLEVEL=mux_n MODULE=mux_n_tb SIM_BUILD=sim_mux_n

.PHONY: branch_calc 
branch_calc:
	$(MAKE) sim TOPLEVEL=branch_calc MODULE=branch_calc_tb SIM_BUILD=sim_branch_calc

.PHONY: bypass_mux 
bypass_mux:
	$(MAKE) sim TOPLEVEL=bypass_mux MODULE=bypass_mux_tb SIM_BUILD=sim_bypass_mux

.PHONY: control_unit 
control_unit:
	$(MAKE) sim TOPLEVEL=control_unit MODULE=control_unit_tb SIM_BUILD=sim_control_unit

.PHONY: equ 
equ:
	$(MAKE) sim TOPLEVEL=equ MODULE=equ_tb SIM_BUILD=sim_equ

.PHONY: imme 
imme:
	$(MAKE) sim TOPLEVEL=imme MODULE=imme_tb SIM_BUILD=sim_imme

.PHONY: instruction_buffer 
instruction_buffer:
	$(MAKE) sim TOPLEVEL=instruction_buffer MODULE=instruction_buffer_tb SIM_BUILD=sim_instruction_buffer

.PHONY: interconnect
interconnect:
	$(MAKE) sim TOPLEVEL=_interconnect MODULE=interconnect_tb SIM_BUILD=sim_interconnect

.PHONY: coprocessor_system 
coprocessor_system:
	$(MAKE) sim TOPLEVEL=coprocessor_system MODULE=coprocessor_system_tb SIM_BUILD=sim_coprocessor_system

.PHONY: cpu_top 
cpu_top:
	$(MAKE) sim TOPLEVEL=cpu_top MODULE=cpu_top_tb SIM_BUILD=sim_cpu_top

.PHONY: dispatcher 
dispatcher:
	$(MAKE) sim TOPLEVEL=dispatcher MODULE=dispatcher_tb SIM_BUILD=sim_dispatcher

.PHONY: memory_system 
memory_system:
	$(MAKE) sim TOPLEVEL=memory_system MODULE=memory_system_tb SIM_BUILD=sim_memory_system

.PHONY: mmu
mmu:
	$(MAKE) sim TOPLEVEL=mmu MODULE=mmu_tb SIM_BUILD=sim_mmu

.PHONY: gpu_op_queue
gpu_op_queue:
	$(MAKE) sim TOPLEVEL=gpu_op_queue MODULE=gpu_op_queue_tb SIM_BUILD=sim_gpu_op_queue

.PHONY: gpu_result_buffer
gpu_result_buffer:
	$(MAKE) sim TOPLEVEL=gpu_result_buffer MODULE=gpu_result_buffer_tb SIM_BUILD=sim_gpu_result_buffer

.PHONY: gpu_result_wb
gpu_result_wb:
	$(MAKE) sim TOPLEVEL=gpu_result_wb MODULE=gpu_result_wb_tb SIM_BUILD=sim_gpu_result_wb

.PHONY: pipeline_stages
pipeline_stages:
	$(MAKE) sim TOPLEVEL=stage_if MODULE=pipeline_stages_tb SIM_BUILD=sim_pipeline_stages

.PHONY: register_file_system
register_file_system:
	$(MAKE) sim TOPLEVEL=register_file_system MODULE=register_file_system_tb SIM_BUILD=sim_register_file_system

.PHONY: offload_logic
offload_logic:
	$(MAKE) sim TOPLEVEL=offload_manager MODULE=offload_logic_tb SIM_BUILD=sim_offload_logic

.PHONY: clock_divider
clock_divider:
	$(MAKE) sim TOPLEVEL=clock_divider MODULE=clock_divider_tb SIM_BUILD=sim_clock_divider

.PHONY: cpu_axi_wrapper
cpu_axi_wrapper:
	$(MAKE) sim TOPLEVEL=cpu_axi_wrapper MODULE=cpu_axi_wrapper_tb SIM_BUILD=sim_cpu_axi_wrapper

.PHONY: red_pitaya_cpu_wrapper
red_pitaya_cpu_wrapper:
	$(MAKE) sim TOPLEVEL=red_pitaya_cpu_wrapper MODULE=red_pitaya_cpu_wrapper_tb SIM_BUILD=sim_red_pitaya_cpu_wrapper
