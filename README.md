# jing-memoir（履歷／回憶 RAG）

以 **`backend/knowledge/*.md`（優先）或後端應用根目錄下的 `resume.md`** 為知識庫的履歷問答示例：將履歷切分並向量化存入 Chroma，透過 LangChain 與 Google Gemini（嵌入 + 生成）做 RAG（Retrieval-Augmented Generation）。可從 CLI、HTTP API 或使用內建的 React 前端操作。

---

## 需求環境

- Python 3.10+（建議）
- Node.js（僅開發／執行 `frontend/` 時需要）
- [Google AI Studio](https://aistudio.google.com/)（或相容管道）取得的 **Gemini API 金鑰**

---

## 安裝

於 `backend/` 安裝依賴（或自倉庫根：`pip install -r backend/requirements.txt`）：

```bash
cd backend
pip install -r requirements.txt
```

建立 `.env`（倉庫根目錄 **或** `backend/.env`，兩處會依序載入；已存在的變數不會被後者覆蓋），至少設定 Gemini 可用的金鑰（擇一）：

```env
GOOGLE_API_KEY=你的金鑰
```

程式也會自動把 `GEMINI_API_KEY`、`VITE_GEMINI_API_KEY` 對應到 `GOOGLE_API_KEY`。

可選環境變數：

| 變數 | 說明 |
|------|------|
| `RESUME_EMPLOYER_OVERRIDE` | 覆寫顯示的雇主資訊 |
| `RESUME_JOB_TITLE_OVERRIDE` | 覆寫顯示的職稱 |
| `MEMOIR_CORS_ORIGINS` 或 `CORS_ALLOW_ORIGINS` | 逗號分隔的瀏覽器來源（CORS）；未設定時預設為本機 Vite `http://localhost:5173`、`http://127.0.0.1:5173` |

知識庫可採**多檔 Markdown**：若 **`backend/knowledge/` 內至少有一份 `*.md`**，則載入該目錄下所有 `.md`（依路徑排序）；否則退回單檔 **`backend/resume.md`**。每份文件第一個 `---` 之前可作為「開頭摘要」加權區段。向量索引會持久化到 **`backend/.chroma/resume/`**（已列於 `.gitignore`）。

---

## 用法

### 命令列

於 `backend/`：

```bash
cd backend
python memoir_ask.py "根據這份履歷，你最擅長的技術是什麼？"
```

或：

```bash
cd backend
python -m memoir_rag "你的問題"
```

若必須從倉庫根執行而不先 `cd backend`，請設定 **`PYTHONPATH=backend`**（或同等方式）讓 Python 能找到 `memoir_rag`。

未提供問題時會印出用法並以非零狀態結束。

### HTTP API（FastAPI）

於 `backend/`：

```bash
cd backend
uvicorn memoir_rag.api_app:app --reload --host 127.0.0.1 --port 8000
```

| 方法與路徑 | 說明 |
|------------|------|
| `GET /health` 或 `GET /api/health` | 健康檢查，HTTP 通常為 **200**。Body：`status`（`ok` 或 `degraded`）、`ready`、`error`；就緒時另有 `embedding_fingerprint`、`prompt_sha256`、`llm_model`（與 OpenAPI `HealthResponse` 一致）。建鏈失敗時仍為 200，但 `status: degraded`、`ready: false` 並附 `error`。 |
| `POST /api/ask` | Body：`{"question": "..."}`，回傳：`{"answer": "..."}` |
| `POST /api/ask/stream` | 同上問題，**SSE**（`text/event-stream`）：先 `event: meta`（`embeddingFingerprint`、`promptSha256`、`llmModel`），再多次 `event: token`（`{"text": "..."}`），錯誤時 `event: error`。前端優先使用；舊後端無此路由時會改打 `/api/ask`。 |

啟動 API 後可開 **OpenAPI 介面**：`http://127.0.0.1:8000/docs`。

### 前端（Vite + React）

需先啟動上述 API（預設 `127.0.0.1:8000`），再：

```bash
cd frontend
npm install
npm run dev
```

開發伺服器會將 `/api` **proxy** 到後端，因此瀏覽器只需連到 Vite 預設埠（常見為 `http://localhost:5173`）。

---

## 專案結構（簡要）

| 路徑 | 說明 |
|------|------|
| `backend/memoir_rag/` | 套件：設定、載入器、切分、RAG 鏈、API 入口 |
| `backend/memoir_rag/chains/resume_rag.py` | 履歷 RAG 鏈組裝 |
| `backend/memoir_rag/routers/`、`schemas/` | HTTP 路由與 Pydantic schema |
| `backend/memoir_rag/middleware/` | 例如請求日誌 |
| `backend/memoir_rag/deps.py`、`state.py` | FastAPI 依賴與 lifespan 內的 RAG 狀態 |
| `backend/knowledge/` | 可選：多份 `.md` 知識來源（優於 `resume.md`） |
| `frontend/` | React 問答介面 |
| `backend/memoir_ask.py` | 與 `python -m memoir_rag` 等價的快捷入口 |

預設模型（定義於 `backend/memoir_rag/config.py`，向後端透過 `langchain-google-genai` 呼叫）：**嵌入** `EMBEDDING_MODEL=gemini-embedding-001`、**生成** `LLM_MODEL=gemini-2.5-flash-lite`。其他常數仍以該檔為準。

---

## 疑難排解

- **健康檢查為 200 但 `ready: false`、`status: degraded`**：表示應用已啟動，但 RAG 建鏈失敗；請看 body 的 `error`，並檢查 `.env` 金鑰、網路，以及 `backend/knowledge/*.md` 或 `backend/resume.md` 是否存在且可讀。
- **`POST /api/ask`、`POST /api/ask/stream` 回 503**：問答端點在 RAG **未就緒**（`RagFailedState`）時會拒絕；此時健康檢查仍通常為 **200** 並在 body 呈現 `degraded`。若為「Application state not initialized.」，表示 `app.state.rag` 尚未建立，此時 **`GET /health` 亦會 503**（與問答相同，皆走 `get_rag_state`）。其餘問答 503 的內容多為建鏈錯誤，可對照 `/api/health` 的 `error`。
- **前端「無法連線至後端」**：確認 `uvicorn` 已在本機 `8000` 埠執行。
- **送出問題出現「Not Found」**：多半是後端行程仍未 reload、或啟動的不是 `memoir_rag.api_app:app`，路由表裡沒有 `POST /api/ask/stream`。請完全停止舊的 `uvicorn` 後再執行文件中的啟動指令。可用下列指令確認（預期 **不是** `404`）：

  ```bash
  curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/ask/stream \
    -H 'Content-Type: application/json' \
    -d '{"question":"test"}'
  ```

  若為 `404`，請改啟動 `cd backend && uvicorn memoir_rag.api_app:app --reload --host 127.0.0.1 --port 8000`。開發中前端若偵測串流端點 404，會自動改叫 `POST /api/ask`（一次性 JSON，非串流）。

---

## 授權與注意事項

本倉庫為學習用途示例。請勿將 API 金鑰提交至版本庫；生產環境請妥善控管 CORS、驗證與流量限制。
