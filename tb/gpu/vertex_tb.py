
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer, FallingEdge
import random
import struct

CLK_PERIOD = 10

class Vertex:
    def __init__(self, attrs_per_vertex=8, attr_width=32):
        self.attrs_per_vertex = attrs_per_vertex
        self.attr_width = attr_width
        self.attributes = []
        
    def randomize(self):
        self.attributes = [random.randint(0, (1 << self.attr_width) - 1) 
                          for _ in range(self.attrs_per_vertex)]
        return self
    
    def set_position(self, x, y, z, w):
        self.attributes[0:4] = [x, y, z, w]
        return self
    
    def set_color(self, r, g, b, a):
        if self.attrs_per_vertex >= 8:
            self.attributes[4:8] = [r, g, b, a]
        return self
    
    def pack(self):
        packed = 0
        for i, attr in enumerate(self.attributes):
            packed |= (attr & ((1 << self.attr_width) - 1)) << (i * self.attr_width)
        return packed
    
    def unpack(self, packed_data):
        mask = (1 << self.attr_width) - 1
        self.attributes = []
        for i in range(self.attrs_per_vertex):
            self.attributes.append((packed_data >> (i * self.attr_width)) & mask)
        return self

class VertexBuffer:
    def __init__(self, base_addr=0x1000):
        self.base_addr = base_addr
        self.vertices = {}
        self.attr_width = 32
        self.attrs_per_vertex = 8
        self.vertex_stride = (self.attr_width * self.attrs_per_vertex) // 8
        
    def add_vertex(self, index, vertex):
        addr = self.base_addr + (index * self.vertex_stride)
        self.vertices[addr] = vertex.pack()
        return addr
    
    def get_vertex_data(self, addr):
        if addr in self.vertices:
            return self.vertices[addr]
        return 0xDEADBEEFDEADBEEF
    
    def create_triangle(self, start_index=0):
        v0 = Vertex().set_position(100, 100, 0, 1).set_color(255, 0, 0, 255)
        v1 = Vertex().set_position(200, 100, 0, 1).set_color(0, 255, 0, 255)
        v2 = Vertex().set_position(150, 200, 0, 1).set_color(0, 0, 255, 255)
        
        self.add_vertex(start_index, v0)
        self.add_vertex(start_index + 1, v1)
        self.add_vertex(start_index + 2, v2)
        return [v0, v1, v2]
    
    def create_mesh(self, num_vertices):
        vertices = []
        for i in range(num_vertices):
            v = Vertex().randomize()
            self.add_vertex(i, v)
            vertices.append(v)
        return vertices

class MemoryModel:
    def __init__(self, dut, vertex_buffer):
        self.dut = dut
        self.vertex_buffer = vertex_buffer
        self.latency_min = 1
        self.latency_max = 5
        self.current_request = None
        self.response_counter = 0
        self.ready_was_high = False
        self.stats = {
            'total_requests': 0,
            'total_cycles': 0,
            'addresses_accessed': set()
        }
        
    async def handle_requests(self):
        while True:
            await RisingEdge(self.dut.clk)
            
            # Check for new request
            if self.dut.o_mem_req.value == 1 and self.current_request is None:
                addr = int(self.dut.o_mem_addr.value)
                self.current_request = addr
                self.response_counter = random.randint(self.latency_min, self.latency_max)
                self.stats['total_requests'] += 1
                self.stats['addresses_accessed'].add(addr)
                
            # Handle ongoing request
            if self.current_request is not None:
                if self.response_counter > 0:
                    self.response_counter -= 1
                    self.dut.i_mem_ready.value = 0
                    
                if self.response_counter == 0:
                    if not self.ready_was_high:
                        # First cycle: set ready and data
                        self.dut.i_mem_ready.value = 1
                        self.dut.i_mem_rdata.value = self.vertex_buffer.get_vertex_data(self.current_request)
                        self.ready_was_high = True
                    else:
                        # Second cycle: clear ready
                        self.dut.i_mem_ready.value = 0
                        self.current_request = None
                        self.ready_was_high = False
            else:
                self.dut.i_mem_ready.value = 0
            
            self.stats['total_cycles'] += 1

async def reset_dut(dut):
    dut.i_start_fetch.value = 0
    dut.i_base_addr.value = 0
    dut.i_vertex_index.value = 0
    dut.i_mem_ready.value = 0
    dut.i_mem_rdata.value = 0
    dut.rst_n.value = 0
    
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

