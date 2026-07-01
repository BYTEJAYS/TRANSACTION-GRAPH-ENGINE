"""
PyTorch Geometric Graph Neural Network for account risk classification
and suspicious subgraph detection.

Falls back gracefully if torch_geometric is not installed.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import SAGEConv, GATConv, global_mean_pool
    from torch_geometric.data import Data, Batch
    TORCH_GEO_AVAILABLE = True
except ImportError:
    TORCH_GEO_AVAILABLE = False

from config import settings


# ── GNN Architecture ──────────────────────────────────────────────────────────

if TORCH_GEO_AVAILABLE:
    class TransactionGraphSAGE(nn.Module):
        """
        GraphSAGE model for node-level risk classification.
        Aggregates neighborhood information to classify each account
        as safe, moderate, high-risk, or critical.
        """

        def __init__(
            self,
            in_channels: int,
            hidden_channels: int = settings.GNN_HIDDEN_DIM,
            out_channels: int = 4,     # 4 risk classes
            num_layers: int = settings.GNN_LAYERS,
            dropout: float = 0.3,
        ):
            super().__init__()
            self.convs = nn.ModuleList()
            self.bns = nn.ModuleList()
            self.dropout = dropout

            # Input layer
            self.convs.append(SAGEConv(in_channels, hidden_channels))
            self.bns.append(nn.BatchNorm1d(hidden_channels))

            # Hidden layers
            for _ in range(num_layers - 2):
                self.convs.append(SAGEConv(hidden_channels, hidden_channels))
                self.bns.append(nn.BatchNorm1d(hidden_channels))

            # Output classification layer
            self.convs.append(SAGEConv(hidden_channels, out_channels))

            self.embedding_projection = nn.Linear(hidden_channels, settings.EMBEDDING_DIM)

        def forward(self, x, edge_index, return_embeddings: bool = False):
            embeddings = None
            for i, (conv, bn) in enumerate(zip(self.convs[:-1], self.bns)):
                x = conv(x, edge_index)
                x = bn(x)
                x = F.relu(x)
                x = F.dropout(x, p=self.dropout, training=self.training)
                if i == len(self.convs) - 2:
                    embeddings = self.embedding_projection(x)

            x = self.convs[-1](x, edge_index)
            logits = F.log_softmax(x, dim=1)

            if return_embeddings:
                return logits, embeddings
            return logits

    class GraphAnomalyDetector(nn.Module):
        """
        Graph-level anomaly detection via autoencoder reconstruction.
        Clusters with high reconstruction error are flagged as suspicious.
        """

        def __init__(self, in_channels: int, hidden_channels: int = 64):
            super().__init__()
            # Encoder
            self.enc1 = SAGEConv(in_channels, hidden_channels)
            self.enc2 = SAGEConv(hidden_channels, hidden_channels // 2)
            # Decoder
            self.dec1 = nn.Linear(hidden_channels // 2, hidden_channels)
            self.dec2 = nn.Linear(hidden_channels, in_channels)

        def forward(self, x, edge_index):
            z = F.relu(self.enc1(x, edge_index))
            z = F.relu(self.enc2(z, edge_index))
            x_hat = F.relu(self.dec1(z))
            x_hat = self.dec2(x_hat)
            return x_hat, z

        def reconstruction_error(self, x, edge_index) -> torch.Tensor:
            x_hat, _ = self.forward(x, edge_index)
            return ((x - x_hat) ** 2).mean(dim=1)


# ── GNN Manager ───────────────────────────────────────────────────────────────

class GNNManager:
    """
    Wraps GNN models with training, inference, and embedding generation.
    Provides CPU-friendly batched inference with periodic re-training.
    """

    NODE_FEATURE_DIM = 12   # features per account node

    def __init__(self):
        self._available = TORCH_GEO_AVAILABLE
        self._sage_model = None
        self._anomaly_model = None
        self._is_trained = False
        self._device = "cpu"

        if self._available:
            self._sage_model = TransactionGraphSAGE(
                in_channels=self.NODE_FEATURE_DIM,
                hidden_channels=settings.GNN_HIDDEN_DIM,
                out_channels=4,
                num_layers=settings.GNN_LAYERS,
            ).to(self._device)
            self._anomaly_model = GraphAnomalyDetector(
                in_channels=self.NODE_FEATURE_DIM,
                hidden_channels=64,
            ).to(self._device)

    def is_available(self) -> bool:
        return self._available

    def build_pyg_data(self, nodes: List[Dict], edges: List[Dict]) -> Optional[Any]:
        """Convert graph state dicts to a PyG Data object."""
        if not self._available or not nodes:
            return None

        import torch
        node_index = {n["id"]: i for i, n in enumerate(nodes)}

        # Node feature matrix: [risk_score, txn_count, total_sent, total_received,
        #                        is_flagged, degree_out, degree_in, account_type_enc,
        #                        pattern_circular, pattern_fanout, pattern_layering, pattern_mule]
        features = []
        for n in nodes:
            patterns = set(n.get("detected_patterns", []))
            features.append([
                float(n.get("risk_score", 0.0)),
                float(min(n.get("transaction_count", 0), 1000)) / 1000,
                float(min(n.get("total_sent", 0), 1e7)) / 1e7,
                float(min(n.get("total_received", 0), 1e7)) / 1e7,
                float(n.get("is_flagged", False)),
                0.0,   # out_degree placeholder
                0.0,   # in_degree placeholder
                {"normal": 0, "mule": 1, "high_value": 2, "merchant": 3}.get(
                    n.get("account_type", "normal"), 0
                ) / 3.0,
                float("circular_transfer" in patterns),
                float("fan_out" in patterns),
                float("layering" in patterns),
                float("mule_chain" in patterns),
            ])

        x = torch.tensor(features, dtype=torch.float32)

        # Edge index
        edge_pairs = []
        for e in edges:
            src_id, dst_id = e.get("source"), e.get("target")
            if src_id in node_index and dst_id in node_index:
                edge_pairs.append([node_index[src_id], node_index[dst_id]])

        if not edge_pairs:
            edge_index = torch.zeros((2, 0), dtype=torch.long)
        else:
            edge_index = torch.tensor(edge_pairs, dtype=torch.long).t().contiguous()

        return Data(x=x, edge_index=edge_index)

    def infer_risk(self, nodes: List[Dict], edges: List[Dict]) -> Dict[str, Dict]:
        """
        Run GNN inference to produce per-node risk logits and embeddings.
        Returns {account_id: {risk_class, confidence, embedding}}.
        """
        if not self._available or not nodes:
            return self._fallback_risk(nodes)

        import torch
        data = self.build_pyg_data(nodes, edges)
        if data is None:
            return self._fallback_risk(nodes)

        self._sage_model.eval()
        with torch.no_grad():
            logits, embeddings = self._sage_model(
                data.x, data.edge_index, return_embeddings=True
            )
            probs = torch.exp(logits)
            classes = probs.argmax(dim=1).tolist()
            confidences = probs.max(dim=1).values.tolist()
            embs = embeddings.tolist() if embeddings is not None else [None] * len(nodes)

        risk_map = {0: "safe", 1: "moderate", 2: "high", 3: "critical"}
        result = {}
        for i, n in enumerate(nodes):
            result[n["id"]] = {
                "risk_class": risk_map.get(classes[i], "safe"),
                "confidence": round(confidences[i], 4),
                "embedding": embs[i],
            }
        return result

    def compute_anomaly_scores(self, nodes: List[Dict], edges: List[Dict]) -> Dict[str, float]:
        """Reconstruction-error based anomaly scores from the autoencoder."""
        if not self._available or not nodes:
            return {n["id"]: n.get("risk_score", 0.0) for n in nodes}

        import torch
        data = self.build_pyg_data(nodes, edges)
        if data is None:
            return {n["id"]: n.get("risk_score", 0.0) for n in nodes}

        self._anomaly_model.eval()
        with torch.no_grad():
            errors = self._anomaly_model.reconstruction_error(data.x, data.edge_index)

        # Normalize to [0, 1]
        err_np = errors.numpy()
        min_e, max_e = err_np.min(), err_np.max()
        normalized = (err_np - min_e) / (max_e - min_e + 1e-9)

        return {n["id"]: float(normalized[i]) for i, n in enumerate(nodes)}

    def _fallback_risk(self, nodes: List[Dict]) -> Dict[str, Dict]:
        """Rule-based fallback when PyTorch Geometric is not available."""
        risk_map = {
            (0.0, 0.3): ("safe", 0.9),
            (0.3, 0.6): ("moderate", 0.75),
            (0.6, 0.8): ("high", 0.8),
            (0.8, 1.1): ("critical", 0.85),
        }
        result = {}
        for n in nodes:
            rs = n.get("risk_score", 0.0)
            for (lo, hi), (cls, conf) in risk_map.items():
                if lo <= rs < hi:
                    result[n["id"]] = {"risk_class": cls, "confidence": conf, "embedding": None}
                    break
        return result

    def get_status(self) -> Dict:
        return {
            "available": self._available,
            "model": "GraphSAGE + GraphAnomalyDetector" if self._available else "rule-based fallback",
            "device": self._device,
            "feature_dim": self.NODE_FEATURE_DIM,
            "embedding_dim": settings.EMBEDDING_DIM if self._available else 0,
        }
