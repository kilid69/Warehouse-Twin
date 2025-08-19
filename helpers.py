import pandas as pd, numpy as np, plotly.graph_objects as go
import networkx as nx
import math
import os, csv
import plotly.graph_objects as go


def nearest_neighbor_order(G, stops, start):
    """Greedy order: from current, go to the unvisited stop with smallest shortest-path distance."""
    unvisited = set(stops) - {start}
    order = [start]
    current = start
    while unvisited:
        # pick the next stop with minimal shortest-path length (by weight)
        nxt = min(unvisited, key=lambda v: nx.shortest_path_length(G, current, v, weight="weight"))
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    return order


def build_node_route(G, stop_nodes:list):
    """
    Return a flat list of node IDs that forms the complete walk visiting every stop in order.
    Example: stops = [DEPOT, S1, S2, DEPOT] -> route includes shortest path DEPOT->S1, then S1->S2, then S2->DEPOT.
    """
    route = []  # will accumulate node ids in walking order
    for a, b in zip(stop_nodes[:-1], stop_nodes[1:]):  # iterate consecutive pairs: (stop[i], stop[i+1])
        hop = nx.shortest_path(G, a, b, weight="weight")  
        if route:                     # if we already have nodes in the route...
            route.extend(hop[1:])     # append hop without its first node to avoid duplicating the join
        else:
            route.extend(hop)         # first hop: take all nodes
    return route                      


def dist(a, b, G):
    ax, ay = G.nodes[a]["x"], G.nodes[a]["y"]
    bx, by = G.nodes[b]["x"], G.nodes[b]["y"]
    return math.hypot(ax - bx, ay - by)

def path_length(route_nodes, G):
    total = 0.0
    for i in range(len(route_nodes) - 1):
        total += dist(route_nodes[i], route_nodes[i+1], G)
    return total


def plot_graph(G, pos=None):
    if pos is None:
        pos = nx.spring_layout(G)
    # edges
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]; x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines',
                            line=dict(width=1), hoverinfo='none')

    # nodes (color by kind)
    kind_color = {'shelf':'#4e79a7','support':'#f28e2b','twin':'#f28e2b'}
    node_x, node_y, node_text, node_color = [], [], [], []
    for n, d in G.nodes(data=True):
        x, y = pos[n]
        node_x.append(x); node_y.append(y)
        node_text.append(f"{n}<br>({x:.2f},{y:.2f})<br>kind={d.get('kind','?')}")
        node_color.append(kind_color.get(d.get('kind','shelf'), '#9c9c9c'))

    node_trace = go.Scatter(x=node_x, y=node_y, mode='markers+text',
                            text=[str(n.split("-")[0]) for n in G.nodes()],
                            textposition='top center',
                            marker=dict(size=6, color=node_color),
                            textfont=dict(size=8),
                            hovertext=node_text, hoverinfo='text')

    fig = go.Figure([edge_trace, node_trace])

    fig.update_layout(
        title="Zoom out or pan to see the whole warehouse", 
        xaxis=dict(
            # scaleanchor="y",
            showgrid=False, 
            range=[20, 700],
            title="width (in Meter)"), 
        yaxis=dict(showgrid=False, range=[400, 800]),     # set a default range to zoom in
        showlegend=False,                            # hide legend for a cleaner look
        height=500,
        margin=dict(l=40, r=40, t=40, b=40)
    )

    return fig


def visited_path(fig:go.Figure, pos:list, route_nodes:list, i:int):
    # grab the coordinates from pos dict
    x_coords = [pos[node][0] for node in route_nodes]
    y_coords = [pos[node][1] for node in route_nodes]   

    colors=["purple", "green", "gold"]

    # --- Dynamic placeholder for visited edges (will be replaced by frames)
    visited_trace = go.Scatter(
        x=x_coords, y=y_coords,                  
        mode="lines",                
        line=dict(width=4, color=colors[i]),     
        name="Visited path"  
    )

    fig.update_layout(
        xaxis=dict(
                scaleanchor="y",
                showgrid=False, 
                range=[20, 700],
                title="width (in Meter)"), 
            yaxis=dict(showgrid=False, range=[min(y_coords)-100, max(y_coords)+100])
            )
    
    fig.add_trace(visited_trace)
    return fig


def ensure_logfile(path="visits.csv"):
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["timestamp_utc", "ip", "path", "referrer", "user_agent"])