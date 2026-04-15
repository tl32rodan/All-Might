# All-Might Workflow — Human & Agent 責任分工

## 全局流程圖

```
                         Human                              Agent
                        ────────                           ────────
Phase 0: Bootstrap
  ├─ allmight init [--with-memory]  ──────>
  ├─ (optional) allmight memory init ────>
  └─ /ingest                       ──────>

Phase 1: Knowledge Discovery
  │                                        ├─ /search "query"
  │                                        ├─ /explain "uid"
  │                                        └─ 閱讀原始碼, 理解架構

Phase 2: Enrichment (Knowledge Graph)
  │                                        ├─ /enrich --file --symbol --intent
  │                                        ├─ /enrich --relation --bidirectional
  │                                        └─ enrichment-protocol skill 引導

Phase 3: Memory Recording (per session)
  │                                        ├─ [auto] SessionStart hook 初始化
  │                                        ├─ /memory-observe "觀察"
  │  ├─ 手動修正: /memory-update           │
  │  │  user_model "偏好/修正"             │
  │  └─ 手動提示 agent 記住某事            ├─ /memory-recall "query"
  │                                        └─ [auto] SessionEnd hook 儲存 episode

Phase 4: Memory Consolidation
  │  ├─ 手動觸發: /memory-consolidate      ├─ [auto] 偵測重複 pattern
  │  └─ 審核 conflict resolution           ├─ episodic → semantic 合併
  │                                        └─ supersede 過時事實

Phase 5: Knowledge Maintenance
  │  ├─ /power-level                       ├─ /regenerate (更新 SKILL.md)
  │  ├─ /memory-status                     ├─ /graph-report
  │  └─ /panorama                          └─ self-improving (hub audit)

Phase 6: Garbage Collection
  │  ├─ allmight memory gc                  ├─ Decay 自動淘汰低價值記憶
  │  └─ 審核 dormant entries               └─ working memory 超預算時 evict
```

---

## 詳細責任對照表

### Human 的責任

| 時機 | 動作 | 說明 |
|------|------|------|
| **專案初始化** | `allmight init [--with-memory]` | 一次性操作, 建立 workspace |
| **首次 ingest** | `/ingest` | 建立語料庫搜尋索引 |
| **記憶初始化** | `allmight memory init` | 若未用 `--with-memory` flag |
| **修正 agent** | `/memory-update user_model "..."` | 當 agent 記錄不準確時手動修正 |
| **設定偏好** | `/memory-update user_model "偏好簡潔回答"` | 影響所有後續 session |
| **環境事實** | `/memory-update environment "Node 18+, pnpm"` | 持久化環境資訊 |
| **觸發合併** | `/memory-consolidate` | 週期性 (建議每週) 或大量工作後 |
| **審核健康** | `/power-level`, `/memory-status` | 了解知識圖譜 + 記憶系統狀態 |
| **垃圾回收** | `allmight memory gc` | 清理衰減的記憶 |
| **衝突仲裁** | 審核 agent 提出的 conflict | 當新舊事實矛盾, agent 無法自動判斷 |
| **Hooks 設定** | 編輯 `.claude/settings.json` | 啟用自動 episode 錄製 |

### Agent 的責任

| 時機 | 動作 | 說明 |
|------|------|------|
| **每次 session 開始** | 讀取 `MEMORY.md` | 自動載入 (working memory) |
| **閱讀程式碼時** | `/enrich` (若缺少 intent) | enrichment-protocol 引導 |
| **發現關係時** | `/enrich --relation` | 建立 symbol 間的連結 |
| **觀察到 pattern** | `/memory-observe "..."` | 記錄到當前 session buffer |
| **Human 修正時** | `/memory-observe "User 修正: X→Y"` | 立即記錄修正 |
| **需要歷史時** | `/memory-recall "query"` | 搜尋過去的 session 記錄 |
| **Session 結束** | 建立 Episode (via hook 或手動) | 摘要本次 session |
| **合併時** | 萃取 observations → semantic facts | 偵測重複, 衝突, 增強 |
| **檢測 conflict** | 向 human 報告 | 矛盾的事實交由 human 仲裁 |
| **維護時** | `/regenerate` 更新 SKILL.md | 讓技能反映最新知識 |

---

## Session 生命週期 (Memory 視角)

```
┌─────────── Session Start ───────────┐
│                                      │
│  1. SessionStart hook fires          │ ← Hooks 自動
│  2. MEMORY.md 載入 context           │ ← 自動 (working memory)
│  3. one-for-all SKILL.md 載入       │ ← 自動 (知識圖譜)
│  4. enrichment-protocol 載入         │ ← 自動
│                                      │
├─────────── Active Work ─────────────┤
│                                      │
│  Agent 工作:                         │
│  ├─ 搜尋 → /search, /memory-recall  │
│  ├─ 理解 → /explain                 │
│  ├─ 記錄 → /memory-observe          │ ← Agent 主動
│  ├─ 豐富 → /enrich                  │ ← Agent 主動
│  └─ Human 修正 → /memory-update      │ ← Human 主動
│                                      │
├─────────── Session End ─────────────┤
│                                      │
│  1. Agent 或 Hook 觸發 episode 建立  │
│     - summary: 本次 session 摘要     │
│     - observations: 所有 /observe    │
│     - key_decisions: 重要決定        │
│     - files_touched: 修改的檔案      │
│  2. Episode 寫入 memory/episodes/    │ ← 自動
│  3. /ingest (if configured)           │ ← Hook 可觸發
│  4. SessionEnd hook 清理             │ ← Hooks 自動
│                                      │
└──────────────────────────────────────┘
```

---

## Memory 更新時機速查

| 何時 | 誰 | 做什麼 | 更新哪層 |
|------|-----|--------|---------|
| Session 開始 | 系統 | 載入 MEMORY.md | Working (讀) |
| 使用中, 發現 pattern | Agent | `/memory-observe` | Episodic (buffer) |
| 使用中, Human 修正 | Human | `/memory-update user_model` | Working (寫) |
| 使用中, 需要回憶 | Agent | `/memory-recall` | Episodic + Semantic (讀) |
| Session 結束 | Hook/Agent | 建立 Episode | Episodic (寫) |
| 週期性 | Human 觸發 | `/memory-consolidate` | Semantic (寫) |
| 衝突偵測 | Agent 報告 | Human 仲裁 | Semantic (supersede) |
| 維護 | Human | `allmight memory gc` | Semantic (清理) |
