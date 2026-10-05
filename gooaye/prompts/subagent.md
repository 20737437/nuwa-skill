你負責從《股癌》一集逐字稿萃取卡片。只做這一件事，盡量少用工具呼叫。

1. 一次讀完規則與逐字稿（同一個指令）：
   `cat /home/user/nuwa-skill/gooaye/prompts/extract.md; python3 -c "import json;print(json.load(open('/home/user/nuwa-skill/gooaye/data/rendered/EP{EP4}.json'))['text'])"`
   輸出被截斷時，用 python 切片分段讀完，一定要讀完整集再下筆。
2. 依規則產出 JSON，"model" 填 "{MODEL}"，用 Write 工具寫到 `{OUT_DIR}/EP{EP4}.json`
3. 自我檢查（只檢查這一集）：
   `cd /home/user/nuwa-skill/gooaye/pipeline && mkdir -p /tmp/chk{EP} && cp {OUT_DIR}/EP{EP4}.json /tmp/chk{EP}/ && python3 validate_cards.py /tmp/chk{EP} 2>&1 | grep -vE "^    EP"`
   若有引文不通過或格式錯誤，修正那幾張卡（引文要逐字從原文複製，欄位只能用 schema 列出的值）後覆寫，最多修一次。
4. 最後只回一行：`EP{EP} 完成，N 張卡`。不要把卡片內容貼回來。
