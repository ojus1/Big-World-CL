#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export HIP_VISIBLE_DEVICES=0
exec "$TASK_ROOT/llama.cpp/build-rocm72/bin/llama-server" \
  -m "$TASK_ROOT/models/MiniCPM5-2B-Q8_0.gguf" --alias minicpm5-2b \
  --host 127.0.0.1 --port 8080 -ngl 999 -fa on \
  --parallel 32 -c 131072 --kv-unified --kv-unified-per-slot 32768 \
  -ctk f16 -ctv f16 -b 2048 -ub 512 -t 6 -tb 6 \
  --jinja \
  --reasoning off --reasoning-budget 0 \
  --metrics --slots --cache-ram 2048 --threads-http 64 "$@"