async def fetch_vertex(dut, base_addr, vertex_index, timeout=100):
    dut.i_base_addr.value = base_addr
    dut.i_vertex_index.value = vertex_index
    dut.i_start_fetch.value = 1
    
    await RisingEdge(dut.clk)
    dut.i_start_fetch.value = 0
    
    cycle_count = 0
    while dut.o_fetch_done.value != 1:
        await RisingEdge(dut.clk)
        cycle_count += 1
        if cycle_count > timeout:
            raise TimeoutError(f"Vertex fetch timeout for index {vertex_index}")
    
    result = int(dut.o_vertex_data.value)
    await RisingEdge(dut.clk)
    
    return result, cycle_count

@cocotb.test()
async def test_vertex_fetch_basic(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    attr_width = int(dut.ATTR_WIDTH.value)
    attrs_per_vertex = int(dut.ATTRS_PER_VERTEX.value)
    
    dut._log.info(f"Starting vertex fetch test (ATTR_WIDTH={attr_width}, ATTRS_PER_VERTEX={attrs_per_vertex})")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0x10000)
    memory = MemoryModel(dut, vertex_buffer)
    cocotb.start_soon(memory.handle_requests())
    
    dut._log.info("Test 1: Single vertex fetch")
    
    test_vertex = Vertex().set_position(123, 456, 789, 1).set_color(255, 128, 64, 255)
    vertex_buffer.add_vertex(0, test_vertex)
    
    result, cycles = await fetch_vertex(dut, vertex_buffer.base_addr, 0)
    
    expected = test_vertex.pack()
    assert result == expected, f"Vertex mismatch: got 0x{result:x}, expected 0x{expected:x}"
    
    dut._log.info(f"  Single vertex fetched in {cycles} cycles")
    
    dut._log.info("Test 2: Multiple sequential vertices")
    
    vertices = vertex_buffer.create_triangle()
    
    for i, vertex in enumerate(vertices):
        result, cycles = await fetch_vertex(dut, vertex_buffer.base_addr, i)
        expected = vertex.pack()
        assert result == expected, f"Triangle vertex {i} mismatch"
        dut._log.info(f"  Vertex {i} fetched in {cycles} cycles")
    
    dut._log.info("Basic vertex fetch test passed!")

@cocotb.test()
async def test_vertex_fetch_addressing(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    attr_width = int(dut.ATTR_WIDTH.value)
    attrs_per_vertex = int(dut.ATTRS_PER_VERTEX.value)
    vertex_stride = (attr_width * attrs_per_vertex) // 8
    
    dut._log.info("Testing vertex addressing calculations")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0x80000)
    memory = MemoryModel(dut, vertex_buffer)
    cocotb.start_soon(memory.handle_requests())
    
    test_indices = [0, 1, 10, 100, 255, 1000, 65535]
    
    for idx in test_indices:
        if idx <= 65535:
            vertex = Vertex().randomize()
            vertex_buffer.add_vertex(idx, vertex)
            
            expected_addr = vertex_buffer.base_addr + (idx * vertex_stride)
            
            dut.i_base_addr.value = vertex_buffer.base_addr
            dut.i_vertex_index.value = idx
            dut.i_start_fetch.value = 1
            
            await RisingEdge(dut.clk)
            dut.i_start_fetch.value = 0
            await RisingEdge(dut.clk)
            
            actual_addr = int(dut.o_mem_addr.value)
            assert actual_addr == expected_addr, f"Address calculation wrong for index {idx}: got 0x{actual_addr:x}, expected 0x{expected_addr:x}"
            
            dut._log.info(f"  Index {idx}: address 0x{actual_addr:08x} ✓")
            
            while dut.o_fetch_done.value != 1:
                await RisingEdge(dut.clk)
    
    dut._log.info("Addressing test passed!")

