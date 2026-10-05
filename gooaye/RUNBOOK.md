# 全量萃取 Runbook（給負責指揮的 session）

你是指揮者。任務：用子 agent 把《股癌》EP1–700 萃取成卡片，存進私人 repo `20737437/gooaye-data`。
**你自己不讀逐字稿、不寫卡片**，只派工、驗收、存檔、回報。主 session 的上下文要保持精簡。

## 0. 準備（每次新 session 都要做）

1. nuwa-skill 切到分支 `claude/cool-cori-lj6dn3`。
2. 用 `add_repo` 加入 `20737437/gooaye-data`（access=push），clone 到 `/home/user/gooaye-data`。
3. 安裝套件並準備輸入：
   ```bash
   pip install -q anthropic opencc-python-reimplemented rapidfuzz pyyaml jsonschema
   cd /home/user/nuwa-skill/gooaye/pipeline
   python3 s0_s1_fetch.py                         # 約 40 秒，逐字稿只存本機
   python3 s2_segment.py
   python3 s3_extract.py render --all             # EP1–675
   python3 s3_extract.py render --eps $(seq 676 700)
   mkdir -p ../data/cards/inbox
   python3 progress.py status                     # 進度存在 gooaye-data/progress.json，會從上次中斷處接續
   ```

## 1. 迴圈（重複直到全部完成或觸發停止條件）

1. `python3 progress.py next 10` 取得下一批 10 集，以及每集該用的模型（haiku / sonnet）。
2. 每集開一個背景子 agent（`subagent_type: general-purpose`、`model` 照清單、`run_in_background: true`），**10 個在同一回合一起送出**。
   - prompt 用 `gooaye/prompts/subagent.md`，替換 `{EP}`（如 42）、`{EP4}`（如 0042）、`{MODEL}`、`{OUT_DIR}`=`/home/user/nuwa-skill/gooaye/data/cards/inbox`。
3. 等 10 個完成通知（不要輪詢，也不要讀子 agent 的 transcript）。每個通知的 `<usage>` 有 `subagent_tokens`，把這批的總和追加一行到 `/home/user/gooaye-data/usage.log`（格式：`批次 集數 tokens`），之後用來換算每集成本。
4. 驗收並入庫：
   ```bash
   python3 progress.py ingest ../data/cards/inbox && rm -f ../data/cards/inbox/EP*.json
   cd /home/user/gooaye-data && git add -A && git commit -qm "cards: batch $(date +%s)" && git push -q
   ```
5. 失敗的集數（記在 progress.json 的 failed）重跑一次；再失敗就跳過，留到最後回報。

主 session 每批只保留一行紀錄，例如「批次 7：10/10 入庫，累計 70 集」。不要把卡片內容或驗證細節貼進對話。

## 2. 檢查點與停止條件

- **第一個檢查點：累計 40 集時**，停下來回報給使用者：
  - 各模型每集平均卡數、丟卡率、隱私／說話者警示數（`python3 validate_cards.py /home/user/gooaye-data/cards`）
  - 從四個時期各抽 1 集，各看 5 張卡，判斷品質（對照 `gooaye-data/reference/` 的手動標準卡）
  - 請使用者回報目前 credits 剩多少，換算每集成本，推算能不能跑完。跑不完的話提出方案：降比例、改用 haiku，或只跑偶數集
- 之後每 150 集簡短回報一次進度。
- **credits 剩不到 USD 35 時停止萃取**。剩下的額度留給後段（Opus 做主題整理、提煉、預測測試、驗證），那是品質的關鍵，不能全花在萃取。
- 上下文太長、session 變慢時：確認最後一批已 push，回報進度，請使用者開新 session 繼續（照第 0 步準備，進度會自動接上）。

## 3. 規則

- 卡片、逐字稿、驗證輸出**絕不**放進 `nuwa-skill`（公開 repo），只存 `gooaye-data`。
- 不要修改 `prompts/extract.md` 或 `schemas/card.schema.json`：目前凍結在 prompt_version v3（只做投資面）。先前用 v2 抽的集數保留不重跑，後段會只取 invest/both 卡。真的有系統性問題時，先停下來問使用者。
- 不要跳過驗證就入庫。
