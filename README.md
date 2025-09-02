# AOHW25

## Team Information
- **Team number:** AOHW25_684
- **Project name:** AMDHardware CPU/GPU
- **University name:** The University of Central Florida
- **Participant(s):**
  - Rafeed Khan
  - Yousef Alaa Awad
  - Kevin Maa
  - Franco Mezzarapa
- **Supervisor:** Dr. Suboh Suboh

---

# [Link to Video Explanation](https://youtu.be/MD8FkJjmYvk)

# KnightCore

For AOHW2025, our team designed and implemented a complete CPU–GPU system-on-chip for the Red Pitaya 125-14 v1.1, **KnightCore**. The project integrates **KnightCPU**, a custom 32-bit RISC-V processor, with **KnightGPU**, a hardware accelerated graphics processor, to form a cohesive compute and rendering pipeline. The two cores communicate via an AXI4 interconnect for integration of computing and graphics workloads on FPGA hardware.

KnightCPU is a 32-bit RISC-V CPU implementing the RV32IMA instruction set with a 5-stage pipeline (IF, ID, EX, MEM, WB). It features hardware multiply/divide, atomic memory operations, hazard detection and forwarding, a coprocessor interface for accelerators, and native AXI4 support. The architecture follows a Harvard model with separate instruction and data caches, achieving a target frequency of 100 MHz on the Red Pitaya.

KnightGPU implements a programmable 3D graphics pipeline including vertex transformation, triangle rasterization, fragment shading, and texture mapping. It supports SIMD vector operations in its shader cores, hardware barycentric interpolation for per-fragment attributes, and tile-based rendering for efficient memory use. The GPU targets 640×480 resolution with configurable parameters such as 32-bit data paths, 256×256 textures, 10-bit coordinates, and a 64-entry FIFO for streaming commands.

Together, KnightCore and KnightGPU demonstrate a tightly coupled CPU–GPU hardware stack capable of both general-purpose computation and real-time graphics rendering on FPGA.

---

# Directory Structure

- `src/cpu` — CPU core modules (ALU, control unit, register file, etc.)
- `src/cpu/rtl_utils` — CPU utility modules (arbiter, mux, clock divider, etc.)
- `src/gpu` — GPU core modules (ALU, MMU, shader core, rasterizer, etc.)
- `src/gpu/rtl_utils` — GPU utility modules (FIFO, mux, etc.)
- `tb/cpu` — Cocotb testbenches for CPU
- `tb/gpu` — Cocotb testbenches for GPU
- `synth/` — Synthesis and simulation scripts, FPGA project files

---

# Key Specifications

**CPU (KnightCore):**
- ISA: RV32IMA (Integer, Multiply/Divide, Atomics)
- Pipeline: 5-stage (IF, ID, EX, MEM, WB)
- Data Path: 32-bit
- Register File: 32 general-purpose registers
- Memory: Harvard architecture (I/D caches)
- Clock Target: 100 MHz (Artix-7)
- Branch Prediction: Static not-taken
- Hazard Handling: Forwarding and stall logic

**GPU (KnightGPU):**
- Resolution: 640×480 (configurable)
- Data Width: 32-bit
- Vector Size: 4 (RGBA)
- Coordinate Width: 10-bit
- Texture Size: 256×256
- Instruction Depth: 256 instructions
- FIFO Depth: 64 entries
- Pipeline Stages: 5 (Vertex Fetch → Vertex Shader → Rasterization → Fragment Shader → Framebuffer)

---

# Getting Started

## Prerequisites

```bash
# Install Verilator (recommended version 4.0+)
sudo apt-get install verilator gtkwave make gcc g++

# Install Python dependencies for testbenches
sudo apt-get install python3 python3-pip 
# After this it is recomended you start a virtual environment
pip3 install cocotb cocotb-test pytest

# Install Icarus Verilog (alternative simulator)
sudo apt-get install iverilog
```

## Simulation & Testing

To run testbenches, use the makefile format:

```bash
make [testbench] cpu   # For CPU modules
make [testbench] gpu   # For GPU modules
```

For comprehensive testing with Verilator:

```bash
make [testbench] cpu SIM=verilator
make [testbench] gpu SIM=verilator
```

Run `make help` to list all available targets.
