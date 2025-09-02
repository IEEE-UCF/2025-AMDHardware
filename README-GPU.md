# AOHW25

## Team Information

- **Team number:** AOHW25_684
- **Project name:** AMDHardware-GPU
- **University name:** The University of Central Florida
- **Participant(s):**
   - Rafeed Khan
   - Yousef Alaa Awad
   - Kevin Maa
   - Franco Mezzarapa
- **Supervisor:** Dr. Suboh Suboh

# KnightGPU

KnightGPU is a hardware accelerated 3D graphics processor for the Red Pitaya. For AOHW2025, we have implemented a complete rendering pipeline with vertex transformation, triangle rasterization, and texture mapping. The design features a custom shader core with SIMD vector operations, hardware barycentric interpolation for fragment attributes, and a tile-based rendering approach for efficient memory usage on FPGA resources.

## Directory Structure

- `src/gpu` — Main SystemVerilog modules (GPU core, ALU, MMU, etc.)
- `src/gpurtl_utils` — Utility SystemVerilog modules (FIFO, mux, etc.)
- `tb/gpu` — Python cocotb testbenches for each module
- `sw/` — Software: drivers, host interface, assembler, example programs
- `docs/` — Documentation (architecture, ISA, memory map, etc.)
- `synth/` — Synthesis and simulation scripts, FPGA project files

### Key Specifications
- **Resolution**: 640x480 (configurable)
- **Data Width**: 32-bit
- **Vector Size**: 4 (RGBA)
- **Coordinate Width**: 10-bit (for screen coordinates)
- **Texture Size**: 256x256
- **Instruction Depth**: 256 instructions
- **FIFO Depth**: 64 entries
- **Pipeline Stages**: 5 (Vertex Fetch → Vertex Shader → Rasterization → Fragment Shader → Framebuffer)

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
```

### Simulation & Testing

To run the test benches, the makefile following format.

```bash
make [testbench] gpu 
```
To find the files needed for testing, 
```bash
make help
```
will list all of them. 

This command will use CocoTB to test the testbenches, if comprehensive testing is needed, put

```bash
make {rest of command} gpu SIM=Verilator
```
at the end of the command.

```bash
# Example

make attribute_interpolator gpu SIM=Verilator
```