@cocotb.test()
async def test_vertex_fetch_pipeline(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing pipelined vertex fetches")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0x20000)
    memory = MemoryModel(dut, vertex_buffer)
    memory.latency_min = 2
    memory.latency_max = 2
    cocotb.start_soon(memory.handle_requests())
    
    num_vertices = 50
    vertices = vertex_buffer.create_mesh(num_vertices)
    
    total_cycles = 0
    fetch_times = []
    
    for i in range(num_vertices):
        start_time = cocotb.utils.get_sim_time(units='ns')
        
        result, cycles = await fetch_vertex(dut, vertex_buffer.base_addr, i)
        
        end_time = cocotb.utils.get_sim_time(units='ns')
        fetch_time = end_time - start_time
        fetch_times.append(fetch_time)
        total_cycles += cycles
        
        expected = vertices[i].pack()
        assert result == expected, f"Vertex {i} data mismatch"
        
        if (i + 1) % 10 == 0:
            dut._log.info(f"  Fetched {i + 1}/{num_vertices} vertices")
    
    avg_fetch_time = sum(fetch_times) / len(fetch_times)
    throughput = num_vertices / (total_cycles * CLK_PERIOD / 1000)
    
    dut._log.info(f"Pipeline performance:")
    dut._log.info(f"  Average fetch time: {avg_fetch_time:.2f} ns")
    dut._log.info(f"  Throughput: {throughput:.2f} vertices/μs")
    
    dut._log.info("Pipeline test passed!")

@cocotb.test()
async def test_vertex_fetch_memory_stalls(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing behavior with memory stalls")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0x30000)
    
    class VariableLatencyMemory(MemoryModel):
        def __init__(self, dut, vertex_buffer):
            super().__init__(dut, vertex_buffer)
            self.stall_pattern = [1, 1, 5, 1, 10, 2, 1, 20, 1, 1]
            self.pattern_index = 0
        
        async def handle_requests(self):
            while True:
                await RisingEdge(self.dut.clk)
                
                # Check for new request
                if self.dut.o_mem_req.value == 1 and self.current_request is None:
                    addr = int(self.dut.o_mem_addr.value)
                    self.current_request = addr
                    self.response_counter = self.stall_pattern[self.pattern_index % len(self.stall_pattern)]
                    self.pattern_index += 1
                    self.stats['total_requests'] += 1
                    
                # Handle ongoing request
                if self.current_request is not None:
                    if self.response_counter > 0:
                        self.response_counter -= 1
                        self.dut.i_mem_ready.value = 0
                        
                    if self.response_counter == 0:
                        if not self.ready_was_high:
                            # First cycle: set ready and data
                            self.dut.i_mem_ready.value = 1
                            self.dut.i_mem_rdata.value = self.vertex_buffer.get_vertex_data(self.current_request)
                            self.ready_was_high = True
                        else:
                            # Second cycle: clear ready
                            self.dut.i_mem_ready.value = 0
                            self.current_request = None
                            self.ready_was_high = False
                else:
                    self.dut.i_mem_ready.value = 0
    
    memory = VariableLatencyMemory(dut, vertex_buffer)
    cocotb.start_soon(memory.handle_requests())
    
    vertices = vertex_buffer.create_mesh(10)
    
    for i in range(10):
        dut._log.info(f"  Fetch {i}: expecting {memory.stall_pattern[i]} cycle latency")
        result, cycles = await fetch_vertex(dut, vertex_buffer.base_addr, i)
        expected = vertices[i].pack()
        assert result == expected, f"Data mismatch with stall pattern"
        dut._log.info(f"    Completed in {cycles} cycles")
    
    dut._log.info("Memory stall test passed!")

@cocotb.test()
async def test_vertex_fetch_stress(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Starting vertex fetch stress test")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=random.randint(0x10000, 0xF0000))
    memory = MemoryModel(dut, vertex_buffer)
    memory.latency_min = 1
    memory.latency_max = 10
    cocotb.start_soon(memory.handle_requests())
    
    num_operations = 500
    vertices = vertex_buffer.create_mesh(256)
    
    errors = 0
    total_cycles = 0
    
    for op in range(num_operations):
        vertex_index = random.randint(0, 255)
        
        try:
            result, cycles = await fetch_vertex(dut, vertex_buffer.base_addr, vertex_index, timeout=50)
            total_cycles += cycles
            
            expected = vertices[vertex_index].pack()
            if result != expected:
                errors += 1
                dut._log.error(f"Mismatch at index {vertex_index}")
        except TimeoutError:
            errors += 1
            dut._log.error(f"Timeout at index {vertex_index}")
        
        if (op + 1) % 100 == 0:
            dut._log.info(f"  Progress: {op + 1}/{num_operations} operations")
    
    assert errors == 0, f"Stress test failed with {errors} errors"
    
    avg_cycles = total_cycles / num_operations
    dut._log.info(f"Stress test completed!")
    dut._log.info(f"  Total operations: {num_operations}")
    dut._log.info(f"  Average cycles per fetch: {avg_cycles:.2f}")
    dut._log.info(f"  Memory requests: {memory.stats['total_requests']}")

@cocotb.test()
async def test_vertex_fetch_boundary(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing boundary conditions")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0)
    memory = MemoryModel(dut, vertex_buffer)
    cocotb.start_soon(memory.handle_requests())
    
    dut._log.info("Test 1: Base address = 0")
    v = Vertex().randomize()
    vertex_buffer.add_vertex(0, v)
    result, _ = await fetch_vertex(dut, 0, 0)
    assert result == v.pack(), "Failed with base_addr = 0"
    
    dut._log.info("Test 2: Maximum vertex index")
    max_index = 0xFFFF
    v = Vertex().randomize()
    vertex_buffer.base_addr = 0x1000
    vertex_buffer.add_vertex(max_index, v)
    result, _ = await fetch_vertex(dut, vertex_buffer.base_addr, max_index)
    assert result == v.pack(), "Failed with max vertex index"
    
    dut._log.info("Test 3: Maximum base address")
    vertex_buffer.base_addr = 0xFFFFF000
    v = Vertex().randomize()
    vertex_buffer.add_vertex(0, v)
    result, _ = await fetch_vertex(dut, vertex_buffer.base_addr, 0)
    assert result == v.pack(), "Failed with max base address"
    
    dut._log.info("Test 4: Rapid state transitions")
    vertex_buffer.base_addr = 0x5000
    vertices = vertex_buffer.create_mesh(5)
    
    for i in range(5):
        dut.i_base_addr.value = vertex_buffer.base_addr
        dut.i_vertex_index.value = i
        dut.i_start_fetch.value = 1
        await RisingEdge(dut.clk)
        dut.i_start_fetch.value = 0
        
        for _ in range(2):
            await RisingEdge(dut.clk)
            if dut.o_fetch_done.value == 1:
                break
        
        while dut.o_fetch_done.value != 1:
            await RisingEdge(dut.clk)
    
    dut._log.info("Boundary test passed!")

@cocotb.test()
async def test_vertex_fetch_reset(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Testing reset behavior")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0x6000)
    memory = MemoryModel(dut, vertex_buffer)
    cocotb.start_soon(memory.handle_requests())
    
    vertices = vertex_buffer.create_mesh(10)
    
    dut._log.info("Test 1: Reset during fetch")
    
    dut.i_base_addr.value = vertex_buffer.base_addr
    dut.i_vertex_index.value = 5
    dut.i_start_fetch.value = 1
    await RisingEdge(dut.clk)
    dut.i_start_fetch.value = 0
    
    await ClockCycles(dut.clk, 2)
    
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    
    assert dut.o_mem_req.value == 0, "Memory request should be cleared on reset"
    assert dut.o_fetch_done.value == 0, "Fetch done should be cleared on reset"
    
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    
    dut._log.info("Test 2: Normal operation after reset")
    
    for i in range(3):
        result, cycles = await fetch_vertex(dut, vertex_buffer.base_addr, i)
        expected = vertices[i].pack()
        assert result == expected, f"Post-reset fetch {i} failed"
        dut._log.info(f"  Post-reset fetch {i} successful")
    
    dut._log.info("Reset test passed!")

@cocotb.test()
async def test_vertex_fetch_performance(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD, units="ns").start())
    
    dut._log.info("Performance benchmarking")
    
    await reset_dut(dut)
    
    vertex_buffer = VertexBuffer(base_addr=0x100000)
    
    test_configs = [
        ("Best case (1 cycle)", 1, 1),
        ("Typical (2-3 cycles)", 2, 3),
        ("Slow memory (5-10 cycles)", 5, 10),
        ("Very slow (10-20 cycles)", 10, 20),
    ]
    
    for config_name, min_lat, max_lat in test_configs:
        memory = MemoryModel(dut, vertex_buffer)
        memory.latency_min = min_lat
        memory.latency_max = max_lat
        cocotb.start_soon(memory.handle_requests())
        
        vertices = vertex_buffer.create_mesh(100)
        
        start_time = cocotb.utils.get_sim_time(units='ns')
        
        for i in range(100):
            result, _ = await fetch_vertex(dut, vertex_buffer.base_addr, i)
            expected = vertices[i].pack()
            assert result == expected
        
        end_time = cocotb.utils.get_sim_time(units='ns')
        total_time = end_time - start_time
        throughput = 100000 / total_time
        
        dut._log.info(f"  {config_name}:")
        dut._log.info(f"    Total time: {total_time:.0f} ns")
        dut._log.info(f"    Throughput: {throughput:.2f} vertices/μs")
        
        await ClockCycles(dut.clk, 10)
    
    dut._log.info("Performance benchmark completed!")