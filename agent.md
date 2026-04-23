# Agent Configuration

## Identity
name: CEH-Agent
version: 0.1.0
description: Your local AI assistant

## Model Settings
model:
  path: /home/tarik/my-settings/models/Qwen3.6-35B-A3B/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
  n_gpu_layers: -1        # Offload all layers to GPU (Apple Silicon / Vulkan)
  n_ctx: 8192              # Context window size
  temperature: 0.7         # Sampling temperature

## Memory Settings
memory:
  max_context_tokens: 8192
  compaction_strategy: microcompact  # snip | microcompact

## Permission Settings
permissions:
  mode: autonomous         # autonomous | approval
  max_auto_errors: 3       # Switch to approval mode after N errors
  success_reset: 5         # Reset to autonomous after N successful steps

## Tools
tools:
  file_read: true
  file_write: true
  execute_command: true
  web_search: false        # Disabled by default

## Logging
logging:
  level: INFO              # DEBUG | INFO | WARNING | ERROR
  format: json             # json | text
