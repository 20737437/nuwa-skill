"""管線共用：路徑、manifest 讀寫、逐字稿解析。"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TRANSCRIPTS = DATA / "transcripts"
SEGMENTS = DATA / "segments"
CARDS = DATA / "cards"
MANIFEST = DATA / "manifest.jsonl"

ARCHIVE_RAW = "https://raw.githubusercontent.com/huijoson/gooaye-agent/main/transcripts/EP{ep:04d}.md"


def ep_path(ep: int) -> Path:
    return TRANSCRIPTS / f"EP{ep:04d}.md"


def load_manifest() -> dict[int, dict]:
    if not MANIFEST.exists():
        return {}
    rows = (json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip())
    return {r["ep"]: r for r in rows}


def save_manifest(rows: dict[int, dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8") as f:
        for ep in sorted(rows):
            f.write(json.dumps(rows[ep], ensure_ascii=False) + "\n")


def parse_transcript(text: str) -> tuple[dict, str]:
    """回傳 (frontmatter dict, 正文)。正文去掉 frontmatter 與檔頭的 metadata 區塊。"""
    meta: dict = {}
    body = text
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
        body = text[m.end():]
    # 檔頭的「# EPxx｜標題」與 metadata 清單到第一個 --- 為止
    parts = re.split(r"^---\s*$", body, maxsplit=1, flags=re.M)
    if len(parts) == 2 and parts[0].lstrip().startswith("#"):
        body = parts[1]
    return meta, body.strip()


_PUNCT = re.compile(r"[\s　，。、！？；：「」『』（）()《》〈〉…—\-~～,.!?;:'\"“”‘’\[\]【】]+")


def normalize_for_match(s: str) -> str:
    """引文比對用：去空白與標點、全形英數轉半形、轉小寫。"""
    s = "".join(chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else c for c in s)
    return _PUNCT.sub("", s).lower()
