"""
INDRA — Autonomous Data Pipeline
=================================
Zero manual input. Run once and the graph builds itself.

Sources (all free, no API key needed except NewsData):
  1. RSS feeds          — Indian & international news (PIB, IE, Hindu, TOI, Livemint)
  2. NewsData.io API    — India-focused news (free: 200 req/day)

Run modes:
  python autonomous_pipeline.py bootstrap   # First-time: loads recent data
  python autonomous_pipeline.py sync        # Incremental: pulls only new articles
  python autonomous_pipeline.py watch       # Continuous: polls every 15 minutes
  python autonomous_pipeline.py query "your question"
"""

import os
import json
import time
import asyncio
import hashlib
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

WORKING_DIR  = "./indra_data"
SEEN_FILE    = "./indra_data/seen_articles.json"
NEWSDATA_KEY = os.getenv("NEWSDATA_API_KEY", "")

# Verified-working RSS feeds (tested 2026-03-27)
RSS_SOURCES = {
    # ── International / geopolitics ──
    "The Hindu Intl":    "https://www.thehindu.com/news/international/?service=rss",
    "The Hindu National":"https://www.thehindu.com/news/national/?service=rss",
    "IE World":          "https://indianexpress.com/section/world/feed/",
    "IE India":          "https://indianexpress.com/section/india/feed/",
    "TOI World":         "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
    "TOI India":         "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    # ── Economy & strategic ──
    "Livemint Economy":  "https://www.livemint.com/rss/economy",
    "Livemint Politics": "https://www.livemint.com/rss/politics",
}

os.makedirs(WORKING_DIR, exist_ok=True)

# ── Dedup engine ──────────────────────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


# ── RSS Feed Fetcher (with retry) ─────────────────────────────────────────────

def fetch_rss(name: str, url: str, max_items: int = 20) -> list:
    """Fetch articles from a single RSS feed with retry logic."""
    import requests

    for attempt in range(2):  # 1 retry
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={"User-Agent": "INDRA-Bot/1.0 (geopolitical intelligence)"},
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            # Handle both RSS 2.0 and Atom feeds
            items = (
                root.findall(".//item")
                or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            )

            articles = []
            for item in items[:max_items]:
                title = (getattr(item.find("title"), "text", "") or "").strip()
                link  = (getattr(item.find("link"),  "text", "") or "").strip()
                desc  = (getattr(item.find("description"), "text", "") or "").strip()
                date  = (getattr(item.find("pubDate"), "text", "") or "").strip()

                # For Atom feeds
                if not link:
                    link_el = item.find("{http://www.w3.org/2005/Atom}link")
                    if link_el is not None:
                        link = link_el.get("href", "")

                if title and link:
                    articles.append({
                        "title": title,
                        "url": link,
                        "date": date,
                        "source": name,
                        "text": f"{title}. {desc}"[:2000],
                    })
            print(f"  [RSS] {name}: {len(articles)} articles")
            return articles

        except requests.exceptions.Timeout:
            if attempt == 0:
                print(f"  [RSS] {name}: timeout, retrying...")
                time.sleep(1)
            else:
                print(f"  [RSS] {name}: timeout after retry — skipping")
                return []
        except Exception as e:
            print(f"  [RSS] {name}: error — {e}")
            return []


def fetch_all_rss() -> list:
    """Fetch from all RSS sources with progress tracking."""
    print("\n[RSS] Fetching from all sources...")
    all_articles = []
    success_count = 0
    for name, url in RSS_SOURCES.items():
        articles = fetch_rss(name, url)
        if articles:
            success_count += 1
        all_articles.extend(articles)
    print(f"  [RSS] Total: {len(all_articles)} articles from {success_count}/{len(RSS_SOURCES)} feeds")
    return all_articles


# ── NewsData.io ───────────────────────────────────────────────────────────────

