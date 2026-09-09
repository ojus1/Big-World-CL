#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$TASK_ROOT"
# /opt/rocm/llvm on this host points to a different compiler distribution.
HIPCXX=/opt/rocm/lib/llvm/bin/clang HIP_PATH=/opt/rocm \
cmake -S llama.cpp -B llama.cpp/build-rocm72 \
  -DGGML_HIP=ON -DGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/opt/rocm -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON
cmake --build llama.cpp/build-rocm72 --config Release -j 8 --target llama-server llama-bench
