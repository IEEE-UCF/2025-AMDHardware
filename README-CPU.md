# AOHW25

## Team Information

- **Team number:** AOHW25_684
- **Project name:** AMDHardware-CPU
- **University name:** The University of Central Florida
- **Participant(s):**
   - Rafeed Khan
   - Yousef Alaa Awad
   - Kevin Maa
   - Franco Mezzarapa
- **Supervisor:** Dr. Suboh Suboh

# KnightCore

KnightCore is a 32-bit RISC-V processor optimized for the Red Pitaya 125-14 version 1.1. For AOHW2025, we have implemented the RV32IMA instruction set with a 5-stage pipeline, hardware multiply/divide unit, and atomic memory operations. The design features forwarding logic for hazard mitigation, a coprocessor interface for custom accelerators, and native AXI4 interconnect support for integration with the KnightGPU graphics processor.

## Directory Structure

- `src/` — Main SystemVerilog modules (CPU core, ALU, control unit, etc.)
- `rtl_utils/` — Utility SystemVerilog modules (arbiter, mux, clock divider, etc.)
- `tb/` — Python cocotb testbenches for each module
- `sw/` — Software: bootloader, test programs, compiler toolchain
- `docs/` — Documentation (ISA implementation, pipeline stages, memory map)
- `synth/` — Synthesis and simulation scripts, FPGA project files

### Key Specifications
- **ISA**: RV32IMA (Integer, Multiply/Divide, Atomics)
- **Pipeline**: 5-stage (IF, ID, EX, MEM, WB)
- **Data Path**: 32-bit
- **Register File**: 32 general-purpose registers
- **Memory**: Harvard architecture with separate I/D caches
- **Clock Target**: 100 MHz on Artix-7
- **Branch Prediction**: Static not-taken
- **Hazard Handling**: Forwarding and stall logic

## Getting Started

### Prerequisites

```bash
# Install Verilator (recommended version 4.0+)
sudo apt-get install verilator gtkwave make gcc g++

# Install Python dependencies for testing
sudo apt-get install python3 python3-pip
pip3 install cocotb cocotb-test pytest

# Install Icarus Verilog (alternative simulator)
sudo apt-get install iverilog

# For synthesis reports
sudo apt-get install yosys

# Install RISC-V toolchain
sudo apt-get install gcc-riscv64-unknown-elf
```

### Simulation & Testing

To run the test benches, use the makefile following format:

```bash
make [file] 
```

To find the files needed for testing:
```bash
make help
```
will list all available targets.

This command will use CocoTB to test the testbenches. If comprehensive testing is needed, add:

```bash
SIM=verilator
```
at the end of the command.

```bash
# Examples

# Test ALU module
make test_alu SIM=verilator

# Test control unit
make test_control SIM=verilator

# Test full CPU pipeline
make test_cpu_top SIM=verilator
```