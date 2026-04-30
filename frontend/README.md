# jing-agent 前端

以 **Vite 8 + React 19 + TypeScript** 建置的網頁介面：與後端 **FastAPI**（`memoir_rag.api_app`）搭配，提供履歷／知識庫 RAG 問答（串流 SSE）與選用的 Google 行事曆建立流程。

完整環境變數、API 說明與疑難排解請見倉庫根目錄的 [README.md](../README.md)。

---

## 需求

- Node.js（建議與目前維護的 LTS 相容版本）
- 本機已啟動後端（預設 `http://127.0.0.1:8000`）

---

## 安裝與開發

```bash
cd frontend
npm install
npm run dev
```

開發伺服器預設會把 **`/api` 請求 proxy 到 `http://127.0.0.1:8000`**（見 `vite.config.ts`），因此瀏覽器只需開 Vite 埠（常見為 `http://localhost:5173`），無需在瀏覽器端設定 CORS 或 API base URL。

| 指令 | 說明 |
|------|------|
| `npm run dev` | 啟動開發伺服器（含 HMR） |
| `npm run build` | TypeScript 檢查後產出 production 靜態檔 |
| `npm run preview` | 預覽 build 結果 |
| `npm run lint` | 執行 ESLint |

---

## 路由與功能（簡要）

| 路徑 | 說明 |
|------|------|
| `/` | 知識庫問答：呼叫 `POST /api/ask/stream`（若後端無串流路由會退回 `POST /api/ask`），並顯示 `/api/health` 就緒狀態 |
| `/calendar` | 行事曆：依後端 OAuth 設定建立事件等（見根目錄 README） |

主要實作目錄：`src/pages/`、`src/components/`、`src/hooks/`、`src/lib/api/`。樣式為 **Tailwind CSS v4**（`@tailwindcss/vite`），路徑別名 `@/` 對應 `src/`。

---

## 技術摘要

- **React Router** 路由、`@tanstack/react-query` 請求快取
- **`react-markdown` + `remark-gfm`** 渲染模型回答
- UI 元件風格接近 shadcn／Base UI 組合（見 `src/components/ui/`）

前端目前不依賴 `VITE_*` 環境變數；Gemini 金鑰等由後端 `.env` 載入（見根目錄 README）。
