# yt2fb

YouTube 影片轉 Facebook 粉專長貼文自動化。

這個專案的目標是把一個 YouTube 連結轉成繁體中文 Facebook 長貼文草稿，先輸出預覽，等人工確認後才發佈到 Facebook 粉專。

## 核心流程

```text
YouTube URL
  ↓
擷取影片資訊與字幕
  ↓
產生 Facebook 長貼文草稿
  ↓
輸出 preview.md 與 run.json
  ↓
人工確認
  ↓
發佈到 Facebook 粉專
```

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

然後在 `.env` 填入：

```env
OPENAI_API_KEY=你的 OpenAI API key
OPENAI_MODEL=gpt-4.1-mini
META_PAGE_ID=你的 Facebook 粉專 ID
META_PAGE_ACCESS_TOKEN=你的 Facebook 粉專 Page Access Token
META_GRAPH_VERSION=v20.0
```

## 產生草稿

```bash
python yt2fb.py draft "https://youtu.be/VIDEO_ID"
```

成功後會產生：

```text
preview.md
run.json
```

`preview.md` 會包含完整貼文、字數檢查、禁用詞檢查、具體錨點列表與原片連結。

## 發佈

發佈前請先人工檢查 `preview.md`。

確認後執行：

```bash
python yt2fb.py publish "https://youtu.be/VIDEO_ID" --confirm
```

沒有 `--confirm` 時，程式會拒絕發佈。

## GitHub Actions 使用方式

到 GitHub：

```text
Actions → yt2fb → Run workflow
```

輸入 YouTube URL。

- `mode=draft`：只產生草稿 artifact。
- `mode=publish` 且 `confirm_publish=true`：先產生草稿，再進入 `facebook-publish` environment。建議在 GitHub repo 設定該 environment 的 Required reviewers，做到人工審核後才發佈。

## GitHub Secrets

請到：

```text
Repo → Settings → Secrets and variables → Actions
```

新增：

```text
OPENAI_API_KEY
META_PAGE_ID
META_PAGE_ACCESS_TOKEN
```

可選：

```text
OPENAI_MODEL
META_GRAPH_VERSION
```

## Facebook 權限提醒

Meta Page Access Token 需要能對粉專發文。常見需要的權限包括粉專管理與內容發佈相關權限。實際權限名稱會依 Meta Graph API 版本與 App 設定而變動。

## 安全設計

這個專案刻意保留人工確認步驟：

- `draft` 只產生預覽，不發佈。
- `publish` 必須加 `--confirm`。
- GitHub Actions 的發佈 job 建議放進需要 reviewer 的 environment。
