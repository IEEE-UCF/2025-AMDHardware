# CPU Offload System Documentation

## Overview

The CPU offload system provides a comprehensive framework for dispatching instructions to specialized coprocessors while maintaining proper pipeline coordination and hazard detection. The system consists of three main components:

1. **Offload Stall Handler** (`offload_stall_handler.sv`)
2. **Offload Destination Table** (`offload_destination_table.sv`) 
3. **Offload Manager** (`offload_manager.sv`)

## Architecture

### System Components

```
CPU Pipeline → Offload Manager → Coprocessors
                     ↓
            ┌─────────────────────┐
            │  Stall Handler      │←── Pipeline Hazards
            │  Destination Table  │←── Instruction Tracking
            │  Dispatcher Logic   │←── CP Selection
            └─────────────────────┘
```

### Coprocessor Mapping

- **CP0**: System Control (CSR, exceptions, privileged instructions)
- **CP1**: Floating Point Unit (FPU operations)
- **CP2**: Memory Management (TLB, cache control)
- **CP3**: GPU/Custom Operations (optional)

## Components

### 1. Offload Stall Handler

**Purpose**: Manages pipeline stalls when instructions are offloaded to coprocessors.

**Key Features**:
- RAW (Read After Write) hazard detection
- WAW (Write After Write) hazard detection  
- Structural hazard detection
- Coprocessor busy/exception handling
- Timeout protection
- Memory conflict detection

**Stall Conditions**:
- `STALL_CP_BUSY`: Coprocessor is busy
- `STALL_DATA_HAZARD`: Data dependency detected
- `STALL_STRUCTURAL_HAZARD`: Resource conflict
- `STALL_CP_EXCEPTION`: Coprocessor exception
- `STALL_MEM_CONFLICT`: Memory system conflict
- `STALL_CP_TIMEOUT`: Operation timeout
- `STALL_RESOURCE_CONFLICT`: General resource conflict

### 2. Offload Destination Table

**Purpose**: Tracks offloaded instructions and manages routing to appropriate coprocessors.

**Key Features**:
- Instruction classification by opcode
- Coprocessor availability tracking
- Operation completion tracking
- Exception handling
- Performance statistics

**Table Entry Structure**:
```systemverilog
typedef struct packed {
    logic                  valid;
    logic                  completed;
    logic                  exception_flag;
    logic [INST_WIDTH-1:0] instruction;
    logic [ADDR_WIDTH-1:0] pc;
    logic [1:0]            cp_select;
    logic [TAG_WIDTH-1:0]  tag;
    logic [4:0]            rd;
    logic [DATA_WIDTH-1:0] result;
    logic [3:0]            exception_code;
    logic [31:0]           timestamp;
} table_entry_t;
```

### 3. Offload Manager

**Purpose**: Unified interface integrating all offload components with the CPU pipeline.

**Key Features**:
- Complete pipeline integration
- Coordinated stall management
- Result forwarding
- Statistics collection
- Flush operations support

## Instruction Classification

Instructions are classified by opcode for coprocessor dispatch:

| Opcode    | Format     | Coprocessor | Description |
|-----------|------------|-------------|-------------|
| 7'b1110011| System     | CP0         | CSR, exceptions |
| 7'b1010011| FP         | CP1         | Floating point |
| 7'b0001011| Custom-0   | CP2         | Memory management |
| 7'b0101011| Custom-1   | CP3         | GPU operations |

## Pipeline Integration

### Stall Propagation

The offload system integrates with the CPU pipeline stages:

```
IF → ID → EX → MM → WB
 ↓    ↓    ↓    ↓    ↓
 Stall signals propagate upstream when dependencies detected
```

### Hazard Detection

**RAW Hazards**:
- Detect when offload instruction reads register being written by:
  - Pending coprocessor operation
  - EX/MM/WB pipeline stages

**WAW Hazards**:
- Detect when offload instruction writes to same register as:
  - Pending coprocessor operation
  - EX/MM pipeline stages

## Configuration Parameters

### Offload Stall Handler
- `STALL_TIMEOUT`: Maximum stall cycles before timeout (default: 1024)
- `CP_NUM`: Number of coprocessors (default: 4)

### Destination Table
- `TABLE_ENTRIES`: Number of tracking entries (default: 16)
- `TAG_WIDTH`: Tag width for instruction tracking (default: 4)

### Offload Manager
- Combines all component parameters
- Provides unified configuration interface

## Usage Example

```systemverilog
// Instantiate offload manager
offload_manager #(
    .ADDR_WIDTH(64),
    .DATA_WIDTH(64),
    .INST_WIDTH(32),
    .CP_NUM(4),
    .TABLE_ENTRIES(16),
    .STALL_TIMEOUT(1024)
) offload_mgr (
    .clk(clk),
    .rst_n(rst_n),
    
    // CPU pipeline interface
    .if_valid(if_valid),
    .if_pc(if_pc),
    .id_valid(id_valid),
    .id_instruction(id_instruction),
    // ... other pipeline signals
    
    // Coprocessor interface
    .cp_valid(cp_valid),
    .cp_instruction(cp_instruction),
    .cp_data_in(cp_data_in),
    .cp_select(cp_select),
    .cp_data_out(cp_data_out),
    .cp_ready(cp_ready),
    // ... other coprocessor signals
    
    // Control outputs
    .global_stall(global_stall),
    .result_valid(result_valid),
    .result_data(result_data)
);
```

## Testing

### Test Coverage

**Offload Stall Handler Tests**:
- Basic stall handling
- Coprocessor busy conditions
- RAW hazard detection
- WAW hazard detection
- Exception handling
- Timeout mechanism
- Memory conflict handling
- Pipeline stage hazards

**Running Tests**:
```bash
# Run all offload tests
make test-offload-stall

# Run specific test
cd tb && python3 -m pytest offload_stall_handler_tb.py::test_raw_hazard_detection -v
```

## Performance Considerations

### Stall Minimization
- Early coprocessor availability detection
- Efficient hazard resolution
- Parallel operation scheduling

### Resource Usage
- Configurable table sizes
- Optional timeout protection
- Selective flush operations

### Debugging Support
- Comprehensive stall reason reporting
- Operation tracking statistics
- Performance counters

## Future Enhancements

1. **Dynamic Scheduling**: Out-of-order coprocessor dispatch
2. **Load Balancing**: Distribution across multiple coprocessors
3. **Adaptive Timeouts**: Dynamic timeout based on operation type
4. **Advanced Hazard Resolution**: Register renaming support
5. **Power Management**: Coprocessor power gating integration

## Integration Notes

- Requires proper coprocessor interface implementation
- Pipeline stages must support stall signals
- Memory system must provide conflict detection
- Exception handling must be coordinated with main CPU

## See Also

- `dispatcher.sv` - Basic coprocessor dispatcher
- `coprocessor_system.sv` - Coprocessor system integration
- `cpu_top.sv` - Main CPU integration example
