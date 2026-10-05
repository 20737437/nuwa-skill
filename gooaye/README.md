# 股癌蒸餾管線

計畫見 [`plans/gooaye-distillation-plan.md`](../plans/gooaye-distillation-plan.md)，試跑結果見 [`reports/pilot-report.md`](reports/pilot-report.md)。

逐字稿與所有中間產物都放在 `gooaye/data/`（已 gitignore，著作權屬於節目本人，不進 repo）。

## 安裝

```bash
pip install anthropic opencc-python-reimplemented rapidfuzz pyyaml
export ANTHROPIC_API_KEY=...        # 只有 S3 的 count / submit / collect 需要
cd gooaye/pipeline
```

## 執行順序

| 步驟 | 指令 | 需要 API |
|---|---|---|
| S0+S1 抓逐字稿、建 manifest | `python3 s0_s1_fetch.py` | 否 |
| S2 規則分段 | `python3 s2_segment.py` | 否 |
| S3 產生輸入 | `python3 s3_extract.py render` | 否 |
| S3 實測 token 與成本 | `python3 s3_extract.py count --model claude-opus-5-5` | 是 |
| S3 送出試跑（三個模型各一批） | `python3 s3_extract.py submit` | 是 |
| S3 收結果 | `python3 s3_extract.py collect <batch_id>` | 是 |
| 引文驗證與品質報表 | `python3 validate_cards.py ../data/cards/<model> [--write]` | 否 |
| S6 表達 DNA 統計 | `python3 s6_dna_stats.py` | 否 |

`s3_extract.py` 預設處理 `config.yaml` 的 20 集試跑樣本；`--all` 處理全部（自動排除 holdout 區間），`--eps` 指定集數。
