#!/usr/bin/env python3
"""S3：每集一次請求，抽出投資 + 人生兩條線的卡片（Message Batches API）。

子命令：
    render  [--eps …]                 產生帶段落編號的輸入（data/rendered/），不需 API
    count   [--eps …] [--model M]     用 count_tokens 實測輸入 token 與預估成本
    submit  [--eps …] [--model M …]   送出 batch，batch id 記在 data/batches.jsonl
    collect <batch_id>                收結果 → data/cards/<model>/EPxxxx.json（含 usage）

--eps 省略時用 config.yaml 的 pilot_eps；--all 處理全部（排除 holdout）。
需要 ANTHROPIC_API_KEY（或 ant auth login 的設定檔）；render 不需要。
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import yaml

from common import CARDS, DATA, ROOT, SEGMENTS, load_manifest

RENDERED = DATA / "rendered"
BATCHES = DATA / "batches.jsonl"
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "schemas" / "card.schema.json").read_text(encoding="utf-8"))
SYSTEM = (ROOT / "prompts" / "extract.md").read_text(encoding="utf-8")


def render(ep: int) -> dict:
    """把分段結果轉成 [P n] 編號文字；同時存段落表供引文驗證用。"""
    seg = json.loads((SEGMENTS / f"EP{ep:04d}.json").read_text(encoding="utf-8"))
    meta = load_manifest()[ep]
    lines = [f"EP{ep}｜{meta['title']}｜{meta['date']}", ""]
    if seg["mode"] == "needs_llm":
        lines.append("（未分段：請先輸出 segments）")
    paragraphs = []
    for s in seg["segments"]:
        if s["type"] == "sponsor":
            continue  # 業配不送模型，省 token 也避免誤抽
        if seg["mode"] == "headings":
            lines += ["", f"<<{s['seg_id']}|{s['type']}|{s['title']}>>"]
        for para in re.split(r"\n\s*\n", s["text"]):
            para = para.strip()
            if not para or re.fullmatch(r"#+\s.*", para):
                continue
            paragraphs.append({"p": len(paragraphs) + 1, "seg_id": s["seg_id"], "text": para})
            lines.append(f"[P{len(paragraphs)}] {para}")
    out = {"ep": ep, "mode": seg["mode"], "text": "\n".join(lines), "paragraphs": paragraphs}
    RENDERED.mkdir(parents=True, exist_ok=True)
    (RENDERED / f"EP{ep:04d}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def params(model: str, user_text: str) -> dict:
    p = {
        "model": model,
        "max_tokens": CONFIG["extract"]["max_tokens"],
        # system 固定放前面並快取：每集只有 user 內容不同
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_text}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if not model.startswith("claude-haiku"):
        p["output_config"]["effort"] = CONFIG["extract"]["effort"]
    return p


def target_eps(args) -> list[int]:
    if args.eps:
        return args.eps
    if args.all:
        return [e for e in sorted(load_manifest()) if e < CONFIG["holdout_from_ep"]]
    return CONFIG["pilot_eps"]


def cmd_render(args) -> None:
    eps = target_eps(args)
    total = sum(len(render(ep)["text"]) for ep in eps)
    print(f"已產生 {len(eps)} 集輸入，共 {total:,} 字（data/rendered/）")


def cmd_count(args) -> None:
    import anthropic

    client = anthropic.Anthropic()
    model = args.model[0]
    price = CONFIG["pricing"][model]
    total_tokens = total_chars = 0
    for ep in target_eps(args):
        r = render(ep)
        p = params(model, r["text"])
        n = client.messages.count_tokens(
            model=model, system=p["system"], messages=p["messages"]
        ).input_tokens
        total_tokens += n
        total_chars += len(r["text"])
        print(f"EP{ep}: {len(r['text']):,} 字 → {n:,} tokens")
    print(f"\n{model}: {total_tokens:,} tokens / {total_chars:,} 字 = {total_tokens / total_chars:.2f} token/字")
    print(f"輸入成本（Batch 半價）≈ USD {total_tokens / 1e6 * price['input'] / 2:.2f}")


def cmd_submit(args) -> None:
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = anthropic.Anthropic()
    eps = target_eps(args)
    rendered = {ep: render(ep) for ep in eps}
    for model in args.model:
        reqs = [
            Request(custom_id=f"EP{ep:04d}", params=MessageCreateParamsNonStreaming(**params(model, r["text"])))
            for ep, r in rendered.items()
        ]
        batch = client.messages.batches.create(requests=reqs)
        with BATCHES.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"batch_id": batch.id, "model": model, "eps": eps, "created": time.time()}) + "\n")
        print(f"{model}: batch {batch.id}（{len(reqs)} 集）")


def cmd_collect(args) -> None:
    import anthropic

    client = anthropic.Anthropic()
    rec = next(json.loads(l) for l in BATCHES.read_text(encoding="utf-8").splitlines() if args.batch_id in l)
    batch = client.messages.batches.retrieve(args.batch_id)
    if batch.processing_status != "ended":
        sys.exit(f"尚未完成：{batch.processing_status}，處理中 {batch.request_counts.processing}")
    out_dir = CARDS / rec["model"]
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = bad = 0
    for res in client.messages.batches.results(args.batch_id):
        if res.result.type != "succeeded":
            print(f"[{res.custom_id}] {res.result.type}")
            bad += 1
            continue
        msg = res.result.message
        if msg.stop_reason in ("refusal", "max_tokens"):
            print(f"[{res.custom_id}] stop_reason={msg.stop_reason}")
            bad += 1
            continue
        text = next(b.text for b in msg.content if b.type == "text")
        data = json.loads(text)
        data["ep"] = int(res.custom_id[2:])
        data["model"] = rec["model"]
        data["usage"] = msg.usage.model_dump()
        (out_dir / f"{res.custom_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        ok += 1
    print(f"{rec['model']}: 成功 {ok}、失敗 {bad} → {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "count", "submit"):
        sp = sub.add_parser(name)
        sp.add_argument("--eps", type=int, nargs="*")
        sp.add_argument("--all", action="store_true")
        sp.add_argument("--model", nargs="+", default=CONFIG["extract"]["models"])
    sp = sub.add_parser("collect")
    sp.add_argument("batch_id")
    args = ap.parse_args()
    {"render": cmd_render, "count": cmd_count, "submit": cmd_submit, "collect": cmd_collect}[args.cmd](args)


if __name__ == "__main__":
    main()
