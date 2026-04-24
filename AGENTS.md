# yt2fb Agent Instructions

當這個 repo 收到 YouTube URL 時，目標是產生 Facebook 粉專長貼文草稿，並在人工確認後才發佈。

## 不可跳過的安全規則

- 必須先產生 `preview.md`。
- 沒有人工確認，不得發佈。
- CLI 發佈必須使用 `--confirm`。
- GitHub Actions 發佈建議使用 `facebook-publish` environment 並設定 required reviewers。

## 寫作規則

- 800–1500 字繁體中文，預設約 1500 字。
- 使用 `prompts/system.md` 的貼文風格指南。
- 每篇至少 3–5 個具體錨點。
- 禁用詞命中時，要在預覽中標示。
- 原片連結放在貼文最後：`▶ 原片：https://youtu.be/{VIDEO_ID}`。

## 技術規則

- 不用瀏覽器操作 Facebook composer。
- 不用剪貼簿。
- 不做 UI click 自動發文。
- 發佈使用 Meta Graph API。
- YouTube 連結讓 Facebook 自動生成預覽卡。
