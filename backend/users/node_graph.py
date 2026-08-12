"""Layout + SVG rendering for the Node question-graph (next_node/alt_next_node)."""
from collections import defaultdict, deque
from html import escape

NODE_W, NODE_H = 180, 64
X_GAP, Y_GAP = 220, 130
MARGIN = 40


def _build_edges(nodes):
    edges = []
    for n in nodes:
        if n.next_node_id:
            edges.append((n.id, n.next_node_id, "next"))
        if n.alt_next_node_id:
            edges.append((n.id, n.alt_next_node_id, "alt"))
    return edges


def _layered_positions(nodes, edges):
    node_ids = [n.id for n in nodes]
    incoming = defaultdict(int)
    adj = defaultdict(list)
    for src, dst, _ in edges:
        incoming[dst] += 1
        adj[src].append(dst)

    roots = [nid for nid in node_ids if incoming.get(nid, 0) == 0]
    if not roots and node_ids:
        roots = [min(node_ids)]

    depth = {}
    dq = deque()
    for r in roots:
        depth[r] = 0
        dq.append(r)
    while dq:
        cur = dq.popleft()
        for nxt in adj[cur]:
            if nxt in node_ids and (nxt not in depth or depth[nxt] > depth[cur] + 1):
                depth[nxt] = depth[cur] + 1
                dq.append(nxt)

    # Orphan nodes never reached from a root (e.g. a broken/dead branch)
    # get their own trailing layer so they're still visible on the map.
    max_depth = max(depth.values(), default=-1)
    for nid in node_ids:
        if nid not in depth:
            max_depth += 1
            depth[nid] = max_depth

    layers = defaultdict(list)
    for nid in node_ids:
        layers[depth[nid]].append(nid)

    pos = {}
    for d, ids in layers.items():
        for i, nid in enumerate(sorted(ids)):
            pos[nid] = (
                MARGIN + i * X_GAP,
                MARGIN + d * Y_GAP,
            )
    return pos


def render_node_graph_svg(nodes):
    """Return (svg_markup, width, height) for the given Node queryset/list."""
    nodes = list(nodes)
    edges = _build_edges(nodes)
    pos = _layered_positions(nodes, edges)
    by_id = {n.id: n for n in nodes}

    if not pos:
        return "<p>No nodes to display.</p>", 0, 0

    width = max(x for x, y in pos.values()) + NODE_W + MARGIN
    height = max(y for x, y in pos.values()) + NODE_H + MARGIN

    parts = [
        '<defs>',
        '<marker id="arrow-next" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#2b6cb0"/></marker>',
        '<marker id="arrow-alt" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#c05621"/></marker>',
        '</defs>',
    ]

    # Edges first so node boxes render on top.
    for src, dst, kind in edges:
        if src not in pos or dst not in pos:
            continue
        x1, y1 = pos[src]
        x2, y2 = pos[dst]
        x1c, y1c = x1 + NODE_W / 2, y1 + NODE_H
        x2c, y2c = x2 + NODE_W / 2, y2
        if kind == "next":
            stroke, marker, dash = "#2b6cb0", "arrow-next", ""
        else:
            stroke, marker, dash = "#c05621", "arrow-alt", 'stroke-dasharray="6,4"'
        midy = (y1c + y2c) / 2
        path = f"M{x1c},{y1c} C{x1c},{midy} {x2c},{midy} {x2c},{y2c}"
        parts.append(
            f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="2" '
            f'{dash} marker-end="url(#{marker})"/>'
        )

    for nid, (x, y) in pos.items():
        n = by_id[nid]
        is_junction = n.effects == "JUNCTION"
        fill = "#fefcbf" if is_junction else "#ebf8ff"
        stroke = "#d69e2e" if is_junction else "#2b6cb0"
        label = escape(n.data)[:34] + ("…" if len(n.data) > 34 else "")
        parts.append(
            f'<a xlink:href="/admin/users/node/{nid}/change/">'
            f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="8" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + 10}" y="{y + 20}" font-size="12" font-weight="bold" '
            f'fill="#1a202c">#{nid}</text>'
            f'<text x="{x + 10}" y="{y + 38}" font-size="11" fill="#2d3748">{label}</text>'
            f'<text x="{x + 10}" y="{y + 54}" font-size="10" fill="#4a5568">'
            f'{escape(n.effects)} · score {n.score}</text>'
            f'</a>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        + "".join(parts)
        + "</svg>"
    )
    return svg, width, height
