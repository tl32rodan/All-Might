# Hooks 概念介紹 + Auto-Episode Recording Proposal

## Part 1: Hooks 是什麼?

### 核心概念

Hooks 是**使用者定義的 shell 指令**, 在 Claude Code / OpenCode 的特定生命週期時間點**自動執行**。
它提供的是**確定性的自動化** — 不依賴 LLM 決定是否執行, 而是每次觸發都必定執行。

```
Human Input → [UserPromptSubmit hook] → Claude 處理
                                              ↓
                                        Claude 呼叫工具
                                              ↓
                                     [PreToolUse hook] ← 可以阻止!
                                              ↓
                                         工具執行
                                              ↓
                                     [PostToolUse hook] ← 可以注入回饋
                                              ↓
                                      Claude 回應
                                              ↓
                                       [Stop hook] ← 可以阻止停止
                                              ↓
                                      等待下次輸入
```

### 與 LLM 指令的根本差異

| | LLM 指令 (CLAUDE.md) | Hooks |
|---|---|---|
| **執行保證** | LLM 可能遺忘 | 100% 確定執行 |
| **時機** | LLM 自行判斷 | 精確的事件觸發 |
| **能力** | 文字建議 | 可阻止操作、注入 context、執行外部指令 |
| **適用場景** | 引導、偏好 | 政策強制、自動化、整合 |

---

## Part 2: 可用的 Hook 事件

### Claude Code 完整事件表

| 事件 | 觸發時機 | 頻率 | 可阻止? |
|------|---------|------|---------|
| **SessionStart** | Session 開始/恢復 | 每 session 一次 | 否 |
| **SessionEnd** | Session 結束 | 每 session 一次 | 否 |
| **UserPromptSubmit** | 使用者送出 prompt | 每次送出 | 可注入 context |
| **Stop** | Claude 完成回應 | 每回合 | 可阻止 (exit 2) |
| **PreToolUse** | 工具呼叫前 | 每次呼叫 | 可阻止 |
| **PostToolUse** | 工具呼叫後 | 每次呼叫 | 可注入回饋 |
| **Notification** | Claude 需要注意 | 不定 | 否 |
| **PreCompact** | Context 壓縮前 | 不定 | 否 |
| **PostCompact** | Context 壓縮後 | 不定 | 否 |

### OpenCode 事件 (透過 Plugin 框架)

| 事件 | 觸發時機 | 設定方式 |
|------|---------|---------|
| **session_completed** | Session 結束 | opencode.json hooks |
| **file_edited** | 檔案被修改 | opencode.json hooks |
| **Plugin events** | 各種生命週期 | @opencode-ai/plugin SDK |

---

## Part 3: 設定方式

### Claude Code — `.claude/settings.json`

```json
{
  "hooks": {
    "EventName": [
      {
        "matcher": "ToolName",
        "hooks": [
          {
            "type": "command",
            "command": "./script.sh",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

**設定檔位置 (優先順序由低到高):**

| 位置 | 範圍 | 版控? |
|------|------|------|
| `~/.claude/settings.json` | 所有專案 (全域) | 否 |
| `.claude/settings.json` | 單一專案 | 是 |
| `.claude/settings.local.json` | 單一專案 (本地) | 否 |

### OpenCode — `opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "hooks": {
    "session_completed": {
      "command": "./.opencode/hooks/finalize.sh"
    }
  }
}
```

**設定檔位置:**
- 全域: `~/.config/opencode/opencode.json`
- 專案: `./opencode.json`
- 環境變數: `OPENCODE_CONFIG`

---

## Part 4: Hook 的執行模型

### 輸入 (stdin)

每個 hook 透過 stdin 收到 JSON:

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/dir",
  "hook_event_name": "SessionEnd"
}
```

### 輸出 (exit code + stdout/stderr)

| Exit Code | 效果 |
|-----------|------|
| **0** | 成功. stdout 的文字/JSON 注入到 Claude context |
| **2** | 阻止. stderr 的訊息回饋給 Claude (解釋為什麼被阻止) |
| **其他** | 非阻止錯誤. 記入 transcript, 繼續執行 |

---

## Part 5: Auto-Episode Recording — 完整 Proposal

### 目標

在每次 Claude Code / OpenCode session 結束時, **自動建立 Episode**,
無需 agent 或 human 手動觸發。

### 架構

```
SessionStart hook
  └─ 初始化 session metadata
       ↓
  (Agent 正常工作, /memory-observe 記錄觀察)
       ↓
Stop hook (每回合)
  └─ 累積 observations 到暫存檔
       ↓
SessionEnd hook
  └─ 讀取 transcript + 暫存 observations
  └─ 產生 episode YAML
  └─ (optional) 觸發 smak ingest
```

### 實作檔案

