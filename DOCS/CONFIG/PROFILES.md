# Configuration Profiles

> Profile management for C.E.H. — Easy and Advanced configuration modes.

## Overview

C.E.H. supports **configuration profiles** stored in `profiles.yaml`. Profiles let you save, load, clone, and delete sets of model parameters without editing `agent.md` manually.

Profiles are managed via:

- **`ProfileManager`** class (`src/c_e_h/profile_manager.py`)
- **Interactive Launcher** (`ceh run` — step 3–4)
- **CLI** (future: `ceh profile list`, `ceh profile load`, etc.)

## File Format

`profiles.yaml` is a **multi-document YAML** file. Each profile is a YAML document separated by `---`.

```yaml
---
name: default
model: ''
n_gpu_layers: -1
threads: null
ctx_size: 8192
flash_attn: auto
cache_type_k: q8_0
cache_type_v: q8_0
n_cpu_moe_draft: 0
temperature: 0.7
---
name: fast
model: ./models/llama-3-8b.Q4_K_M.gguf
n_gpu_layers: -1
threads: 4
ctx_size: 4096
flash_attn: on
cache_type_k: q8_0
cache_type_v: q8_0
n_cpu_moe_draft: 0
temperature: 0.8
```

## Easy Mode Parameters

Easy mode contains the **9 most-common** llama.cpp parameters.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | *(required)* | Unique profile name |
| `model` | `str` | *(required)* | Path to the GGUF model file |
| `n_gpu_layers` | `int` | `-1` | Number of layers to offload to GPU (`-1` = all layers) |
| `threads` | `int \| None` | `None` | Number of CPU threads (`None` = auto-detect) |
| `ctx_size` | `int` | `8192` | Context window size in tokens |
| `flash_attn` | `str` | `"auto"` | Flash attention mode: `"on"`, `"off"`, or `"auto"` |
| `cache_type_k` | `str` | `"q8_0"` | Key cache quantization type |
| `cache_type_v` | `str` | `"q8_0"` | Value cache quantization type |
| `n_cpu_moe_draft` | `int` | `0` | Number of CPU threads for MoE draft (`0` = disabled) |

> **Note:** `temperature` and other sampling parameters are **Advanced Mode only**. See [`EasyProfile`](src/c_e_h/profile_manager.py:50).

## Advanced Mode Parameters

Advanced mode extends Easy mode with the **full llama.cpp flag set** (120+ flags). Key additional parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `top_k` | `int` | `40` | Top-K threshold |
| `top_p` | `float` | `0.95` | Top-P threshold (`0.0`–`1.0`) |
| `seed` | `int` | `-1` | Random seed (`-1` = time-based) |
| `repeat_penalty` | `float` | `1.1` | Repeat penalty |
| `lora` | `str \| None` | `None` | LoRA adapter path (optional) |
| `lora_base` | `str \| None` | `None` | LoRA base model path |
| `lora_scaled` | `float \| None` | `None` | LoRA scale factor |
| `ub_k_override` | `str \| None` | `None` | K-block override (e.g., `"f16"`) |
| `ub_v_override` | `str \| None` | `None` | V-block override (e.g., `"f16"`) |
| `server` | `bool` | `False` | Enable server mode |
| `port` | `int` | `8080` | Server port |
| `host` | `str` | `"127.0.0.1"` | Server host |
| `n_batch` | `int` | `512` | Batch size |
| `n_threads` | `int` | `None` | Override threads (alias) |
| `n_threads_batch` | `int` | `None` | Batch threads override |
| `rope_scaling` | `str \| None` | `None` | RoPE scaling type (`"linear"`, `"yarn"`) |
| `rope_freq_base` | `float` | `0.0` | RoPE base frequency (`0` = model default) |
| `logits_all` | `bool` | `False` | Compute logits for all tokens |
| `embeddings` | `bool` | `False` | Extract embeddings |
| `numa` | `bool` | `False` | NUMA-aware initialization |

> **Note:** The full Advanced profile supports 120+ parameters. The table above shows the most commonly used ones. See [`AdvancedProfile`](src/c_e_h/profile_manager.py) for the complete list.

## Example `profiles.yaml`

```yaml
---
name: default
model: /home/tarik/my-settings/models/Qwen3.6-35B-A3B/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
n_gpu_layers: -1
threads: null
ctx_size: 8192
flash_attn: auto
cache_type_k: q8_0
cache_type_v: q8_0
n_cpu_moe_draft: 0
temperature: 0.7
---
name: fast
model: ./models/llama-3-8b.Q4_K_M.gguf
n_gpu_layers: -1
threads: 4
ctx_size: 4096
flash_attn: on
cache_type_k: q8_0
cache_type_v: q8_0
n_cpu_moe_draft: 0
temperature: 0.8
top_k: 20
top_p: 0.9
seed: 42
---
name: research
model: ./models/mixtral-8x7b.Q4_K_M.gguf
n_gpu_layers: 30
threads: 8
ctx_size: 16384
flash_attn: auto
cache_type_k: q8_0
cache_type_v: q8_0
n_cpu_moe_draft: 0
temperature: 0.5
top_k: 50
top_p: 0.95
seed: -1
repeat_penalty: 1.05
server: true
port: 8080
```

## CLI Flag Reference for `ceh run`

The `ceh run` command (Interactive Launcher) accepts the following flags:

| Flag | Description | Default |
|------|-------------|---------|
| `--scan-dir <path>` | Directory to scan for `.gguf` models | Value from `agent.md` `models_directory`, then `"models/"` |
| `--profile <name>` | Load a specific profile by name | Interactive prompt |
| `--model <path>` | Override model path | Interactive prompt |
| `--ctx-size <n>` | Override context size | Profile value |
| `--gpu-layers <n>` | Override GPU layers | Profile value |
| `--threads <n>` | Override CPU threads | Profile value |
| `--temperature <f>` | Override temperature | Profile value |
| `--non-interactive` | Skip interactive prompts, use defaults | Interactive mode |
| `--default-profile <name>` | Default profile to auto-load | Value from `agent.md` `default_profile` |

### Non-Interactive Mode

When `--non-interactive` is passed, the launcher:

1. Scans for models in `--scan-dir` (or default)
2. Loads the profile specified by `--profile` (or `--default-profile`)
3. Applies any `--model`, `--ctx-size`, etc. overrides
4. Launches the agent immediately

If no profile is specified and `default_profile` is set in `agent.md`, that profile is loaded automatically.

## Programmatic Usage

```python
from c_e_h.profile_manager import ProfileManager

pm = ProfileManager()

# List all profiles
names = pm.list()
print(names)  # ['default', 'fast', 'research']

# Load a profile
profile = pm.read("fast")
print(profile.model)  # './models/llama-3-8b.Q4_K_M.gguf'

# Create a new profile
pm.create("my-profile", "easy", model="./models/my-model.gguf", ctx_size=16384)

# Clone a profile
pm.clone("fast", "fast-v2")

# Update a profile
pm.update("fast", ctx_size=8192, temperature=0.6)

# Delete a profile
pm.delete("fast-v2")
```

## Security

- `profiles.yaml` is created with `0600` permissions (owner read/write only) when first initialized.
- Profile names are validated: alphanumeric, hyphens, underscores only.
- Model paths are not validated for existence at save time (validated at load/launch).
