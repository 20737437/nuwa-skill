#!/usr/bin/env python3
"""S6：表達 DNA 量化統計（純統計，不用 LLM），對應 extraction-framework §2.1。

全語料逐年計算：句長、疑問句比例、確定／保留語氣、中英夾雜、口語粗話、第一人稱，
以及高頻 n-gram（口頭禪候選）。業配段：有標題的集數用 S2 的 sponsor 標記排除；
沒標題的集數用關鍵字粗略排除含業配用語的段落。

輸出：data/dna_stats.json，並印出摘要表。
注意：句長受 ASR 斷句與標點影響，只看相對趨勢。
用法：python3 gooaye/pipeline/s6_dna_stats.py
"""

import collections
import json
import re

from common import DATA, SEGMENTS, load_manifest

SPONSOR_HINT = re.compile(r"贊助|優惠|折扣|點擊資訊欄|折碼|輸入代碼|限時")
CERTAIN = ["一定", "絕對", "肯定", "顯然", "百分之百", "毫無疑問", "很明顯"]
HEDGE = ["可能", "也許", "或許", "不知道", "不確定", "我猜", "應該是", "搞不好", "很難說"]
CRUDE = ["幹", "靠北", "他媽", "媽的", "屁", "三小", "智障", "白痴"]
STOP_NGRAM = re.compile(r"^(就是|然後|所以|那個|這個|我們|大家|因為|可是|其實|如果|的話|你|我|他|的|了|是|在|有|會|說|要|也|都|就|那|這)")


def clean_text(ep: int) -> str:
    seg = json.loads((SEGMENTS / f"EP{ep:04d}.json").read_text(encoding="utf-8"))
    parts = []
    for s in seg["segments"]:
        if s["type"] == "sponsor":
            continue
        for para in re.split(r"\n\s*\n", s["text"]):
            if para.lstrip().startswith((">", "#", "**")):
                continue  # 聽眾來信與標題不算他的表達
            if seg["mode"] == "needs_llm" and SPONSOR_HINT.search(para):
                continue
            parts.append(para)
    return "\n".join(parts)


def stats(text: str) -> dict:
    sents = [s for s in re.split(r"[。！？!?\n]", text) if len(s.strip()) > 1]
    n = max(len(text), 1)
    per_k = lambda words: round(sum(text.count(w) for w in words) / n * 1000, 3)
    eng = re.findall(r"[A-Za-z][A-Za-z\-]+", text)
    return {
        "chars": len(text),
        "avg_sentence_len": round(sum(len(s) for s in sents) / max(len(sents), 1), 1),
        "question_ratio": round(sum(1 for s in re.findall(r"[^。！？!?]*[？?]", text)) / max(len(sents), 1), 3),
        "certain_per_k": per_k(CERTAIN),
        "hedge_per_k": per_k(HEDGE),
        "crude_per_k": per_k(CRUDE),
        "english_words_per_k": round(len(eng) / n * 1000, 2),
        "first_person_per_k": per_k(["我"]),
    }


def main() -> None:
    m = load_manifest()
    by_year: dict[str, list[str]] = collections.defaultdict(list)
    ngrams = collections.Counter()
    eng_terms = collections.Counter()
    for ep, row in m.items():
        t = clean_text(ep)
        by_year[row["date"][:4]].append(t)
        han = re.sub(r"[^一-鿿]+", "|", t)
        for chunk in han.split("|"):
            for k in (3, 4):
                for i in range(len(chunk) - k + 1):
                    g = chunk[i:i + k]
                    if not STOP_NGRAM.match(g):
                        ngrams[g] += 1
        eng_terms.update(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", t))

    out = {"by_year": {y: stats("\n".join(ts)) for y, ts in sorted(by_year.items())}}
    out["all"] = stats("\n".join("\n".join(ts) for ts in by_year.values()))
    out["top_ngrams"] = ngrams.most_common(200)
    out["top_english"] = eng_terms.most_common(80)
    (DATA / "dna_stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    cols = ["avg_sentence_len", "question_ratio", "certain_per_k", "hedge_per_k", "crude_per_k", "english_words_per_k", "first_person_per_k"]
    print("年份  " + "  ".join(cols))
    for y, s in list(out["by_year"].items()) + [("全部", out["all"])]:
        print(f"{y:<5} " + "  ".join(str(s[c]) for c in cols))
    print("\n高頻 3–4 字片語（前 60）：")
    print("、".join(g for g, _ in out["top_ngrams"][:60]))
    print("\n高頻英文詞（前 40）：")
    print(", ".join(w for w, _ in out["top_english"][:40]))


if __name__ == "__main__":
    main()
