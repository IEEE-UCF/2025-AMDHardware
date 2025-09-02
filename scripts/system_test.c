#define RESULT_BASE 0x1000
#define VERTEX_BASE 0x2000
#define FRAMEBUFFER 0x3000

// gpu registers (from gpu_top.sv)
#define GPU_CONTROL 0x00000000
#define GPU_STATUS 0x00000004
#define GPU_VERTEX_BASE 0x00000008
#define GPU_VERTEX_COUNT 0x0000000C
#define GPU_PC 0x00000010
#define GPU_SHADER_BASE 0x00001000

// simple memory-mapped i/o
#define WRITE(addr, val) (*((volatile unsigned int *)(addr)) = (val))
#define READ(addr) (*((volatile unsigned int *)(addr)))

// entry point
void _start() {
  // set up stack pointer
  asm volatile("li sp, 0x8000");

  volatile unsigned int *results = (volatile unsigned int *)RESULT_BASE;

  // phase 1: cpu test - basic arithmetic

  // test 1: addition
  int a = 10;
  int b = 25;
  int sum = a + b;
  results[0] = sum; // should be 35 at 0x1000

  // test 2: multiplication (m extension)
  int x = 7;
  int y = 6;
  int product = x * y;
  results[1] = product; // should be 42 at 0x1004

  // test 3: cpu can write/read memory
  results[2] = 0x12345678;
  unsigned int readback = results[2];
  results[3] = (readback == 0x12345678) ? 1 : 0; // should be 1 at 0x100c

  // phase 2: cpu sets up gpu data

  // cpu writes vertex data for gpu to process
  volatile unsigned int *vertex_data = (volatile unsigned int *)VERTEX_BASE;

  // triangle vertex positions (simplified - just using integers)
  vertex_data[0] = 100; // v0_x
  vertex_data[1] = 100; // v0_y
  vertex_data[2] = 200; // v1_x
  vertex_data[3] = 200; // v1_y
  vertex_data[4] = 150; // v2_x
  vertex_data[5] = 250; // v2_y

  // triangle colors (rgb values)
  vertex_data[6] = 0xFF0000FF; // red for vertex 0
  vertex_data[7] = 0x00FF00FF; // green for vertex 1
  vertex_data[8] = 0x0000FFFF; // blue for vertex 2

  // uv coordinates (texture coordinates)
  vertex_data[9] = 0x8000;  // v0_u (0.5 in fixed point)
  vertex_data[10] = 0x0000; // v0_v (0.0)
  vertex_data[11] = 0x0000; // v1_u (0.0)
  vertex_data[12] = 0xFFFF; // v1_v (1.0)
  vertex_data[13] = 0xFFFF; // v2_u (1.0)
  vertex_data[14] = 0xFFFF; // v2_v (1.0)

  // record that cpu prepared data
  results[4] = 0xC0DEFEED; // cpu prepared data marker at 0x1010

  // phase 3: cpu loads gpu shader program

  // load a simple shader program
  volatile unsigned int *shader_mem = (volatile unsigned int *)GPU_SHADER_BASE;

  // simple shader instructions (using format from instruction_decoder.sv)
  // format: [31:27] opcode | [26:23] rd | [22:19] rs1 | [18:15] rs2 | [14:0]
  // imm

  // instruction 0: add r0, r0, r1 (opcode=1)
  shader_mem[0] = (1 << 27) | (0 << 23) | (0 << 19) | (1 << 15);

  // instruction 1: mul r2, r0, r1 (opcode=3)
  shader_mem[1] = (3 << 27) | (2 << 23) | (0 << 19) | (1 << 15);

  // instruction 2: mov r3, r2 (opcode=0x11)
  shader_mem[2] = (0x11 << 27) | (3 << 23) | (2 << 19);

  // record shader loaded
  results[5] = 0xC0DEC0DE; // shader loaded marker at 0x1014

  // phase 4: cpu triggers gpu

  // configure gpu registers
  WRITE(GPU_VERTEX_BASE, VERTEX_BASE); // tell gpu where vertices are
  WRITE(GPU_VERTEX_COUNT, 3);          // process 3 vertices (1 triangle)
  WRITE(GPU_PC, 0);                    // start shader at instruction 0

  // clear any pending interrupts first
  WRITE(GPU_CONTROL, 2); // bit 1 = clear irq

  // start gpu processing
  WRITE(GPU_CONTROL, 1); // bit 0 = start

  // record gpu started
  results[6] = 0x60BECA11; // gpu start marker at 0x1018

  // phase 5: cpu waits for gpu

  // wait for gpu to complete (poll status register)
  int wait_cycles = 0;
  unsigned int gpu_status = 0;

  do {
    gpu_status = READ(GPU_STATUS);
    wait_cycles++;
  } while ((gpu_status & 1) && (wait_cycles < 10000)); // bit 0 = busy

  // record wait results
  results[7] = gpu_status;  // gpu final status at 0x101c
  results[8] = wait_cycles; // how many cycles we waited at 0x1020

  // phase 6: cpu reads gpu results

  // check if gpu wrote to framebuffer
  volatile unsigned int *framebuffer = (volatile unsigned int *)FRAMEBUFFER;
  unsigned int pixel_sample = framebuffer[0]; // read first pixel

  results[9] = pixel_sample; // first framebuffer pixel at 0x1024

  // phase 7: cpu processes gpu output

  // cpu does calculation based on gpu result
  unsigned int masked = pixel_sample;
  masked = masked & 0x000000FF; // Force full 32-bit mask
  unsigned int cpu_gpu_combined = sum + masked;
  results[10] = cpu_gpu_combined; // combined result at 0x1028

  // phase 8: verification and summary

  // check if everything worked
  unsigned int all_good = 0;
  if (sum == 35 &&              // cpu math works
      product == 42 &&          // cpu multiply works
      readback == 0x12345678 && // memory works
      wait_cycles > 0 &&        // gpu ran
      wait_cycles < 10000)      // gpu finished
  {
    all_good = 1;
  }

  results[11] = all_good;   // pass/fail at 0x102c
  results[12] = 0xDEADBEEF; // cpu done marker at 0x1030
  results[13] = 0xCAFEBABE; // gpu done marker at 0x1034

  // calculate checksum of all results
  unsigned int checksum = 0;
  for (int i = 0; i < 14; i++) {
    checksum = checksum + results[i];
  }
  results[14] = checksum; // checksum at 0x1038

  // final completion marker
  results[15] = 0x600D600D; // "GOOD GOOD" at 0x103C

  // infinite loop (halt)
  while (1) {
    asm volatile("nop");
  }
}
