"""Access and isolation impacts from blocked roads: which buildings lose road access, which facilities are cut off, and how long the detours are.
Network: the HOTOSM roads inside the area (vertices snapped to a 5 m grid so touching roads connect). Blocked segments (flow depth >= 0.5 m or rock reach) are removed.
Component logic: a building is 'cut off' when its nearest road node is not in the largest connected component after removal but WAS before (so rural dead ends
that were already disconnected are not blamed on the event). Detour: for hospitals, the shortest-path length to the area's main node before vs after.
Limits: the network ends at the area boundary (anything outside is unseen), speeds are not modelled (length only), and missing OSM roads make isolation overestimated."""
from __future__ import annotations
import math
import numpy as np
import networkx as nx


def _key(p, q=5.0):
    return (round(p[0] / q), round(p[1] / q))


def build_graph(roads_xy, blocked_flags):
    """roads_xy: list of [(x,y),...] in metres; blocked_flags: bool per road segment list (same nesting) -> (G_full, G_open)."""
    Gf, Go = nx.Graph(), nx.Graph()
    for pts, bl in zip(roads_xy, blocked_flags):
        for (a, b), bk in zip(zip(pts[:-1], pts[1:]), bl):
            ka, kb = _key(a), _key(b)
            if ka == kb:
                continue
            L = math.hypot(a[0] - b[0], a[1] - b[1])
            Gf.add_edge(ka, kb, w=L)
            if not bk:
                Go.add_edge(ka, kb, w=L)
    for n in Gf.nodes:
        Go.add_node(n)
    return Gf, Go


def analyse(roads_xy, blocked_flags, points_xy, point_kinds=None):
    """points_xy: building/facility locations (m). Returns dict with isolation counts and per-facility detours."""
    Gf, Go = build_graph(roads_xy, blocked_flags)
    if Gf.number_of_nodes() == 0:
        return {"error": "no road network in the area"}
    nodes = np.array(list(Gf.nodes)); xy = nodes * 5.0
    from scipy.spatial import cKDTree
    tree = cKDTree(xy)
    big_f = max(nx.connected_components(Gf), key=len)
    big_o = max(nx.connected_components(Go), key=len) if Go.number_of_nodes() else set()
    d, idx = tree.query(np.asarray(points_xy, float))
    near = [tuple(nodes[i]) for i in idx]
    near_ok = d < 400.0                                              # farther than 400 m from any road: unassessable, not counted
    cut = [(n in big_f) and (n not in big_o) and ok for n, ok in zip(near, near_ok)]
    reachable_before = [(n in big_f) and ok for n, ok in zip(near, near_ok)]
    # detour for the points flagged as facilities, measured to the node of the main component nearest its centroid
    anchor = tuple(nodes[tree.query(xy.mean(0))[1]]) if True else None
    out = {"points": int(len(points_xy)), "assessable": int(near_ok.sum()), "cut_off": int(sum(cut)), "cut_off_share": float(sum(cut) / max(1, sum(reachable_before))),
           "roads_nodes": int(Gf.number_of_nodes()), "largest_component_share_before": float(len(big_f) / Gf.number_of_nodes()),
           "largest_component_share_after": float(len(big_o) / Gf.number_of_nodes()), "components_after": int(nx.number_connected_components(Go))}
    if point_kinds is not None:
        det = []
        for i, k in enumerate(point_kinds):
            if k not in ("hospital", "school") or not near_ok[i]:
                continue
            n = near[i]
            try:
                before = nx.shortest_path_length(Gf, n, anchor, weight="w") if (n in Gf and anchor in Gf) else None
            except nx.NetworkXNoPath:
                before = None
            try:
                after = nx.shortest_path_length(Go, n, anchor, weight="w") if (n in Go and anchor in Go) else None
            except nx.NetworkXNoPath:
                after = None
            det.append({"index": i, "kind": k, "before_m": before, "after_m": after, "cut": after is None and before is not None,
                        "extra_m": (after - before) if (before is not None and after is not None) else None})
        cut_f = [d for d in det if d["cut"]]; ext = [d["extra_m"] for d in det if d["extra_m"] is not None]
        out["facilities"] = {"assessed": len(det), "cut_off": len(cut_f), "with_detour": int(sum(1 for e in ext if e > 50)),
                             "median_extra_m": float(np.median(ext)) if ext else 0.0, "max_extra_m": float(max(ext)) if ext else 0.0,
                             "worst": sorted([d for d in det if d["extra_m"] or d["cut"]], key=lambda d: -(1e9 if d["cut"] else d["extra_m"]))[:12]}
    return out
