#!/usr/bin/env python3
"""session 內萃取的進度管理。卡片與進度存在私人 data repo（config.yaml 的 data_repo）。

    python3 progress.py status            各時期完成度
    python3 progress.py next N            下一批 N 集與各自應用的模型（輸出 JSON）
    python3 progress.py ingest <dir>      驗證 <dir> 內的卡片，通過者複製進 data repo 並記錄進度

處理順序：先跑偶數集、再跑奇數集，且在四個時期之間輪流。預算中途用完時各時期進度相近，時期比較不會斷層。
EP676 之後（模型訓練截止日後的驗證區）最後才跑。
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from common import DATA, ROOT

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
REPO = Path(CONFIG["data_repo"])
CARDS_OUT = REPO / "cards"
PROGRESS = REPO / "progress.json"
HOLDOUT_FROM = CONFIG["holdout_from_ep"]
LAST_EP = max(int(l.split('"ep": ')[1].split(",")[0]) for l in (DATA / "manifest.jsonl").read_text().splitlines())  # 目前取得的最新集


def load() -> dict:
    return json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {"done": {}, "failed": {}}


def period_of(ep: int) -> str:
    if ep >= HOLDOUT_FROM:
        return "holdout_eval"
    for name, (a, b) in CONFIG["periods"].items():
        if a <= ep <= b:
            return name
    raise ValueError(ep)


def order() -> list[int]:
    """偶數集先、奇數集後；每一輪在四個時期之間輪流取，預算中途用完時各時期進度相近。"""
    out = []
    for parity in (0, 1):
        queues = [[e for e in range(a, b + 1) if e % 2 == parity] for a, b in CONFIG["periods"].values()]
        while any(queues):
            for q in queues:
                if q:
                    out.append(q.pop(0))
    return out + list(range(HOLDOUT_FROM, LAST_EP + 1))


def cmd_status() -> None:
    p = load()
    done = {int(k) for k in p["done"]}
    for name in list(CONFIG["periods"]) + ["holdout_eval"]:
        eps = [e for e in range(1, LAST_EP + 1) if period_of(e) == name]
        n = sum(1 for e in eps if e in done)
        print(f"{name:<13} {n:>4}/{len(eps):<4} 模型 {CONFIG['in_session_assignment'][name]}")
    cards = sum(v["cards"] for v in p["done"].values())
    print(f"合計 {len(done)}/{LAST_EP} 集、{cards} 張卡；失敗待重跑 {len(p['failed'])} 集")


def cmd_next(n: int) -> None:
    p = load()
    done = {int(k) for k in p["done"]}
    batch = [e for e in order() if e not in done][:n]
    print(json.dumps([{"ep": e, "model": CONFIG["in_session_assignment"][period_of(e)]} for e in batch]))


def cmd_ingest(src: Path) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from validate_cards import check, schema_errors
    from common import normalize_for_match

    p = load()
    CARDS_OUT.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("EP*.json")):
        ep = int(f.stem[2:])
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            p["failed"][str(ep)] = "json"
            print(f"EP{ep}: JSON 壞掉 → 待重跑")
            continue
        rendered = json.loads((DATA / "rendered" / f.name).read_text(encoding="utf-8"))
        paragraphs = {x["p"]: x["text"] for x in rendered["paragraphs"]}
        full = normalize_for_match("".join(paragraphs.values()))
        kept = [c for c in data.get("cards", []) if check(c, paragraphs, full)[0]]
        n = len(data.get("cards", []))
        drop = 1 - len(kept) / n if n else 1
        errs = schema_errors(data)
        if n == 0 or drop > CONFIG["validate"]["max_drop_rate"] or len(errs) > 3:
            p["failed"][str(ep)] = f"drop={drop:.0%} schema_errors={len(errs)}"
            print(f"EP{ep}: 不通過（丟卡 {drop:.0%}、格式錯 {len(errs)}）→ 待重跑")
            continue
        data["cards"] = kept
        (CARDS_OUT / f.name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        p["done"][str(ep)] = {"model": data.get("model"), "cards": len(kept), "dropped": n - len(kept), "at": int(time.time())}
        p["failed"].pop(str(ep), None)
        print(f"EP{ep}: {len(kept)} 張卡入庫（丟 {n - len(kept)}）")
    PROGRESS.write_text(json.dumps(p, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "next":
        cmd_next(int(sys.argv[2]))
    elif cmd == "ingest":
        cmd_ingest(Path(sys.argv[2]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