#### 1. `.claude/hooks/memory-session-start.sh`

```bash
#!/usr/bin/env bash
# SessionStart: 初始化 session 記錄
set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))")
PROJECT_DIR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))")

# 建立暫存目錄
SCRATCH_DIR="/tmp/allmight-session-${SESSION_ID}"
mkdir -p "$SCRATCH_DIR"

# 記錄 session metadata
cat > "$SCRATCH_DIR/meta.json" << EOFMETA
{
  "session_id": "$SESSION_ID",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)",
  "project_dir": "$PROJECT_DIR",
  "observations": [],
  "files_touched": []
}
EOFMETA

# 注入 context 提醒 agent 記憶系統已啟動
echo "Memory system active. Use /memory-observe to record important observations during this session."
exit 0
```

#### 2. `.claude/hooks/memory-session-end.sh`

```bash
#!/usr/bin/env bash
# SessionEnd: 從 transcript 建立 Episode
set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id','unknown'))")
PROJECT_DIR=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','.'))")

SCRATCH_DIR="/tmp/allmight-session-${SESSION_ID}"

# 檢查是否在 All-Might workspace 中
if [ ! -f "$PROJECT_DIR/memory/config.yaml" ]; then
  exit 0  # 非 All-Might workspace, 靜默退出
fi

# 讀取 transcript 路徑
TRANSCRIPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))")

# 用 Python 建立 episode (直接呼叫 All-Might API)
python3 - "$PROJECT_DIR" "$SESSION_ID" "$TRANSCRIPT" "$SCRATCH_DIR" << 'EOFPY'
import sys, json, os
from pathlib import Path

project_dir = Path(sys.argv[1])
session_id = sys.argv[2]
transcript_path = sys.argv[3]
scratch_dir = Path(sys.argv[4])

# 確保可以 import allmight
sys.path.insert(0, str(project_dir / "src"))

try:
    from allmight.memory.episodic import EpisodicMemoryStore

    # 讀取暫存的 observations
    observations = []
    meta_path = scratch_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
            observations = meta.get("observations", [])

    # 從 transcript 萃取摘要 (簡化: 取最後幾行)
    summary = f"Session {session_id}"
    if transcript_path and os.path.exists(transcript_path):
        summary = f"Session completed (transcript: {transcript_path})"

    # 建立 episode
    store = EpisodicMemoryStore(project_dir)
    store.record_episode(
        session_id=session_id,
        summary=summary,
        observations=observations,
        outcome="completed",
    )
    print(f"Episode recorded for session {session_id}", file=sys.stderr)

except Exception as e:
    print(f"Warning: Could not record episode: {e}", file=sys.stderr)
    # 非阻止錯誤, 不影響 session 結束
EOFPY

# 清理暫存
rm -rf "$SCRATCH_DIR"
exit 0
```

### 3. Claude Code 設定 — `.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/memory-session-start.sh\""
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/memory-session-end.sh\""
          }
        ]
      }
    ]
  }
}
```

### 4. OpenCode 設定 — `opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "hooks": {
    "session_completed": {
      "command": "bash ./.claude/hooks/memory-session-end.sh"
    }
  }
}
```

### 啟用步驟

1. **確認 memory 已初始化:**
   ```bash
   allmight memory init
   ```

2. **建立 hooks 目錄和腳本:**
   ```bash
   mkdir -p .claude/hooks
   # 複製上述腳本到 .claude/hooks/
   chmod +x .claude/hooks/*.sh
   ```

3. **設定 hooks (擇一):**
   - Claude Code: 編輯 `.claude/settings.json`, 加入上述 hooks 設定
   - OpenCode: 編輯 `opencode.json`, 加入 hooks 設定

4. **驗證:**
   ```bash
   # Claude Code: 啟動後檢查
   # 開啟新 session, 工作, 結束
   # 檢查 episode 是否建立:
   ls memory/episodes/
   allmight memory status
   ```

---

## Part 6: 進階 Hook 範例

### 阻止危險操作

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/protect-memory.sh"
          }
        ]
      }
    ]
  }
}
```

`.claude/hooks/protect-memory.sh`:
```bash
#!/usr/bin/env bash
# 阻止手動編輯 memory 檔案
INPUT=$(cat)
CMD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))")

if echo "$CMD" | grep -qE '(vim|nano|cat\s*>|echo\s*>).*memory/(episodes|semantic|working)/'; then
  echo "Blocked: Do not manually edit memory files. Use /memory-* commands instead." >&2
  exit 2
fi
exit 0
```

### 合併觸發 (PostCompact hook)

Context 壓縮後自動提醒 agent 重新載入 working memory:

```json
{
  "hooks": {
    "PostCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Context was compacted. Re-read memory/working/MEMORY.md for persistent context.'"
          }
        ]
      }
    ]
  }
}
```
