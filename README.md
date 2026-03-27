# INDRA — Intelligence Graph
### Autonomous Geopolitical Analysis Engine

> "See the connections. Before they connect."

INDRA is a Graph-RAG intelligence system that **autonomously ingests geopolitical news** from GDELT, PIB, MEA, ORF, The Hindu, and more — builds a knowledge graph — and lets analysts query it in plain English with cited, graph-traversed answers.

---

## What's in this folder

```
indra/
├── autonomous_pipeline.py   ← The brain — pulls data, builds graph, answers queries
├── server.py                ← FastAPI backend (wraps the pipeline as an API)
├── show_graph.py            ← Standalone graph visualizer (dark theme)
├── requirements.txt         ← All Python dependencies
├── .env.example             ← Copy this to .env and add your keys
├── static/
│   └── index.html           ← War-room UI (served by the FastAPI server)
└── indra_data/              ← Auto-created — stores the knowledge graph
```

---

## Setup (10 minutes total)

### Step 1 — Check Python version
```bash
python --version
```
You need **Python 3.10 or higher**. If not:
```bash
# Mac
brew install python@3.11

# Windows — download from python.org/downloads
# Check "Add to PATH" during install
```

### Step 2 — Create virtual environment
```bash
# Navigate into the indra folder
cd indra

# Create venv
python -m venv venv

# Activate it
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows
```
You should see `(venv)` in your terminal. **All commands from here run inside this.**

### Step 3 — Install dependencies
```bash
pip install -r requirements.txt
```
This takes 3-5 minutes. Go do Step 4 while it runs.

### Step 4 — Set up your API keys

**Copy the example env file:**
```bash
cp .env.example .env
```

**Open `.env` and fill in:**

1. **OpenAI key** (required):
   - Go to: https://platform.openai.com/api-keys
   - Click "Create new secret key"
   - Add $5 credit if needed (GPT-4o-mini costs ~$0.01 per query)
   - Paste it: `OPENAI_API_KEY=sk-...`

2. **NewsData key** (optional but recommended — free):
   - Go to: https://newsdata.io/register
   - Sign up (30 seconds, no credit card)
   - Copy your API key
   - Paste it: `NEWSDATA_API_KEY=...`

---

## Running INDRA

### Option A — Full web app (recommended for demo)

**Terminal 1 — Start the server:**
```bash
uvicorn server:app --reload --port 8000
```

**Terminal 2 — Bootstrap the graph (first time only):**
```bash
python autonomous_pipeline.py bootstrap
```
This pulls the last 7 days from all sources. Takes 3-5 minutes.

**Open your browser:**
```
http://localhost:8000
```

You'll see the war-room UI. Once bootstrap completes, the graph appears and you can query it.

---

### Option B — Command line only

```bash
# Step 1: Load data (run once)
python autonomous_pipeline.py bootstrap

# Step 2: Query it
python autonomous_pipeline.py query "How is China's debt diplomacy affecting India's neighborhood policy?"

# Step 3: See the graph
python show_graph.py
```

---

## Data sources (all autonomous, no manual input)

| Source | What it provides | Update frequency | API key? |
|--------|-----------------|-----------------|---------|
| **GDELT 2.0** | Global geopolitical news in 100+ languages | Every 15 minutes | None needed |
| **PIB Defence** | Indian govt defence press releases | Live RSS | None needed |
| **PIB MEA** | Ministry of External Affairs statements | Live RSS | None needed |
| **ORF** | Observer Research Foundation analysis | Live RSS | None needed |
| **The Hindu** | International news, India perspective | Live RSS | None needed |
| **Indian Express** | Foreign affairs coverage | Live RSS | None needed |
| **DD News** | Doordarshan official news | Live RSS | None needed |
| **NewsData.io** | India-filtered news, 2000 articles/day | Hourly | Free signup |

---

## Keep the graph live (optional)

To keep INDRA continuously updated (syncs every 15 minutes matching GDELT's update cycle):
```bash
python autonomous_pipeline.py watch
```
Run this in a background terminal. Ctrl+C to stop.

---

## Query modes explained

When querying through the UI or CLI, you can choose 3 modes:

| Mode | What it does | Best for |
|------|-------------|---------|
| **Hybrid** | Combines graph traversal + vector search | General questions (default) |
| **Global** | Uses the full graph structure | "What are the major themes?" |
| **Local** | Focuses on specific entities | "Tell me about CPEC" |

---

## Demo script (for presentations)

1. **Open** `http://localhost:8000`
2. **Say:** *"Right now, analysts spend 4 hours manually connecting news articles. INDRA does it in seconds."*
3. **Show** the stats — articles ingested, entities in graph
4. **Type:** *"How is Pakistan's economic instability affecting India's western border security?"*
5. **Show** the graph lighting up + the cited answer
6. **Type second query:** *"What are the second-order effects if the Quad alliance weakens?"*
7. **Closer:** *"This runs on open-source models and can be deployed inside a government data center. Zero data leaves Indian soil."*

---

## Troubleshooting

**"No graph yet" error:**
```bash
python autonomous_pipeline.py bootstrap
```
Wait 3-5 minutes for it to complete.

**OpenAI rate limit error:**
The pipeline has built-in throttling. If you hit limits, reduce batch size:
```python
# In autonomous_pipeline.py, change:
await asyncio.sleep(0.2)   # → await asyncio.sleep(1.0)
```

**GDELT returns no results:**
GDELT sometimes has downtime. The RSS feeds will still work. Check: https://api.gdeltproject.org

**Port 8000 already in use:**
```bash
uvicorn server:app --reload --port 8001
# Then open: http://localhost:8001
```

**Windows venv activation fails:**
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\activate
```

---

## Architecture overview

```
LIVE SOURCES          PIPELINE              STORAGE           QUERY
─────────────         ────────              ───────           ─────
GDELT (15min)  ──┐
PIB RSS        ──┤    autonomous_      →   LightRAG      →   Graph-RAG
MEA RSS        ──┤    pipeline.py          knowledge         hybrid query
ORF RSS        ──┤    (dedup +             graph             → cited
NewsData API   ──┘    LLM extract)         (graphml +        answer
                                           vector store)
```

---

Built by 21Coders | India Innovates 2026
