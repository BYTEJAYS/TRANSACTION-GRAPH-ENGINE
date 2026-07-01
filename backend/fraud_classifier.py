"""
Rule-based fraud classifier for manually ingested transaction chains.

Detection rules:
  1. Forwarding chain depth > 3 hops  (A → B → C → D → E)
  2. Same amount repeated ≥ 3 times   (5000 → 5000 → 5000)
  3. Circular path detected            (A → B → C → A)
  4. Fan-out: one account → ≥ 4 unique recipients
"""

from collections import defaultdict, Counter
from typing import List, Dict, Any, Set


class ManualFraudClassifier:

    def classify(self, transactions: List[Dict]) -> Dict[str, Any]:
        if not transactions:
            return {"status": "normal", "rules_triggered": [], "suspicious_nodes": []}

        out_map: Dict[str, List[str]] = defaultdict(list)
        amounts: List[float] = []

        for t in transactions:
            out_map[t["from_account"]].append(t["to_account"])
            amounts.append(float(t["amount"]))

        rules: List[str] = []
        suspicious: Set[str] = set()

        # Rule 1: longest forwarding chain > 3 hops
        for start in list(out_map.keys()):
            depth, path = self._max_chain_depth(start, out_map, frozenset())
            if depth > 3:
                rules.append("chain_depth_exceeded")
                suspicious.update(path)
                break

        # Rule 2: same amount used ≥ 3 times
        for amount, count in Counter(amounts).items():
            if count >= 3:
                rules.append("repeated_amount_forwarding")
                for t in transactions:
                    if float(t["amount"]) == amount:
                        suspicious.add(t["from_account"])
                        suspicious.add(t["to_account"])
                break

        # Rule 3: circular path
        cycle = self._find_cycle(out_map)
        if cycle:
            rules.append("circular_path_detected")
            suspicious.update(cycle)

        # Rule 4: fan-out to ≥ 4 unique targets
        for acct, targets in out_map.items():
            if len(set(targets)) >= 4:
                rules.append("fan_out_detected")
                suspicious.add(acct)
                suspicious.update(set(targets))
                break

        return {
            "status": "fraud" if rules else "normal",
            "rules_triggered": rules,
            "suspicious_nodes": list(suspicious),
        }

    def _max_chain_depth(
        self,
        node: str,
        out_map: Dict[str, List[str]],
        visited: frozenset,
    ) -> tuple:
        if node in visited or node not in out_map:
            return 0, [node]
        visited = visited | {node}
        best_depth, best_path = 0, [node]
        for nxt in set(out_map[node]):
            d, p = self._max_chain_depth(nxt, out_map, visited)
            if d + 1 > best_depth:
                best_depth, best_path = d + 1, [node] + p
        return best_depth, best_path

    def _find_cycle(self, out_map: Dict[str, List[str]]) -> List[str]:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node: str, path: List[str]) -> List[str]:
            visited.add(node)
            rec_stack.add(node)
            for nbr in set(out_map.get(node, [])):
                if nbr not in visited:
                    result = dfs(nbr, path + [nbr])
                    if result:
                        return result
                elif nbr in rec_stack:
                    idx = next((i for i, n in enumerate(path) if n == nbr), 0)
                    return path[idx:]
            rec_stack.discard(node)
            return []

        for node in list(out_map.keys()):
            if node not in visited:
                result = dfs(node, [node])
                if result:
                    return result
        return []
