# 9Router × Codex App 模型名对齐

Codex App 里选模型会直接改 `~/.codex/config.toml` 的 `model = "..."`，写的是 **Codex 内置裸名**（如 `gpt-5.4`、`gpt-5.5`），不是 9Router Dashboard model picker 里的 `oa-gpt-5.5`。

要让 App 内切换模型可用，9Router 必须能正确解析这些裸名。

本仓库提供 `sync_9router_codex_aliases.py` 做一键配置；`codex_switcher.py` 只管 provider 切换与历史聊天可见性，不管 9Router 路由。

---

## 背景：为什么 App 切模型会 404

### Codex App 做了什么

在 App 里选「GPT-5.5」时：

1. 写入 `~/.codex/config.toml`：`model = "gpt-5.5"`
2. 请求发到 9Router：`POST /v1/responses`，body 里 `model: "gpt-5.5"`

App **不会**写 `oa/gpt-5.5` 或 `cc-pro`。

### 9Router 怎么解析裸名

收到无 `/` 的 model 字符串时，9Router 按以下顺序处理：

```
1. combos 表：有没有名叫 gpt-5.5 的 combo？
      ↓ 有 → 走 combo fallback 链（推荐）
2. modelAliases：gpt-5.5 → provider/model 单跳
      ↓ 有 → 走 alias 目标
3. 推断 provider：gpt-* → openai
      ↓ 无凭证 → 404
```

常见失败原因：

| 现象 | 原因 |
|------|------|
| `No active credentials for provider: openai` | 裸名 `gpt-5.5` 落到 alias `openai/gpt-5.5` 或默认 openai，未指向 ekti |
| Dashboard 显示 `oa-gpt-5.5` 但 App 写 `gpt-5.5` | 导入模型时短名 `gpt-5.5` 已被占用，自动加了 `oa-` 前缀 |
| `cc-pro` 能用但 App 选 GPT-5.5 不行 | combo 名是 `cc-pro`，Codex catalog 发的是 `gpt-5.5` |

### Endpoint 页 vs Model picker 显示不一致

同一模型在两个 UI 读不同字段：

| 界面 | 显示字段 | 例子 |
|------|----------|------|
| Endpoint「可用模型」 | model id | `gpt-5.5` |
| CLI/Codex model picker | alias 快捷键 key | `oa-gpt-5.5` |

灰色小字 `oa/gpt-5.5` 才是对外 API 路径；alias key 是 9Router 内部 shortcut。

---

## 方案对比

| | Combo 镜像 `--mirror-combos` | Endpoint alias `--fix-aliases` | Dashboard Console |
|--|------------------------------|--------------------------------|-------------------|
| **机制** | 新建 `gpt-5.x` combo，复制 `cc-*` 链路 | 写 `modelAliases` KV | `PUT /api/models/alias` |
| **Fallback** | ✅ 完整 combo 链 | ❌ 单跳 ekti | ❌ 单跳 |
| **Codex App 裸名** | ✅ | ✅ | ✅ |
| **自动化** | ✅ CLI 脚本 | ✅ CLI 脚本 | 手动 |
| **改 cc-pro 后同步** | 再跑 `--mirror-combos` | 无关 | 手动 |

**推荐：** 已有 `cc-pro` / `cc-normal` / `cc-lite` combo 时，用 **Combo 镜像**。

---

## 默认镜像关系

脚本 `DEFAULT_COMBO_MIRROR`（可在 `sync_9router_codex_aliases.py` 里改）：

| Codex App 裸名 | 复制自 combo | 典型链路 |
|---------------|--------------|----------|
| `gpt-5.5` | `cc-pro` | `cc/claude-opus-4-7` → `oa/gpt-5.5` → `ds/deepseek-v4-pro` |
| `gpt-5.4` | `cc-normal` | `cc/claude-sonnet-4-6` → `oa/gpt-5.4` → `ds/deepseek-v4-flash` |
| `gpt-5.4-mini` | `cc-lite` | `cc/claude-haiku-4-5` → `oa/gpt-5.4-mini` → `cx/gpt-5.4-mini` → `ds/deepseek-v4-flash` |

说明：`cc-normal` 是 sonnet 档；`cc-lite` 是 haiku/mini 档，不要和名字上的 "lite" 混淆。

---

## CLI 完整用法

### 前置条件

- 9Router 在运行或已停止均可（脚本直接写 SQLite）
- 默认数据库：`~/.9router/db/data.sqlite`
- 已存在源 combo：`cc-pro`、`cc-normal`（及可选 `cc-lite`）
- ekti compatible endpoint 已导入模型（alias 方案需要）

### 命令

```bash
cd /path/to/codex-switcher

# 查看当前 combo + gpt 相关 alias
python3 sync_9router_codex_aliases.py --list

# 预览 combo 镜像（不写盘）
python3 sync_9router_codex_aliases.py --mirror-combos --dry-run

# 写入 combo 镜像（创建或更新 gpt-5.x combo）
python3 sync_9router_codex_aliases.py --mirror-combos

# 仅修 ekti 单跳 alias（无 combo fallback）
python3 sync_9router_codex_aliases.py --fix-aliases --dry-run
python3 sync_9router_codex_aliases.py --fix-aliases

# 自定义 DB 路径
python3 sync_9router_codex_aliases.py --db ~/.9router/db/data.sqlite --list
```

