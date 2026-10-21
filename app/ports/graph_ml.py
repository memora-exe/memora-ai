from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class EdgeData:
    source_id: str
    target_id: str
    weight: float = 1.0


@dataclass
class ClusterAssignmentData:
    cluster_id: str
    node_ids: List[str]
    metrics: Dict[str, float]


class GraphMlPort(ABC):
    """Abstract port for graph machine learning and community detection."""

    @abstractmethod
    def detect_communities(
        self,
        node_ids: List[str],
        edges: List[EdgeData],
        algorithm: str = "louvain",
    ) -> List[ClusterAssignmentData]:
        """Detect graph communities using specified clustering algorithm."""
        pass
