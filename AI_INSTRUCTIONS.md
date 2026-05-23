# AI Instructions For Codex Switcher

如果用户提到下面这些现象，优先使用本工具：

- 切换 Codex provider 后历史对话消失
- 想从 `9router` 切到 `ekti`
- 想保留历史聊天，同时切换 API/provider
- 想一键修复 `.codex` 下的 provider 元数据
- Codex App 里切 `gpt-5.4` / `gpt-5.5` 报 404 或路由不对

## 9Router 模型名对齐（Codex App 内切模型）

完整说明见 [`9router_codex_aliases.md`](9router_codex_aliases.md)。

### 何时用

- Codex App 切 GPT-5.5 / GPT-5.4 报 404（常见：`No active credentials for provider: openai`）
- 已有 `cc-pro` / `cc-normal` combo，希望 App 裸名走同一条 fallback 链

### 标准工作流

1. `python3 sync_9router_codex_aliases.py --list` — 确认源 combo 存在。
2. `python3 sync_9router_codex_aliases.py --mirror-combos --dry-run` — 看会 create/update 哪些 `gpt-5.x` combo。
3. `python3 sync_9router_codex_aliases.py --mirror-combos` — 写入 `~/.9router/db/data.sqlite`。
4. 可选验证：`curl -X POST http://127.0.0.1:20128/v1/responses -d '{"model":"gpt-5.5","input":"hi","max_output_tokens":5}'`
5. Codex App 内再切模型测试。

### 方案选择

- **推荐 `--mirror-combos`：** 裸名 → combo，与 `cc-pro` 等同链路。
- **备选 `--fix-aliases`：** 裸名 → ekti 单跳，无 combo fallback。
- **备选 Dashboard Console：** 同 `--fix-aliases`，手动 PUT `/api/models/alias`。

### 与 codex_switcher 分工

- `codex_switcher.py` → `model_provider`、历史 rollout/sqlite
- `sync_9router_codex_aliases.py` → 9Router 路由，不改 `~/.codex`

## 标准工作流

1. 先确认 Codex 已经完全关闭。
2. 先运行 dry run。
3. 读取 dry run JSON 输出，重点看：
   - `current_provider`
   - `target_provider`
   - `backup_dir`
   - `rollout_seen`
   - `rollout_changed`
   - `sqlite_updated`
4. 如果输出合理，再运行正式命令。
5. 正式执行后，提示用户重新打开 Codex。
6. 如果仍有历史不可见，再做只读检查：
   - `config.toml` 中 `model_provider`
   - `sessions` / `archived_sessions` 中 `rollout` 首行 provider
   - `state_5.sqlite` 中 `threads.model_provider`

## 不要做的事

- 不要只改 `config.toml` 就结束
- 不要跳过备份
- 不要在 Codex 正在运行时改写 `state_5.sqlite`
- 不要手动混用多套零散命令，优先走统一脚本

## ekti 推荐命令

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider ekti -Model gpt-5.5 -ReasoningEffort xhigh -DisableResponseStorage -BaseUrl https://chat.ekti.cc/v1 -WireApi responses -RequiresOpenAIAuth
```

## 9router 推荐命令

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider 9router -Model gpt-5.4 -BaseUrl http://127.0.0.1:20128/v1 -WireApi responses -SubagentModel oa/gpt-5.4
```

## macOS 推荐命令

```bash
bash ./run_codex_switcher.sh --provider ekti --model gpt-5.5 --reasoning-effort xhigh --disable-response-storage --base-url https://chat.ekti.cc/v1 --wire-api responses --requires-openai-auth
```

```bash
bash ./run_codex_switcher.sh --provider 9router --model gpt-5.4 --base-url http://127.0.0.1:20128/v1 --wire-api responses --subagent-model oa/gpt-5.4
```