### 输出 JSON 字段

| 字段 | 含义 |
|------|------|
| `combo_mirror[].action` | `created` / `updated` / `unchanged` / `skipped` / `would_*` |
| `combo_mirror[].models` | 写入的目标 combo 模型链 |
| `alias_fix[].target` | `openai-compatible-chat-<uuid>/gpt-5.5` 形式 |
| `state.ekti_prefix` | 检测到的 ekti storage provider id |

`skipped` 通常表示源 combo 不存在，需先在 9Router Dashboard 建好 `cc-pro` 等。

---

## 脚本内部做了什么

不调用 9Router HTTP API（Dashboard API 需登录）。直接读写 SQLite：

### `--mirror-combos`

1. `SELECT * FROM combos WHERE name = 'cc-pro'`（等）
2. 读取 `models` JSON 数组
3. `INSERT` 或 `UPDATE` `combos` 表，名称为 `gpt-5.5` 等

Combo 与 alias **同名不冲突**（不同表）。请求时 **combo 优先于 alias**，因此即使 KV 里仍有旧的 `gpt-5.5 → openai/...`，combo 镜像后也会走 combo 链。

### `--fix-aliases`

1. 从 `kv`（`scope=modelAliases`）或 `providerNodes` 检测 `openai-compatible-chat-*` 前缀
2. `UPSERT` alias：`gpt-5.5` → `{prefix}/gpt-5.5`

### 改 cc-pro 链路之后

在 Dashboard 调整了 `cc-pro` 的模型顺序或成员后，再执行：

```bash
python3 sync_9router_codex_aliases.py --mirror-combos
```

会把最新 `cc-pro` 链同步到 `gpt-5.5` combo（`updated`）。

---

## 验证

### 1. CLI 看状态

```bash
python3 sync_9router_codex_aliases.py --list
```

应看到 `combos.gpt-5.5` 与 `combos.cc-pro` 的 `models` 数组相同。

### 2. 打 9Router API

```bash
curl -sS -X POST http://127.0.0.1:20128/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-5.5","input":"say ok","max_output_tokens":5}' \
  | head -c 200
```

期望 HTTP 200，而非 `No active credentials for provider: openai`。

### 3. Codex App

1. `model_provider = "9router"`，`base_url = "http://127.0.0.1:20128/v1"`
2. App 内切到 GPT-5.5
3. 发一条消息，应正常回复

---

## 方案 2 细节：Dashboard Console 改 alias

适合不想建 combo、只要 ekti 单跳的场景。

1. 打开 9Router Dashboard（已登录）
2. F12 → Console
3. 从 ekti endpoint「可用模型」复制灰色路径中的 storage id

```javascript
await fetch("/api/models/alias", {
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    alias: "gpt-5.5",
    model: "openai-compatible-chat-<uuid>/gpt-5.5"
  })
}).then(r => r.json()).then(console.log)
```

alias 只能指向 `provider/model` 字符串，**不能**指向 combo 名。

---

## 推荐 Codex config

Combo 镜像完成后：

```toml
model = "gpt-5.4"          # 或在 App 里切到 gpt-5.5
model_provider = "9router"

["model_providers.9router"]
name = "9Router"
base_url = "http://127.0.0.1:20128/v1"
wire_api = "responses"

[agents.subagent]
model = "cc-normal"        # subagent 策略，可与主模型不同
```

手动写 combo 名（App 显示「自定义」，路由相同）：

```toml
model = "cc-pro"
```

---

## 与 codex-switcher 的分工

| 工具 | 作用 | 典型命令 |
|------|------|----------|
| `codex_switcher.py` | 切 provider；修 rollout / sqlite 历史可见性 | `--provider 9router --repair-only` |
| `sync_9router_codex_aliases.py` | 9Router 侧裸名 → combo / alias | `--mirror-combos` |

切换 provider 后聊天消失 → 用 switcher。  
App 内切 GPT-5.5 404 → 用本文 / sync 脚本。

---

## 故障排查

| 症状 | 检查 | 处理 |
|------|------|------|
| `--mirror-combos` 全部 skipped | `--list` 是否有 `cc-pro` | Dashboard 先建源 combo |
| 仍 404 openai | `--list` 是否有 `combos.gpt-5.5` | 重跑 `--mirror-combos`；确认 9Router 读同一 DB |
| App 显示自定义但能用 | model 是 `cc-pro` 等 | 正常；要显示 GPT-5.5 用裸名 + combo 镜像 |
| 改了 cc-pro 但 gpt-5.5 未变 | 未再 sync | `--mirror-combos` |
| `--fix-aliases` 报错 no prefix | 未导入 ekti 模型 | Dashboard 先 Add/Import 模型 |

---

## 自定义映射

编辑 `sync_9router_codex_aliases.py`：

```python
DEFAULT_COMBO_MIRROR = {
    "gpt-5.5": "cc-pro",
    "gpt-5.4": "cc-normal",
    "gpt-5.4-mini": "cc-lite",
}

DEFAULT_ALIAS_MODELS = {
    "gpt-5.3-codex": "gpt-5.3-codex",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.5": "gpt-5.5",
}
```

然后 `--dry-run` → 正式执行。