def fetch_newsdata(query: str = "India geopolitics defense") -> list:
    if not NEWSDATA_KEY:
        print("  [NewsData] No API key — skipping (free key at newsdata.io)")
        return []
    import requests
    url = (
        "https://newsdata.io/api/1/news"
        f"?apikey={NEWSDATA_KEY}&q={requests.utils.quote(query)}"
        "&country=in&language=en&category=politics,world"
    )
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
        results = data.get("results", [])
        if not isinstance(results, list):
            print(f"  [NewsData] Unexpected response format: {type(results)}")
            return []
        articles = []
        for item in results:
            if not isinstance(item, dict):
                continue
            articles.append({
                "title":  item.get("title", ""),
                "url":    item.get("link", ""),
                "date":   item.get("pubDate", ""),
                "source": item.get("source_id", "newsdata"),
                "text":   (item.get("title", "") + ". " + (item.get("description") or ""))[:2000],
            })
        print(f"  [NewsData] Got {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"  [NewsData] Error: {e}")
        return []


# ── Full-text fetcher ─────────────────────────────────────────────────────────

def fetch_article_text(url: str, snippet: str) -> str:
    import requests
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = False
            self.skip_tags = {"script","style","nav","footer","header"}
        def handle_starttag(self, tag, attrs):
            if tag in self.skip_tags: self.skip = True
        def handle_endtag(self, tag):
            if tag in self.skip_tags: self.skip = False
        def handle_data(self, data):
            s = data.strip()
            if not self.skip and len(s) > 40: self.parts.append(s)
        def get_text(self): return " ".join(self.parts)[:8000]

    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
        p = TextExtractor(); p.feed(resp.text)
        text = p.get_text()
        return text if len(text) > 200 else snippet
    except:
        return snippet


# ── Groq LLM Wrapper ──────────────────────────────────────────────────────────

async def groq_complete(
    prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs
) -> str:
    """Groq-compatible LLM complete function for LightRAG."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    for msg in history_messages:
        messages.append(msg)

    messages.append({"role": "user", "content": prompt})

    # Filter to only Groq-supported params
    allowed_params = ["model", "messages", "temperature", "max_tokens", "top_p", "stream", "stop"]
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            **filtered_kwargs
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  [Groq] Error: {e}")
        return f"Error from Groq: {e}"


# ── LightRAG helpers ─────────────────────────────────────────────────────────

# Cache the embedding model globally so it's loaded only once
_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        print("  [Embedding] Loading model (one-time)...")
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("  [Embedding] Model ready.")
    return _embedding_model


async def _create_rag():
    """Create and initialize a LightRAG instance."""
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc

    async def hf_embedding(texts: list[str]) -> list[list[float]]:
        import numpy as np
        model = _get_embedding_model()
        embeddings = model.encode(texts)
        return np.array(embeddings)

    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=groq_complete,
        embedding_func=EmbeddingFunc(
            embedding_dim=384, max_token_size=512, func=hf_embedding
        ),
    )
    await rag.initialize_storages()
    return rag


# ── LightRAG ingestion ────────────────────────────────────────────────────────

async def ingest_articles_to_graph(articles: list, fetch_full_text: bool = False):
    rag = await _create_rag()

    seen = load_seen()
    new_count = 0
    errors = 0

    for article in articles:
        aid = article_id(article["url"])
        if aid in seen:
            continue

        text = article["text"]
        if fetch_full_text and article.get("url"):
            print(f"  [Fetch] {article['title'][:60]}...")
            text = fetch_article_text(article["url"], text)

        doc = f"""
SOURCE: {article.get('source','unknown')}
DATE: {article.get('date','unknown')}
TITLE: {article.get('title','')}
URL: {article.get('url','')}

{text}
        """.strip()

        if len(doc) < 100:
            continue

        try:
            print(f"  [Graph] Ingesting: {article['title'][:70]}...")
            await rag.ainsert(doc)
            seen.add(aid)
            new_count += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            errors += 1
            print(f"  [Graph] Failed: {e}")

    save_seen(seen)
    print(f"\n[Graph] Ingested {new_count} new articles. Errors: {errors}. Total seen: {len(seen)}")
    return new_count


# ── Query engine ──────────────────────────────────────────────────────────────

async def query_graph(question: str, mode: str = "hybrid") -> str:
    from lightrag import QueryParam
    rag = await _create_rag()
    try:
        return await rag.aquery(question, param=QueryParam(mode=mode))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: Query failed: {e}")
        return None


# ── Pipeline modes ────────────────────────────────────────────────────────────

async def bootstrap():
    print("\n" + "="*60)
    print("INDRA BOOTSTRAP — Loading intelligence from all sources")
    print("="*60)
    rss     = fetch_all_rss()
    news    = fetch_newsdata("India defense geopolitics Pakistan China")
    all_art = rss + news
    print(f"\n[Pipeline] Total articles to ingest: {len(all_art)}")
    await ingest_articles_to_graph(all_art, fetch_full_text=False)
    print("\n[INDRA] Bootstrap complete. Graph is ready.")


async def sync():
    print("\n[INDRA] Sync — pulling latest articles...")
    rss = fetch_all_rss()
    await ingest_articles_to_graph(rss, fetch_full_text=False)
    print(f"[INDRA] Sync complete at {datetime.datetime.now().strftime('%H:%M:%S')}")


async def watch():
    print("\n[INDRA] Watch mode — syncing every 15 minutes. Ctrl+C to stop.\n")
    while True:
        try:
            await sync()
            print("[INDRA] Next sync in 15 minutes...\n")
            await asyncio.sleep(15 * 60)
        except KeyboardInterrupt:
            print("\n[INDRA] Watch mode stopped.")
            break
        except Exception as e:
            print(f"[INDRA] Error: {e} — retrying in 5 minutes")
            await asyncio.sleep(5 * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
INDRA Autonomous Pipeline
--------------------------
  python autonomous_pipeline.py bootstrap        # Load recent articles (run once)
  python autonomous_pipeline.py sync             # Pull latest articles
  python autonomous_pipeline.py watch            # Continuous 15min polling
  python autonomous_pipeline.py query "..."      # Query the graph
  python autonomous_pipeline.py sources          # List data sources
        """)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "bootstrap":
        asyncio.run(bootstrap())
    elif cmd == "sync":
        asyncio.run(sync())
    elif cmd == "watch":
        asyncio.run(watch())
    elif cmd == "query" and len(sys.argv) > 2:
        q = " ".join(sys.argv[2:])
        print(f"\n[INDRA] Querying: {q}")
        result = asyncio.run(query_graph(q))
        print("\n" + "="*60)
        print("INDRA INTELLIGENCE RESPONSE:")
        print("="*60)
        print(result)
    elif cmd == "sources":
        print(f"\nRSS feeds ({len(RSS_SOURCES)}):")
        for n, u in RSS_SOURCES.items(): print(f"  {n}: {u}")
        print(f"\nNewsData: {'configured' if NEWSDATA_KEY else 'not set (get free key at newsdata.io)'}")
    else:
        print(f"Unknown command: {cmd}")
