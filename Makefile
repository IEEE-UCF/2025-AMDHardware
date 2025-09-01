# Top-level Makefile for cocotb simulation of all CPU and GPU testbenches
# Usage:
#   make all_cpu_tests      # Run all CPU testbenches
#   make all_gpu_tests      # Run all GPU testbenches
#   make all_tests          # Run all testbenches (CPU + GPU)
#   make clean_logs         # Clean logs and build directories
#   make help               # Show help

.PHONY: all_tests all_cpu_tests all_gpu_tests clean_logs help

CPU_TB_DIR := tb/cpu
GPU_TB_DIR := tb/gpu

CPU_TESTS = mux_n branch_calc bypass_mux control_unit equ imme instruction_buffer interconnect coprocessor_system cpu_top dispatcher memory_system mmu gpu_op_queue gpu_result_buffer gpu_result_wb pipeline_stages register_file_system offload_logic clock_divider cpu_axi_wrapper red_pitaya_cpu_wrapper
GPU_TESTS = alu attribute_interpolator controller fragment_shader framebuffer gpu_register_file gpu_top instruction_decoder interconnect mmu rasterizer shader_core shader_loader axi_wrapper texture_unit vertex_fetch

all_cpu_tests:
	$(MAKE) -C $(CPU_TB_DIR) all_tests

all_gpu_tests:
	$(MAKE) -C $(GPU_TB_DIR) all_tests

all_tests:
	$(MAKE) all_cpu_tests
	$(MAKE) all_gpu_tests

clean_logs:
	$(MAKE) -C $(CPU_TB_DIR) clean_logs
	$(MAKE) -C $(GPU_TB_DIR) clean_logs

help:
	@echo "Available targets:"
	@echo "  all_cpu_tests   - Run all CPU testbenches (tb/cpu)"
	@echo "  all_gpu_tests   - Run all GPU testbenches (tb/gpu)"
	@echo "  all_tests       - Run all testbenches (CPU + GPU)"
	@echo "  clean_logs      - Clean logs and build directories in tb/cpu and tb/gpu"
	@echo "  help            - Show this help message"
	@echo ""
	@echo "Individual test invocation:"
	@echo "  <test> cpu      - Run individual CPU testbench (see below)"
	@echo "  <test> gpu      - Run individual GPU testbench (see below)"
	@echo ""
	@echo "CPU testbenches: $(CPU_TESTS)"
	@echo "GPU testbenches: $(GPU_TESTS)"

.PHONY: $(CPU_TESTS) $(GPU_TESTS)

$(CPU_TESTS):
	@if [ "$(filter cpu,$(MAKECMDGOALS))" ]; then \
		$(MAKE) -C $(CPU_TB_DIR) $@; \
	else \
		echo "Usage: make $@ cpu"; \
	fi

$(GPU_TESTS):
	@if [ "$(filter gpu,$(MAKECMDGOALS))" ]; then \
		$(MAKE) -C $(GPU_TB_DIR) $@; \
	else \
		echo "Usage: make $@ gpu"; \
	fi
