#!/usr/bin/env python3
"""S0 + S1：從社群存檔抓逐字稿，建立 manifest。

用法：
    python3 gooaye/pipeline/s0_s1_fetch.py            # 抓全部（遇到連續 5 個缺號停止）
    python3 gooaye/pipeline/s0_s1_fetch.py --eps 1 50 # 只抓指定集數

已存在且 sha256 未變的檔案會跳過；逐字稿只存在 gooaye/data/（已 gitignore）。
官方 RSS 比對與自跑 ASR 尚未實作（本環境網路擋住 RSS），缺號會列在報表裡。
"""

import argparse
import concurrent.futures as cf
import hashlib
import urllib.error
import urllib.request

from common import ARCHIVE_RAW, ep_path, load_manifest, parse_transcript, save_manifest

try:
    import opencc  # Whisper 常吐簡體；存檔多半已是繁體，轉一次無害
    _S2T = opencc.OpenCC("s2twp")
except ImportError:  # pragma: no cover
    _S2T = None


def fetch(ep: int) -> tuple[int, str | None]:
    try:
        with urllib.request.urlopen(ARCHIVE_RAW.format(ep=ep), timeout=60) as r:
            return ep, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ep, None
        raise


def store(ep: int, text: str, rows: dict) -> None:
    meta, body = parse_transcript(text)
    if _S2T and meta.get("source") != "whatmkreallysaid.com":
        text = _S2T.convert(text)
    path = ep_path(ep)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    rows[ep] = {
        **rows.get(ep, {}),
        "ep": ep,
        "date": meta.get("episode_date"),
        "title": meta.get("title"),
        "duration": meta.get("duration"),
        "youtube_id": meta.get("youtube_id"),
        "transcript_source": meta.get("source"),
        "transcript_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "chars": len(body),
        "acquired": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eps", type=int, nargs="*", help="指定集數；省略則全抓")
    ap.add_argument("--max-ep", type=int, default=2000)
    args = ap.parse_args()
    rows = load_manifest()

    if args.eps:
        targets = args.eps
    else:
        targets = list(range(1, args.max_ep + 1))

    missing, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        # 分批送，全抓模式下遇到連續缺號就停
        for start in range(0, len(targets), 64):
            chunk = targets[start:start + 64]
            results = sorted(pool.map(fetch, chunk))
            for ep, text in results:
                if text is None:
                    missing.append(ep)
                else:
                    store(ep, text, rows)
                    done += 1
            if not args.eps and len(missing) >= 5 and missing[-5:] == list(range(missing[-1] - 4, missing[-1] + 1)):
                break

    save_manifest(rows)
    last = max(rows) if rows else 0
    gaps = [e for e in missing if e < last]
    print(f"取得 {done} 集；manifest 共 {len(rows)} 集，最新 EP{last}")
    print(f"缺號（< 最新集）：{gaps or '無'}")


if __name__ == "__main__":
    main()
