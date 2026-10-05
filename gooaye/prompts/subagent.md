你負責從《股癌》一集逐字稿萃取卡片。只做這一件事。

1. 讀規則：`cat /home/user/nuwa-skill/gooaye/prompts/extract.md`
2. 讀逐字稿：`python3 -c "import json;print(json.load(open('/home/user/nuwa-skill/gooaye/data/rendered/EP{EP4}.json'))['text'])"`
   （輸出很長時分段讀完，一定要讀完整集再下筆）
3. 依規則產出 JSON，"model" 填 "{MODEL}"，用 Write 工具寫到 `{OUT_DIR}/EP{EP4}.json`
4. 自我檢查：`cd /home/user/nuwa-skill/gooaye/pipeline && python3 validate_cards.py {OUT_DIR} 2>&1 | grep -E "EP{EP}:|格式錯誤" `
   若該集引文不通過率 > 5% 或有格式錯誤，修正那幾張卡（引文要逐字從原文複製）後覆寫檔案，最多修一次。
5. 最後只回一行：`EP{EP} 完成，N 張卡`。不要把卡片內容貼回來。
