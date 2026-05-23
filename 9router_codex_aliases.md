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
| **机制** | 新建/更新 `gpt-5.x` combo，写入 **oa-first** 链路 | 写 `modelAliases` KV | `PUT /api/models/alias` |
| **Fallback** | ✅ 完整 combo 链 | ❌ 单跳 ekti | ❌ 单跳 |
| **Codex App 裸名** | ✅ | ✅ | ✅ |
| **Codex `apply_patch`** | ✅（oa 首跳） | ✅ | ✅ |
| **自动化** | ✅ CLI 脚本 | ✅ CLI 脚本 | 手动 |

**推荐：** Codex 主会话用 **`--mirror-combos`（默认 oa-first）**。`cc-*` combo 留给 subagent / Claude Code；**不要**对 Codex 裸名用 `--from-cc-combos`（Claude 首跳会破坏 `apply_patch`）。

当前已验证可用的 oa-first 配置见下方「默认 combo 链路」。9Router 侧对 Codex `custom_tool_call` 的翻译问题见 [9router#1371](https://github.com/decolua/9router/issues/1371)（oa-first 路径下已可用）。

---

## 默认 combo 链路

脚本 `DEFAULT_CODEX_COMBO_CHAINS`（可在 `sync_9router_codex_aliases.py` 里改）：

| Codex App 裸名 | 典型链路 |
|---------------|----------|
| `gpt-5.5` | `oa/gpt-5.5` → `ds/deepseek-v4-pro-max` |
| `gpt-5.4` | `oa/gpt-5.4` → `ds/deepseek-v4-pro` |
| `gpt-5.4-mini` | `oa/gpt-5.4-mini` → `cx/gpt-5.4-mini` → `ds/deepseek-v4-flash` |

**为什么 oa 首跳：** Codex 的 `apply_patch` 是 Responses API `custom_tool_call`。combo 第一跳若是 `cc/*`（Claude），工具回传格式不兼容。`oa/*` 首跳 + 当前 9Router 版本下，`apply_patch` 已可正常工作。

旧行为（复制 `cc-pro` 链路）仍可用 `--mirror-combos --from-cc-combos`，**仅**适合非 Codex 场景。

---

## CLI 完整用法

### 前置条件

- 9Router 在运行或已停止均可（脚本直接写 SQLite）
- 默认数据库：`~/.9router/db/data.sqlite`
- ekti / oa / ds 等 provider 已在 9Router 配好（与默认链路一致）
- ekti compatible endpoint 已导入模型（`--fix-aliases` 方案需要）

### 命令

```bash
cd /path/to/codex-switcher

# 查看当前 combo + gpt 相关 alias
python3 sync_9router_codex_aliases.py --list

# 预览 combo 镜像（不写盘）
python3 sync_9router_codex_aliases.py --mirror-combos --dry-run

# 写入 oa-first combo（Codex 默认）
python3 sync_9router_codex_aliases.py --mirror-combos

# 旧：从 cc-pro/cc-normal 复制（会破坏 Codex apply_patch）
python3 sync_9router_codex_aliases.py --mirror-combos --from-cc-combos --dry-run

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

`skipped` 通常表示目标 combo 的 model 链为空；`--from-cc-combos` 时则表示缺少 `cc-pro` 等源 combo。

---

## 脚本内部做了什么

不调用 9Router HTTP API（Dashboard API 需登录）。直接读写 SQLite：

### `--mirror-combos`

默认（oa-first）：

1. 读取 `DEFAULT_CODEX_COMBO_CHAINS`
2. `INSERT` 或 `UPDATE` `combos` 表，名称为 `gpt-5.5` 等

加 `--from-cc-combos` 时改为从 `cc-pro` / `cc-normal` / `cc-lite` 复制 `models` 数组。

Combo 与 alias **同名不冲突**（不同表）。请求时 **combo 优先于 alias**，因此即使 KV 里仍有旧的 `gpt-5.5 → openai/...`，combo 镜像后也会走 combo 链。

### `--fix-aliases`

1. 从 `kv`（`scope=modelAliases`）或 `providerNodes` 检测 `openai-compatible-chat-*` 前缀
2. `UPSERT` alias：`gpt-5.5` → `{prefix}/gpt-5.5`

### 改默认 oa-first 链路之后

编辑 `sync_9router_codex_aliases.py` 里的 `DEFAULT_CODEX_COMBO_CHAINS`，再跑 `--mirror-combos`。

若你仍用 `--from-cc-combos`，改完 `cc-pro` 等源 combo 后再 sync 即可。

---

## 验证

### 1. CLI 看状态

```bash
python3 sync_9router_codex_aliases.py --list
```

应看到 `combos.gpt-5.5` 等为 oa-first 链路（不以 `cc/` 开头）。

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
2. App 内切到 GPT-5.5（或 GPT-5.4）
3. 发一条消息，应正常回复
4. 让 agent 用 `apply_patch` 改一个小文件；rollout 里应出现 `custom_tool_call` 且 `input` 含 `*** Begin Patch`

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
model = "gpt-5.5"          # App 内可切 gpt-5.4 / gpt-5.4-mini
model_provider = "9router"

["model_providers.9router"]
name = "9Router"
base_url = "http://127.0.0.1:20128/v1"
wire_api = "responses"

[agents.subagent]
model = "cc-normal"        # subagent 走 Claude combo，与主模型分离
```

手动写 Claude combo 名（App 显示「自定义」，仅适合非裸名场景）：

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
| `--mirror-combos` 全部 skipped | `--list` 看 `DEFAULT_CODEX_COMBO_CHAINS` 是否为空 | 编辑脚本默认链路或 Dashboard 手动建 combo |
| 仍 404 openai | `--list` 是否有 `combos.gpt-5.5` | 重跑 `--mirror-combos`；确认 9Router 读同一 DB |
| `apply_patch` 空 `{}` / agent 用 heredoc | combo 是否 cc-first；rollout 是否 `toolu_*` | 跑 `--mirror-combos`（oa-first）；勿 `--from-cc-combos` |
| App 显示自定义但能用 | model 是 `cc-pro` 等 | 正常；要显示 GPT-5.5 用裸名 + oa-first combo |
| `--fix-aliases` 报错 no prefix | 未导入 ekti 模型 | Dashboard 先 Add/Import 模型 |

---

## 自定义映射

编辑 `sync_9router_codex_aliases.py`：

```python
DEFAULT_CODEX_COMBO_CHAINS = {
    "gpt-5.5": ["oa/gpt-5.5", "ds/deepseek-v4-pro-max"],
    "gpt-5.4": ["oa/gpt-5.4", "ds/deepseek-v4-pro"],
    "gpt-5.4-mini": ["oa/gpt-5.4-mini", "cx/gpt-5.4-mini", "ds/deepseek-v4-flash"],
}

DEFAULT_ALIAS_MODELS = {
    "gpt-5.3-codex": "gpt-5.3-codex",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.5": "gpt-5.5",
}
```

然后 `--dry-run` → 正式执行。
