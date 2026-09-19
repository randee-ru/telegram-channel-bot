#!/usr/bin/env python3
"""Fetch vc.ru timeline and score items against topic keywords."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = "https://api.vc.ru/v2.1/timeline"
UA = "Mozilla/5.0 (compatible; GrokBotNews/1.0)"

# Default interests for @tochka_vx — edit via --topics or config later
DEFAULT_TOPICS = {
    "ai": ["ии", "ai", "нейросет", "chatgpt", "openai", "llm", "машинн", "искусственн"],
    "startup": ["стартап", "startup", "seed", "раунд", "инвест", "фаундер", "founder"],
    "business": ["бизнес", "предпринима", "выручк", "маржинал", "unit-экономик", "масштабир"],
    "marketing": ["маркетинг", "реклам", "smm", "контент", "бренд", "трафик"],
    "product": ["продукт", "product", "saas", "mvp", "retention", "онборд"],
    "tech": ["разработк", "технолог", "облак", "api", "devops", "код"],
}


@dataclass
class Item:
    id: int
    title: str
    url: str
    subtitle: str
    date: int
    subsite: str
    hits: list[str]

    def score(self) -> int:
        return len(self.hits)


def fetch_timeline(sorting: str = "date", count: int = 40) -> list[dict]:
    q = urllib.parse.urlencode({"sorting": sorting, "count": count})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("result", {}).get("items", [])


def flatten(entry: dict) -> Item | None:
    data = entry.get("data") or {}
    if entry.get("type") != "entry" or not data.get("id"):
        return None
    title = (data.get("title") or "").strip()
    subtitle = (data.get("subtitle") or data.get("intro") or "").strip()
    # strip html
    subtitle = re.sub(r"<[^>]+>", " ", subtitle)
    subtitle = re.sub(r"\s+", " ", subtitle).strip()
    url = data.get("url") or f"https://vc.ru/{data['id']}"
    if url.startswith("/"):
        url = "https://vc.ru" + url
    subsite = ""
    sub = data.get("subsite") or {}
    if isinstance(sub, dict):
        subsite = (sub.get("name") or sub.get("nickname") or "").strip()
    return Item(
        id=int(data["id"]),
        title=title,
        url=url,
        subtitle=subtitle,
        date=int(data.get("date") or 0),
        subsite=subsite,
        hits=[],
    )


def _kw_hit(blob: str, kw: str) -> bool:
    kw = kw.lower().strip()
    if not kw:
        return False
    # short tokens need word-ish boundaries (avoid "ии" in "улучшить")
    if len(kw) <= 3:
        return re.search(rf"(?<![\wа-яА-ЯёЁ]){re.escape(kw)}(?![\wа-яА-ЯёЁ])", blob, re.I) is not None
    return kw in blob


def match_topics(item: Item, topics: dict[str, list[str]]) -> Item:
    blob = f"{item.title}\n{item.subtitle}\n{item.subsite}".lower()
    hits: list[str] = []
    for name, kws in topics.items():
        if any(_kw_hit(blob, k) for k in kws):
            hits.append(name)
    item.hits = hits
    return item


def main() -> int:
    ap = argparse.ArgumentParser(description="vc.ru feed + topic filter")
    ap.add_argument("--sorting", default="date", choices=["date", "hot", "popular"])
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--min-score", type=int, default=1, help="min matched topic groups")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--all",
        action="store_true",
        help="include non-matching items (marked fit=false)",
    )
    args = ap.parse_args()

    raw = fetch_timeline(args.sorting, args.count)
    items: list[Item] = []
    for e in raw:
        it = flatten(e)
        if not it:
            continue
        items.append(match_topics(it, DEFAULT_TOPICS))

    fitted = [i for i in items if len(i.hits) >= args.min_score]
    fitted.sort(key=lambda i: (-i.score(), -i.date))
    out_items = items if args.all else fitted

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": i.id,
                        "title": i.title,
                        "url": i.url,
                        "subtitle": i.subtitle,
                        "subsite": i.subsite,
                        "topics": i.hits,
                        "fit": len(i.hits) >= args.min_score,
                        "date": i.date,
                    }
                    for i in out_items
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"fetched={len(items)} fit={len(fitted)} sorting={args.sorting}")
        for i in fitted[:20]:
            print(f"- [{','.join(i.hits)}] {i.title}")
            print(f"  {i.url}")
            if i.subtitle:
                print(f"  {i.subtitle[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
