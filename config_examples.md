# Config Examples

## ekti

目标配置等价于：

```toml
model_provider = "ekti"
model = "gpt-5.5"
model_reasoning_effort = "xhigh"
disable_response_storage = true

[model_providers.ekti]
name = "ekti"
wire_api = "responses"
requires_openai_auth = true
base_url = "https://chat.ekti.cc/v1"
```

## 9router

目标配置等价于：

```toml
model = "cc-pro"
model_provider = "9router"

["model_providers.9router"]
name = "9Router"
base_url = "http://127.0.0.1:20128/v1"
wire_api = "responses"

[agents.subagent]
model = "cc-normal"
```

## 路径说明

- Windows 默认 Codex 根目录：`C:\Users\<用户名>\.codex`
- macOS 默认 Codex 根目录：`~/.codex`

如果默认路径不是你当前机器的实际路径，可以显式传：

```bash
bash ./run_codex_switcher.sh --codex-root ~/.codex --provider ekti --model gpt-5.5 --dry-run
```
