# Config Examples

## 9router（推荐）

Codex 主会话走本地 9Router，App 内可切 `gpt-5.4` / `gpt-5.5` 裸名。先确保 oa-first combo 已写入（见 [`9router_codex_aliases.md`](9router_codex_aliases.md)）。

目标配置等价于：

```toml
model = "gpt-5.5"
model_provider = "9router"
model_reasoning_effort = "medium"
disable_response_storage = true

["model_providers.9router"]
name = "9Router"
base_url = "http://127.0.0.1:20128/v1"
wire_api = "responses"

[agents.subagent]
model = "cc-normal"
```

切换命令：

```bash
bash ./run_codex_switcher.sh \
  --provider 9router \
  --model gpt-5.5 \
  --base-url http://127.0.0.1:20128/v1 \
  --wire-api responses \
  --subagent-model cc-normal
```

Combo 同步（404 或裸名未路由时）：

```bash
python3 sync_9router_codex_aliases.py --mirror-combos --dry-run
python3 sync_9router_codex_aliases.py --mirror-combos
```

## ekti（直连备选）

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

需在 Codex Settings 或 `~/.codex/auth.json` 里配置有效的 ekti `sk-...` key（`requires_openai_auth = true`）。

## 路径说明

- Windows 默认 Codex 根目录：`C:\Users\<用户名>\.codex`
- macOS 默认 Codex 根目录：`~/.codex`

如果默认路径不是你当前机器的实际路径，可以显式传：

```bash
bash ./run_codex_switcher.sh --codex-root ~/.codex --provider 9router --model gpt-5.5 --dry-run
```
