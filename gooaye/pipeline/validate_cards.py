#!/usr/bin/env python3
"""引文驗證 + 卡片品質報表。不需要 API。

每張卡的 quote 正規化後必須出現在逐字稿裡（完全子字串），
或 rapidfuzz partial_ratio ≥ 門檻（容許標點／斷句差異）。不通過的卡移到 rejected。

用法：python3 gooaye/pipeline/validate_cards.py <cards 目錄> [--write]
    --write  把 cards 改寫成只留通過的卡，並附 rejected 清單
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from common import DATA, ROOT, normalize_for_match

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
THRESH = CONFIG["validate"]["fuzzy_threshold"]
# 隱私警示：命中只標記、不自動丟卡，交給人工抽查
PRIVACY = re.compile(r"腎|病房|囊腫|確診|癌症|診斷|住院|開刀|手術|病名|學校|住址|地址|身分證|小名|取名|老婆的|太太的|兒子的|女兒的")
MAX_DROP = CONFIG["validate"]["max_drop_rate"]


def warnings(card: dict, paragraphs: dict[int, str]) -> list[str]:
    out = []
    if PRIVACY.search(card["claim"] + card["quote"]):
        out.append("privacy")
    # 引文落在聽眾來信（以 > 開頭的引用行）卻標成本人觀點
    para = paragraphs.get(card["paragraph"], "")
    q = normalize_for_match(card["quote"])
    listener_lines = [l for l in para.splitlines() if l.lstrip().startswith(">")]
    if card["speaker"] == "self" and any(q in normalize_for_match(l) for l in listener_lines):
        out.append("speaker")
    return out


def check(card: dict, paragraphs: dict[int, str], full: str) -> tuple[bool, str]:
    q = normalize_for_match(card["quote"])
    if len(q) < 6:
        return False, "too_short"
    para = normalize_for_match(paragraphs.get(card["paragraph"], ""))
    if q in para:
        return True, "exact_para"
    if q in full:
        return True, "exact_elsewhere"  # 段落編號標錯，但原文存在
    score = fuzz.partial_ratio(q, para) if para else 0
    if score >= THRESH:
        return True, "fuzzy"
    return False, f"not_found({score:.0f})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards_dir", type=Path)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    totals = collections.Counter()
    warned = collections.Counter()
    flagged = []
    kinds, lenses, tones = collections.Counter(), collections.Counter(), collections.Counter()
    per_ep = []
    for f in sorted(args.cards_dir.glob("EP*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        rendered = json.loads((DATA / "rendered" / f.name).read_text(encoding="utf-8"))
        paragraphs = {p["p"]: p["text"] for p in rendered["paragraphs"]}
        full = normalize_for_match("".join(paragraphs.values()))
        kept, rejected = [], []
        for c in data["cards"]:
            ok, why = check(c, paragraphs, full)
            totals[why] += 1
            (kept if ok else rejected).append({**c, "_check": why})
        for c in kept:
            for w in warnings(c, paragraphs):
                warned[w] += 1
                flagged.append((data.get("ep"), w, c["claim"]))
            kinds[c["kind"]] += 1
            lenses[c["lens"]] += 1
            tones[c["tone"]] += 1
        n = len(data["cards"])
        drop = len(rejected) / n if n else 0
        per_ep.append((data.get("ep"), n, len(rejected), drop, len(data.get("segments", []))))
        if args.write:
            data["cards"], data["rejected"] = kept, rejected
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    n_all = sum(r[1] for r in per_ep)
    n_rej = sum(r[2] for r in per_ep)
    print(f"{args.cards_dir}：{len(per_ep)} 集、{n_all} 張卡、引文不通過 {n_rej}（{n_rej / max(n_all, 1):.1%}）")
    print("  判定：", dict(totals))
    print("  種類：", dict(kinds.most_common()))
    print("  lens：", dict(lenses), " tone：", dict(tones))
    print("  警示（需人工看）：", dict(warned) or "無")
    for ep, w, claim in flagged:
        print(f"    EP{ep} [{w}] {claim[:60]}")
    for ep, n, rej, drop, nseg in per_ep:
        flag = "  ⚠️ 需重跑" if drop > MAX_DROP else ""
        print(f"  EP{ep}: {n} 張、丟 {rej}（{drop:.0%}）、模型分段 {nseg}{flag}")
    if any(r[3] > MAX_DROP for r in per_ep):
        sys.exit(1)


if __name__ == "__main__":
    main()
