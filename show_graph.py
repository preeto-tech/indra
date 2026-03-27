"""
INDRA — Graph Visualizer
=========================
Generates a standalone dark-theme HTML visualization of the knowledge graph.

Usage:
  python show_graph.py              # Generate and open the graph
  python show_graph.py highlight "India"   # Highlight nodes matching a keyword
"""

import sys
import os
import xml.etree.ElementTree as ET
from pyvis.network import Network

GRAPHML = "./indra_data/graph_chunk_entity_relation.graphml"
OUTPUT  = "./static/graph.html"

TYPE_COLORS = {
    "organization": "#7F77DD",
    "person":       "#00C896",
    "geo":          "#378ADD",
    "event":        "#EF9F27",
    "policy":       "#D85A30",
    "default":      "#888780",
}

def generate(highlight_keyword: str = ""):
    if not os.path.exists(GRAPHML):
        print("No graph yet — run: python autonomous_pipeline.py bootstrap")
        return

    tree = ET.parse(GRAPHML)
    root = tree.getroot()
    ns   = {"g": "http://graphml.graphdrawing.org/graphml"}

    net = Network(
        height="100%", width="100%",
        bgcolor="#0A1628", font_color="#ffffff",
        directed=True
    )

    net.set_options("""
    {
      "nodes": {
        "borderWidth": 2,
        "shadow": {"enabled": true, "size": 8}
      },
      "edges": {
        "smooth": {"type": "curvedCW", "roundness": 0.2},
        "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
        "color": {"opacity": 0.6}
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 150
        },
        "solver": "forceAtlas2Based",
        "stabilization": {"iterations": 150}
      },
      "interaction": {"hover": true, "tooltipDelay": 100}
    }
    """)

    nodes_added = set()
    edges_added = 0

    for node in root.findall(".//g:node", ns):
        nid = node.get("id")
        if not nid or nid in nodes_added:
            continue

        label = nid.replace("_", " ").title()[:30]
        is_highlight = highlight_keyword and highlight_keyword.lower() in label.lower()

        color = "#EF9F27" if is_highlight else "#00C896"
        size  = 35 if is_highlight else 22

        net.add_node(nid, label=label, color=color, size=size,
                     title=f"Entity: {label}")
        nodes_added.add(nid)

    for edge in root.findall(".//g:edge", ns):
        src, tgt = edge.get("source"), edge.get("target")
        if src not in nodes_added or tgt not in nodes_added:
            continue
        label = ""
        for data in edge.findall("g:data", ns):
            if data.text and len(data.text) < 50:
                label = data.text[:30]
                break
        net.add_edge(src, tgt, label=label,
                     color="#00C896", title=label)
        edges_added += 1

    os.makedirs("static", exist_ok=True)
    net.write_html(OUTPUT)
    print(f"Graph: {len(nodes_added)} nodes, {edges_added} edges")
    print(f"Saved to: {OUTPUT}")
    return len(nodes_added), edges_added


if __name__ == "__main__":
    kw = sys.argv[2] if len(sys.argv) > 2 else ""
    generate(highlight_keyword=kw)

    # Auto-open in browser
    import subprocess, platform
    if platform.system() == "Darwin":
        subprocess.run(["open", OUTPUT])
    elif platform.system() == "Windows":
        os.startfile(OUTPUT)
    else:
        subprocess.run(["xdg-open", OUTPUT])
