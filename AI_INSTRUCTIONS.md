# AI Instructions For Codex Switcher

如果用户提到下面这些现象，优先使用本工具：

- 切换 Codex provider 后历史对话消失
- 切换 provider 后所有会话时间都显示成「刚刚 / 1 分钟前」
- 想从 `ekti` 切到 `9router`（或反向）
- 想保留历史聊天，同时切换 API/provider
- 想一键修复 `.codex` 下的 provider 元数据
- Codex App 里切 `gpt-5.4` / `gpt-5.5` 报 404 或路由不对

## 9Router 模型名对齐（Codex App 内切模型）

完整说明见 [`9router_codex_aliases.md`](9router_codex_aliases.md)。

### 何时用

- 新装 / 重装 9Router 后，Codex 裸名 404
- App 内切 GPT-5.5 / GPT-5.4 报 `No active credentials for provider: openai`
- 需要把 Dashboard 里的 oa-first combo 同步进 SQLite

### 标准工作流

1. `python3 sync_9router_codex_aliases.py --list` — 确认 `gpt-5.x` combo 为 oa-first。
2. `python3 sync_9router_codex_aliases.py --mirror-combos --dry-run` — 预览写入的链路。
3. `python3 sync_9router_codex_aliases.py --mirror-combos` — 写入 `~/.9router/db/data.sqlite`。
4. 可选验证：`curl -X POST http://127.0.0.1:20128/v1/responses -d '{"model":"gpt-5.5","input":"hi","max_output_tokens":5}'`
5. Codex App 内切模型并试 `apply_patch` 改文件。

### 方案选择

- **推荐 `--mirror-combos`（默认 oa-first）：** 裸名 → combo；Codex 聊天 + `apply_patch` 均可用。
- **勿用 `--mirror-combos --from-cc-combos` 给 Codex 主模型：** Claude 首跳会破坏 `apply_patch`。
- **备选 `--fix-aliases`：** 裸名 → ekti 单跳，无 combo fallback。
- **备选 ekti 直连：** 见下方 ekti 命令；需有效 API key。

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
   - `rollout_mtime_restored`
   - `sqlite_updated`
   - `sqlite_timestamps_updated`
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
- 不要对 Codex 主模型跑 `--mirror-combos --from-cc-combos`

## 9router 推荐命令（默认）

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider 9router -Model gpt-5.5 -BaseUrl http://127.0.0.1:20128/v1 -WireApi responses -SubagentModel cc-normal
```

```bash
bash ./run_codex_switcher.sh --provider 9router --model gpt-5.5 --base-url http://127.0.0.1:20128/v1 --wire-api responses --subagent-model cc-normal
```

只修历史、不改 config：

```bash
bash ./run_codex_switcher.sh --provider 9router --repair-only
```

## ekti 推荐命令（直连备选）

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -Provider ekti -Model gpt-5.5 -ReasoningEffort xhigh -DisableResponseStorage -BaseUrl https://chat.ekti.cc/v1 -WireApi responses -RequiresOpenAIAuth
```

```bash
bash ./run_codex_switcher.sh --provider ekti --model gpt-5.5 --reasoning-effort xhigh --disable-response-storage --base-url https://chat.ekti.cc/v1 --wire-api responses --requires-openai-auth
```

## 会话时间被刷成「刚刚」时

根因通常是改写 rollout 时把文件 `mtime` 刷成了当前时间。修复逻辑对齐 [cockpit-tools](https://github.com/jlcodes99/cockpit-tools)：

1. 优先用 `session_index.jsonl` 的 `updated_at`
2. 否则用 rollout 事件行里的最大 `timestamp`
3. 同步修正 `state_5.sqlite` 的 `updated_at` / `updated_at_ms`

只修时间、不切 provider：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_codex_switcher.ps1 -RepairSessionTimesOnly
```

```bash
bash ./run_codex_switcher.sh --repair-session-times-only
```
