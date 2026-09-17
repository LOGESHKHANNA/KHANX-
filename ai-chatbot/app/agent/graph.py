"""
Lightweight graph engine inspired by LangGraph.
Provides a simple StateGraph class that allows adding node functions and conditional edges.
CompiledGraph.run(state) executes the graph respecting max_iterations and returns the final state.
"""
import asyncio
from typing import Callable, Dict, Any, List, Tuple


class StateGraph:
    """Define a directed graph of async node functions.

    Nodes are identified by a string name and must be async callables accepting a state dict.
    Edges are defined via ``add_conditional_edges`` which maps a predicate function to a target node.
    """

    def __init__(self):
        self._nodes: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._edges: Dict[str, List[Tuple[Callable[[Dict[str, Any]], bool], str]]] = {}
        self._start_node: str | None = None

    def add_node(self, name: str, fn: Callable[[Dict[str, Any]], Any]):
        self._nodes[name] = fn
        if self._start_node is None:
            self._start_node = name
        return self

    def add_conditional_edges(
        self,
        source: str,
        conditions: List[Tuple[Callable[[Dict[str, Any]], bool], str]],
        default: str | None = None,
    ):
        """Add edges from *source* to target nodes based on predicates.

        ``conditions`` is a list of (predicate, target_name) tuples evaluated in order.
        The first predicate returning ``True`` determines the next node.
        If none match, ``default`` is used (must be a valid node name).
        """
        self._edges[source] = conditions
        if default:
            # Append a catch‑all predicate that always returns True
            self._edges[source].append((lambda _: True, default))
        return self

    def set_start(self, name: str):
        if name not in self._nodes:
            raise ValueError(f"Start node '{name}' not registered")
        self._start_node = name
        return self

    def compile(self):
        if not self._start_node:
            raise RuntimeError("Graph has no start node defined")
        return CompiledGraph(self._nodes, self._edges, self._start_node)


class CompiledGraph:
    """Executable graph – runs async nodes until a node returns ``{"is_complete": True}``.

    The graph also respects ``state["max_iterations"]`` and ``state["iteration_count"]``.
    Any exception is captured into ``state["errors"]`` and the graph aborts.
    """

    def __init__(self, nodes: Dict[str, Callable[[Dict[str, Any]], Any]], edges: Dict[str, List[Tuple[Callable[[Dict[str, Any]], bool], str]]], start: str):
        self.nodes = nodes
        self.edges = edges
        self.start = start

    async def run(self, state: Dict[str, Any]):
        current = self.start
        while True:
            # Guard against runaway loops
            state["iteration_count"] = state.get("iteration_count", 0) + 1
            if state["iteration_count"] > state.get("max_iterations", 5):
                state.setdefault("errors", []).append("Maximum graph iterations exceeded")
                break
            # Execute node
            node_fn = self.nodes.get(current)
            if node_fn is None:
                state.setdefault("errors", []).append(f"Node '{current}' not found")
                break
            try:
                result = await node_fn(state)
                # Node can optionally return a dict with explicit next node
                if isinstance(result, dict) and result.get("next_node"):
                    next_node = result["next_node"]
                else:
                    # Determine next node via conditional edges
                    conds = self.edges.get(current, [])
                    next_node = None
                    for pred, target in conds:
                        if pred(state):
                            next_node = target
                            break
                # If node signals completion, exit loop
                if state.get("is_complete"):
                    break
                if not next_node:
                    # No further edge – treat as termination
                    break
                current = next_node
            except Exception as exc:
                state.setdefault("errors", []).append(str(exc))
                break
        return state
