# Codex Switcher

独立小工具，用来处理 Codex provider 切换时最容易出问题的两件事：

1. 切换 `config.toml` 中的 provider 配置
2. 修复历史对话可见性

它会把下面这些事情串成一次操作：

- 备份 `C:\Users\Andrew\.codex`
- 可选地改写 `config.toml`
- 统一修复 `sessions` / `archived_sessions` 中历史 `rollout` 的 `session_meta.payload.model_provider`
- 统一修复 `state_5.sqlite` 中 `threads.model_provider`

## 文件说明

- `codex_switcher.py`
  核心脚本。支持 dry run、备份、切 provider、修历史。
- `run_codex_switcher.ps1`
  PowerShell 启动入口。适合双击或命令行直接调用。
- `run_codex_switcher.sh`
  macOS / Linux 启动入口。适合终端直接调用。
- `AI_INSTRUCTIONS.md`
  给 AI 的固定操作指令模板。把这个文件给下一个 AI，它就能按统一流程做。
- `config_examples.md`
  常见 provider 配置示例。
- `9router_codex_aliases.md`
  Codex App 裸模型名与 9Router combo/alias 对齐说明。
- `sync_9router_codex_aliases.py`
  一键镜像 `gpt-5.x` combo 或修复 ekti alias。

## 推荐用法

先彻底关闭 Codex，再执行。

### 正式切到 9router（推荐）

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider 9router -Model gpt-5.5 -BaseUrl http://127.0.0.1:20128/v1 -WireApi responses -SubagentModel cc-normal
```

```bash
bash ./run_codex_switcher.sh --provider 9router --model gpt-5.5 --base-url http://127.0.0.1:20128/v1 --wire-api responses --subagent-model cc-normal
```

### 只看会改什么

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider 9router -Model gpt-5.5 -BaseUrl http://127.0.0.1:20128/v1 -WireApi responses -SubagentModel cc-normal -DryRun
```

### 正式切到 ekti（直连备选）

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider ekti -Model gpt-5.5 -ReasoningEffort xhigh -DisableResponseStorage -BaseUrl https://chat.ekti.cc/v1 -WireApi responses -RequiresOpenAIAuth
```

### 只修历史，不改 config.toml

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider 9router -RepairOnly
```

## macOS 用法

先彻底关闭 Codex，再执行。

### 正式切到 9router（推荐）

```bash
bash ./run_codex_switcher.sh --provider 9router --model gpt-5.5 --base-url http://127.0.0.1:20128/v1 --wire-api responses --subagent-model cc-normal
```

### 只看会改什么

```bash
bash ./run_codex_switcher.sh --provider 9router --model gpt-5.5 --base-url http://127.0.0.1:20128/v1 --wire-api responses --subagent-model cc-normal --dry-run
```

### 正式切到 ekti（直连备选）

```bash
bash ./run_codex_switcher.sh --provider ekti --model gpt-5.5 --reasoning-effort xhigh --disable-response-storage --base-url https://chat.ekti.cc/v1 --wire-api responses --requires-openai-auth
```

### 只修历史，不改 config.toml

```bash
bash ./run_codex_switcher.sh --provider 9router --repair-only
```

## 9Router：Codex App 内切 GPT-5.4 / GPT-5.5

App 选模型会直接改 `config.toml` 里的裸名（`gpt-5.5`）。配合 **oa-first combo**，聊天与 `apply_patch` 均可正常工作。详见 [`9router_codex_aliases.md`](9router_codex_aliases.md)。

```bash
# 查看 ~/.9router 里 combo / alias 状态
python3 sync_9router_codex_aliases.py --list

# 写入/同步 oa-first gpt-5.x combo
python3 sync_9router_codex_aliases.py --mirror-combos --dry-run
python3 sync_9router_codex_aliases.py --mirror-combos
```

改默认链路：编辑 `sync_9router_codex_aliases.py` 里的 `DEFAULT_CODEX_COMBO_CHAINS`，再跑 `--mirror-combos`。

## 设计原则

- 不依赖 git
- 不要求项目仓库
- 先备份，再改写
- dry run 和正式执行使用同一套逻辑
- 输出 JSON 摘要，方便人看，也方便 AI 读取
