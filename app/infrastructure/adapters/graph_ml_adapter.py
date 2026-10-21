from typing import List, Set

import networkx as nx
from networkx.algorithms import community as nx_comm

from ...ports.graph_ml import GraphMlPort, EdgeData, ClusterAssignmentData


class GraphMlAdapter(GraphMlPort):
    """Adapter for graph clustering and community detection using NetworkX."""

    def detect_communities(
        self,
        node_ids: List[str],
        edges: List[EdgeData],
        algorithm: str = "louvain",
    ) -> List[ClusterAssignmentData]:
        if not node_ids and not edges:
            return []

        algo = (algorithm or "louvain").lower()
        G = nx.Graph()
        G.add_nodes_from(node_ids)

        for e in edges:
            w = float(e.weight) if e.weight > 0 else 1.0
            G.add_edge(e.source_id, e.target_id, weight=w)

        communities: List[Set[str]] = []
        try:
            if G.number_of_edges() == 0:
                communities = [{n} for n in G.nodes()]
            elif algo in ["louvain", "leiden"]:
                communities = list(nx_comm.louvain_communities(G, weight="weight", seed=42))
            elif algo in ["greedy", "greedy_modularity"]:
                communities = list(nx_comm.greedy_modularity_communities(G, weight="weight"))
            elif algo in ["label_propagation", "infomap"]:
                communities = list(nx_comm.label_propagation_communities(G))
            else:
                communities = list(nx_comm.louvain_communities(G, weight="weight", seed=42))
        except Exception:
            communities = list(nx.connected_components(G))

        clusters: List[ClusterAssignmentData] = []
        for i, comm in enumerate(communities):
            nodes_in_comm = sorted(list(comm))
            size = len(nodes_in_comm)
            clusters.append(
                ClusterAssignmentData(
                    cluster_id=f"cluster_{i + 1}",
                    node_ids=nodes_in_comm,
                    metrics={"size": float(size)},
                )
            )

        return clusters
