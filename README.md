# learn-langchain

以 **`resume.md` 為知識庫**的履歷問答示例：將履歷切分並向量化存入 Chroma，透過 LangChain 與 Google Gemini（嵌入 + 生成）做 RAG（Retrieval-Augmented Generation）。可從 CLI、HTTP API 或使用內建的 React 前端操作。

---

## 需求環境

- Python 3.10+（建議）
- Node.js（僅開發／執行 `frontend/` 時需要）
- [Google AI Studio](https://aistudio.google.com/)（或相容管道）取得的 **Gemini API 金鑰**

---

## 安裝

在專案根目錄：

```bash
pip install -r requirements.txt
```

建立 `.env`，至少設定 Gemini 可用的金鑰（擇一）：

```env
GOOGLE_API_KEY=你的金鑰
```

程式也會自動把 `GEMINI_API_KEY`、`VITE_GEMINI_API_KEY` 對應到 `GOOGLE_API_KEY`。

可選環境變數：

| 變數 | 說明 |
|------|------|
| `RESUME_EMPLOYER_OVERRIDE` | 覆寫顯示的雇主資訊 |
| `RESUME_JOB_TITLE_OVERRIDE` | 覆寫顯示的職稱 |

履歷內容放在專案根目錄 **`resume.md`**。向量索引會持久化到 **`.chroma/resume/`**（已列於 `.gitignore`）。

---

## 用法

### 命令列

```bash
python learn-langchain.py "根據這份履歷，你最擅長的技術是什麼？"
```

或：

```bash
python -m learn_langchain "你的問題"
```

未提供問題時會印出用法並以非零狀態結束。

### HTTP API（FastAPI）

```bash
uvicorn learn_langchain.api_app:app --reload --host 127.0.0.1 --port 8000
```

| 方法與路徑 | 說明 |
|------------|------|
| `GET /health` 或 `GET /api/health` | 健康檢查；若建鏈失敗會回傳 `degraded` 與錯誤訊息 |
| `POST /api/ask` | Body：`{"question": "..."}`，回傳：`{"answer": "..."}` |

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
| `learn_langchain/` | 套件：設定、載入器、切分、RAG 鏈、API |
| `learn_langchain/chains/resume_rag.py` | 履歷 RAG 鏈組裝 |
| `frontend/` | React 問答介面 |
| `learn-langchain.py` | 與 `python -m learn_langchain` 等價的快捷入口 |

預設模型名稱等常數見 `learn_langchain/config.py`（嵌入與 LLM 透過 `langchain-google-genai` 呼叫）。

---

## 疑難排解

- **503 / 健康檢查 `ready: false`**：檢查 `.env` 金鑰、網路，以及 `resume.md` 是否存在且可讀。
- **前端「無法連線至後端」**：確認 `uvicorn` 已在本機 `8000` 埠執行。

---

## 授權與注意事項

本倉庫為學習用途示例。請勿將 API 金鑰提交至版本庫；生產環境請妥善控管 CORS、驗證與流量限制。
