#!/usr/bin/env python3
"""S2：規則分段。有 `##` 標題的集數直接切；沒有的標記 needs_llm，交給 S3 同一次呼叫分段。

輸出 data/segments/EPxxxx.json：
    {"ep": 600, "mode": "headings" | "needs_llm", "segments": [{seg_id, type, title, text}]}

用法：python3 gooaye/pipeline/s2_segment.py [--eps 10 45 ...]
"""

import argparse
import json
import re

from common import SEGMENTS, ep_path, load_manifest, parse_transcript, save_manifest

TYPE_RULES = [
    ("sponsor", r"贊助|業配|本集節目由"),
    ("qa", r"^Q ?& ?A|^QA|聽眾(提問|問答)"),
    ("pep_talk", r"pep ?talk|心態|心法"),
    ("market", r"盤勢|大盤|市場|崩盤|股災|總經|聯準會|Fed|利率|關稅"),
]


def classify(title: str) -> str:
    for t, pat in TYPE_RULES:
        if re.search(pat, title, re.I):
            return t
    return "topic"  # 產業 / 生活 / 其他，留給 S3 細分


def split_qa(text: str) -> list[str]:
    """Q&A 段按題切：常見格式為「第一題」「下一題」「Q1」或粗體題目列。"""
    parts = re.split(r"(?=^(?:\*\*.+\*\*|Q\d+[.:：]|第[一二三四五六七八九十]+題|下一題))", text, flags=re.M)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [text]


def segment(body: str) -> dict:
    heads = list(re.finditer(r"^#{2,3}\s+(.+)$", body, re.M))
    # 只有 Q&A 標題（或幾乎沒標題）的集數，正文其實沒切，整集交給模型分段
    qa_at = next((h.start() for h in heads if classify(h.group(1)) == "qa"), len(body))
    body_heads = [h for h in heads if h.start() < qa_at]  # Q&A 之後的小標題是聽眾名字，不算
    if len(body_heads) < 3:
        return {"mode": "needs_llm", "segments": [{"seg_id": "s0", "type": "unsegmented", "title": "", "text": body}]}
    segs = []
    if heads[0].start() > 0 and body[: heads[0].start()].strip():
        segs.append(("開場", body[: heads[0].start()]))
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        segs.append((h.group(1).strip(), body[h.end():end]))
    out = []
    in_qa = False  # Q&A 固定在節目最後；進入後其餘小標題都是聽眾來信
    for title, text in segs:
        t = "opening" if title == "開場" else classify(title)
        if t == "qa" or in_qa:
            in_qa, t = True, "qa"
        if not text.strip():
            continue
        chunks = split_qa(text) if t == "qa" else [text]
        for j, c in enumerate(chunks):
            out.append({
                "seg_id": f"s{len(out)}",
                "type": "qa_item" if t == "qa" else t,
                "title": title if len(chunks) == 1 else f"{title} #{j + 1}",
                "text": c.strip(),
            })
    return {"mode": "headings", "segments": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eps", type=int, nargs="*")
    args = ap.parse_args()
    rows = load_manifest()
    eps = args.eps or sorted(rows)
    SEGMENTS.mkdir(parents=True, exist_ok=True)
    stats = {"headings": 0, "needs_llm": 0}
    for ep in eps:
        _, body = parse_transcript(ep_path(ep).read_text(encoding="utf-8"))
        seg = {"ep": ep, **segment(body)}
        (SEGMENTS / f"EP{ep:04d}.json").write_text(json.dumps(seg, ensure_ascii=False, indent=1), encoding="utf-8")
        rows[ep]["segment_mode"] = seg["mode"]
        stats[seg["mode"]] += 1
    save_manifest(rows)
    print(f"分段完成：有標題 {stats['headings']} 集、需 LLM 分段 {stats['needs_llm']} 集")


if __name__ == "__main__":
    main()
