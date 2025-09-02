SIM ?= icarus

VERILOG_SOURCES += $(shell pwd)/../../src/gpu/alu.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/attribute_interpolator.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/controller.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/fragment_shader.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/framebuffer.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/gpu_register_file.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/gpu_top.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/instruction_decoder.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/gpu_interconnect.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/mmu.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/rasterizer.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/shader_core.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/shader_loader.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/axi_wrapper.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/texture_unit.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/vertex_fetch.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/rtl_utils/reset_sync.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/rtl_utils/arbiter.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/rtl_utils/fifo.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/rtl_utils/clock_divider.sv
VERILOG_SOURCES += $(shell pwd)/../../src/gpu/rtl_utils/gpu_mux_n.sv

TOPLEVEL_LANG = verilog
TOPLEVEL ?= alu
MODULE ?= alu_tb

include $(shell cocotb-config --makefiles)/Makefile.sim

TESTBENCHES = alu:alu_tb attribute_interpolator:attribute_interpolator_tb controller:controller_tb fragment_shader:fragment_shader_tb framebuffer:framebuffer_tb gpu_register_file:gpu_reg_tb gpu_top:gpu_top_tb instruction_decoder:instr_decode_tb gpu_interconnect:interconnect_tb mmu:mmu_tb rasterizer:rasterizer_tb shader_core:shader_core_tb shader_loader:shader_loader_tb axi_wrapper:axi_wrapper_tb texture_unit:texture_tb vertex_fetch:vertex_tb

.PHONY: all_tests
all_tests:
	echo "Running all testbenches in parallel..."
	for tb in $(TESTBENCHES); do 		toplevel=$$(echo $$tb | cut -d: -f1); 		module=$$(echo $$tb | cut -d: -f2); 		echo "Starting $$module ($$toplevel)..."; 		$(MAKE) -j1 TOPLEVEL=$$toplevel MODULE=$$module SIM_BUILD=sim_build_$$module > $$module.log 2>&1 & 	done; 	wait; 	echo "All testbenches completed. Check individual .log files for results."

.PHONY: all_tests_sequential
all_tests_sequential:
	echo "Running all testbenches sequentially..."
	for tb in $(TESTBENCHES); do 		toplevel=$$(echo $$tb | cut -d: -f1); 		module=$$(echo $$tb | cut -d: -f2); 		echo "Running $$module ($$toplevel)..."; 		if $(MAKE) TOPLEVEL=$$toplevel MODULE=$$module SIM_BUILD=sim_build_$$module; then 			echo "✓ $$module PASSED"; 		else 			echo "✗ $$module FAILED"; 		fi; 	done

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
	echo "Available targets:"
	echo "  all_tests           - Run all testbenches in parallel"
	echo "  all_tests_sequential- Run all testbenches sequentially"
	echo "  clean_logs          - Clean test log files and build directories"
	echo "  <module_name>       - Run specific testbench (e.g., make alu)"
	echo "  help                - Show this help message"

.PHONY: alu
alu:
	$(MAKE) TOPLEVEL=alu MODULE=alu_tb SIM_BUILD=sim_build_alu

.PHONY: attribute_interpolator
attribute_interpolator:
	$(MAKE) TOPLEVEL=attribute_interpolator MODULE=attribute_interpolator_tb SIM_BUILD=sim_build_attribute_interpolator

.PHONY: controller
controller:
	$(MAKE) TOPLEVEL=controller MODULE=controller_tb SIM_BUILD=sim_build_controller

.PHONY: fragment_shader
fragment_shader:
	$(MAKE) TOPLEVEL=fragment_shader MODULE=fragment_shader_tb SIM_BUILD=sim_build_fragment_shader

.PHONY: framebuffer
framebuffer:
	$(MAKE) TOPLEVEL=framebuffer MODULE=framebuffer_tb SIM_BUILD=sim_build_framebuffer

.PHONY: gpu_register_file
gpu_register_file:
	$(MAKE) TOPLEVEL=gpu_register_file MODULE=gpu_reg_tb SIM_BUILD=sim_build_gpu_register_file

.PHONY: gpu_top
gpu_top:
	$(MAKE) TOPLEVEL=gpu_top MODULE=gpu_top_tb SIM_BUILD=sim_build_gpu_top

.PHONY: instruction_decoder
instruction_decoder:
	$(MAKE) TOPLEVEL=instruction_decoder MODULE=instr_decode_tb SIM_BUILD=sim_build_instruction_decoder

.PHONY: interconnect
interconnect:
	$(MAKE) TOPLEVEL=gpu_interconnect MODULE=interconnect_tb SIM_BUILD=sim_build_interconnect

.PHONY: mmu
mmu:
	$(MAKE) TOPLEVEL=mmu MODULE=mmu_tb SIM_BUILD=sim_build_mmu

.PHONY: rasterizer
rasterizer:
	$(MAKE) TOPLEVEL=rasterizer MODULE=rasterizer_tb SIM_BUILD=sim_build_rasterizer

.PHONY: shader_core
shader_core:
	$(MAKE) TOPLEVEL=shader_core MODULE=shader_core_tb SIM_BUILD=sim_build_shader_core

.PHONY: shader_loader
shader_loader:
	$(MAKE) TOPLEVEL=shader_loader MODULE=shader_loader_tb SIM_BUILD=sim_build_shader_loader

.PHONY: axi_wrapper
axi_wrapper:
	$(MAKE) TOPLEVEL=axi_wrapper MODULE=axi_wrapper_tb SIM_BUILD=sim_build_axi_wrapper

.PHONY: texture_unit
texture_unit:
	$(MAKE) TOPLEVEL=texture_unit MODULE=texture_tb SIM_BUILD=sim_build_texture_unit

.PHONY: vertex_fetch
vertex_fetch:
	$(MAKE) TOPLEVEL=vertex_fetch MODULE=vertex_tb SIM_BUILD=sim_build_vertex_fetch
