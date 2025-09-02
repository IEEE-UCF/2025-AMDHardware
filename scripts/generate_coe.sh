#!/bin/bash
echo "memory_initialization_radix=16;"
echo "memory_initialization_vector="
hexdump -v -e '1/4 "%08x,\n"' system_test.bin | sed '$ s/,$/;/'
