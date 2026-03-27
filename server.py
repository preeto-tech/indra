"""
INDRA — FastAPI Backend Server
================================
Run: uvicorn server:app --reload --port 8000
Then open: http://localhost:8000
"""

import os
import asyncio
import shutil
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from autonomous_pipeline import (
    fetch_all_gdelt, fetch_all_rss, fetch_newsdata,
    ingest_articles_to_graph, query_graph,
    load_seen, WORKING_DIR
)

app = FastAPI(title="INDRA Intelligence Graph")

# Serve static files (the frontend)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Status ────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    seen = load_seen()
    graph_file = os.path.join(WORKING_DIR, "graph_chunk_entity_relation.graphml")
    graph_exists = os.path.exists(graph_file)
    return {
        "status": "ready" if graph_exists else "empty",
        "articles_ingested": len(seen),
        "graph_ready": graph_exists,
    }


# ── Sync endpoint (trigger a pull from all sources) ──────────────────────────

@app.post("/api/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    async def do_sync():
        gdelt = fetch_all_gdelt(days_back=1)
        rss   = fetch_all_rss()
        await ingest_articles_to_graph(gdelt + rss)

    background_tasks.add_task(do_sync)
    return {"status": "sync started in background"}


# ── Bootstrap endpoint ────────────────────────────────────────────────────────

@app.post("/api/bootstrap")
async def trigger_bootstrap(background_tasks: BackgroundTasks):
    async def do_bootstrap():
        gdelt = fetch_all_gdelt(days_back=7)
        rss   = fetch_all_rss()
        news  = fetch_newsdata("India defense geopolitics Pakistan China")
        await ingest_articles_to_graph(gdelt + rss + news)

    background_tasks.add_task(do_bootstrap)
    return {"status": "bootstrap started — this takes 3-5 minutes"}


# ── Manual PDF upload (optional) ─────────────────────────────────────────────

@app.post("/api/ingest/pdf")
async def ingest_pdf(file: UploadFile = File(...)):
    from pypdf import PdfReader
    from autonomous_pipeline import ingest_articles_to_graph, article_id

    os.makedirs("uploads", exist_ok=True)
    path = f"uploads/{file.filename}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""

    articles = [{
        "title": file.filename,
        "url": f"local://{file.filename}",
        "date": "",
        "source": "manual-upload",
        "text": text[:50000],
    }]

    count = await ingest_articles_to_graph(articles)
    return {"status": "success", "pages": len(reader.pages), "ingested": count}


# ── Query endpoint ────────────────────────────────────────────────────────────

@app.post("/api/query")
async def query(body: dict):
    question = body.get("question", "")
    mode     = body.get("mode", "hybrid")

    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)

    graph_file = os.path.join(WORKING_DIR, "graph_chunk_entity_relation.graphml")
    if not os.path.exists(graph_file):
        return JSONResponse({"error": "Graph not ready. Run bootstrap first."}, status_code=400)

    try:
        answer = await query_graph(question, mode=mode)
        return {"answer": answer, "question": question}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Graph visualization data ──────────────────────────────────────────────────

@app.get("/api/graph-data")
async def graph_data():
    import xml.etree.ElementTree as ET

    graph_file = os.path.join(WORKING_DIR, "graph_chunk_entity_relation.graphml")
    if not os.path.exists(graph_file):
        return {"nodes": [], "edges": []}

    tree = ET.parse(graph_file)
    root = tree.getroot()
    ns   = {"g": "http://graphml.graphdrawing.org/graphml"}

    nodes, edges = [], []
    node_ids = set()

    for node in root.findall(".//g:node", ns):
        nid = node.get("id")
        if nid and nid not in node_ids:
            node_ids.add(nid)
            nodes.append({"id": nid, "label": nid.replace("_", " ").title()[:30]})

    for edge in root.findall(".//g:edge", ns):
        src, tgt = edge.get("source"), edge.get("target")
        if src in node_ids and tgt in node_ids:
            label = ""
            for data in edge.findall("g:data", ns):
                if data.text and len(data.text) < 50:
                    label = data.text[:30]
                    break
            edges.append({"from": src, "to": tgt, "label": label})

    return {"nodes": nodes[:200], "edges": edges[:500],
            "total_nodes": len(nodes), "total_edges": len(edges)}


# ── Serve frontend ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")
