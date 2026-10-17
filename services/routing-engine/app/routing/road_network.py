"""Extensible road network graph model with realistic topology and pathfinding algorithms.

Supports:
- Directed road segments with one-way and turn restrictions.
- Road classification, lane counts, and access constraints (emergency, freight, etc.).
- Segment capacities and BPR (Bureau of Public Roads) travel time impedance functions.
- Dynamic conditions: closures, incidents, weather slowdowns, and predicted speeds.
- Dijkstra, A*, and Yen's K-Shortest Paths algorithms for viable alternative routing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
from typing import Any, Callable


class RoutingError(ValueError):
    """Base routing exception."""
    pass


class UnreachableDestinationError(RoutingError):
    """Raised when no viable path exists between origin and destination."""
    pass


class InvalidPathError(RoutingError):
    """Raised when a path violates graph connectivity or restrictions."""
    pass


@dataclass
class RoadNode:
    """Represents an intersection or vertex in the road network."""
    node_id: str
    lat: float = 0.0
    lon: float = 0.0
    elevation_m: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoadSegment:
    """Represents a directed road link between two intersections."""
    segment_id: str
    from_node: str
    to_node: str
    length_m: float
    speed_limit_kmh: float = 50.0
    road_class: str = "primary"  # motorway, trunk, primary, secondary, residential, service
    one_way: bool = False
    lanes: int = 1
    capacity_vph: float = 1200.0  # capacity in vehicles per hour
    access_restrictions: set[str] = field(default_factory=lambda: {"car", "emergency", "transit", "freight"})
    is_closed: bool = False
    active_incident: bool = False
    incident_delay_s: float = 0.0
    current_speed_kmh: float | None = None
    predicted_speed_kmh: float | None = None
    flow_count: int = 0  # current vehicle load for congestion modeling
    geometry: list[tuple[float, float]] = field(default_factory=list)

    @property
    def effective_speed_kmh(self) -> float:
        """Resolve effective speed considering predictions, live speed, or speed limit."""
        if self.is_closed:
            return 0.001  # Virtually blocked
        if self.predicted_speed_kmh is not None and self.predicted_speed_kmh > 0:
            return max(5.0, min(self.predicted_speed_kmh, self.speed_limit_kmh * 1.3))
        if self.current_speed_kmh is not None and self.current_speed_kmh > 0:
            return max(5.0, min(self.current_speed_kmh, self.speed_limit_kmh * 1.3))
        return self.speed_limit_kmh

    def compute_travel_time_seconds(self, vehicle_count: int = 0) -> float:
        """Calculate dynamic travel time using BPR congestion formula."""
        if self.is_closed:
            return 86400.0  # 24 hours penalty for closed road

        speed_kmh = self.effective_speed_kmh
        speed_mps = max(0.5, speed_kmh * (1000.0 / 3600.0))
        t_free = self.length_m / speed_mps

        # BPR congestion impedance: t = t_0 * (1 + alpha * (V/C)^beta)
        load = self.flow_count + vehicle_count
        alpha = 0.15
        beta = 4.0
        bpr_factor = 1.0 + alpha * math.pow(load / max(1.0, self.capacity_vph), beta)

        incident_delay = self.incident_delay_s if self.active_incident else 0.0
        return (t_free * bpr_factor) + incident_delay


@dataclass(frozen=True)
class PathResult:
    """Detailed pathfinding outcome."""
    origin: str
    destination: str
    route_id: str
    nodes: list[str]
    segments: list[str]
    total_distance_m: float
    total_travel_time_s: float
    is_valid: bool = True
    bottleneck_segment: str | None = None
    applied_penalties: float = 0.0


class RoadGraph:
    """Directed graph representing an urban or regional road transportation network."""

    def __init__(self, name: str = "road_network") -> None:
        self.name = name
        self.nodes: dict[str, RoadNode] = {}
        self.segments: dict[str, RoadSegment] = {}
        # Outgoing edges: node_id -> list of segment_ids
        self._adj_out: dict[str, list[str]] = {}
        # Incoming edges: node_id -> list of segment_ids
        self._adj_in: dict[str, list[str]] = {}
        # Turn restrictions: (from_seg, via_node, to_seg)
        self.turn_restrictions: set[tuple[str, str, str]] = set()

    def add_node(self, node_id: str, lat: float = 0.0, lon: float = 0.0, **kwargs: Any) -> RoadNode:
        node = RoadNode(node_id=str(node_id), lat=lat, lon=lon, metadata=kwargs)
        self.nodes[node.node_id] = node
        self._adj_out.setdefault(node.node_id, [])
        self._adj_in.setdefault(node.node_id, [])
        return node

    def add_segment(
        self,
        segment_id: str,
        from_node: str,
        to_node: str,
        length_m: float,
        speed_limit_kmh: float = 50.0,
        road_class: str = "primary",
        one_way: bool = False,
        lanes: int = 1,
        capacity_vph: float = 1200.0,
        access_restrictions: set[str] | None = None,
        is_closed: bool = False,
        geometry: list[tuple[float, float]] | None = None,
    ) -> RoadSegment:
        if from_node not in self.nodes:
            self.add_node(from_node)
        if to_node not in self.nodes:
            self.add_node(to_node)

        seg = RoadSegment(
            segment_id=segment_id,
            from_node=from_node,
            to_node=to_node,
            length_m=float(length_m),
            speed_limit_kmh=float(speed_limit_kmh),
            road_class=road_class,
            one_way=one_way,
            lanes=lanes,
            capacity_vph=capacity_vph,
            access_restrictions=access_restrictions or {"car", "emergency", "transit", "freight"},
            is_closed=is_closed,
            geometry=geometry or [],
        )
        self.segments[segment_id] = seg
        self._adj_out[from_node].append(segment_id)
        self._adj_in[to_node].append(segment_id)

        # If bidirectional, add reverse edge with _rev suffix if not existing
        if not one_way:
            rev_id = f"{segment_id}_rev"
            rev_seg = RoadSegment(
                segment_id=rev_id,
                from_node=to_node,
                to_node=from_node,
                length_m=float(length_m),
                speed_limit_kmh=float(speed_limit_kmh),
                road_class=road_class,
                one_way=False,
                lanes=lanes,
                capacity_vph=capacity_vph,
                access_restrictions=access_restrictions or {"car", "emergency", "transit", "freight"},
                is_closed=is_closed,
                geometry=list(reversed(geometry)) if geometry else [],
            )
            self.segments[rev_id] = rev_seg
            self._adj_out[to_node].append(rev_id)
            self._adj_in[from_node].append(rev_id)

        return seg

    def add_turn_restriction(self, from_segment_id: str, via_node: str, to_segment_id: str) -> None:
        """Register prohibited turn maneuver."""
        self.turn_restrictions.add((from_segment_id, via_node, to_segment_id))

    def update_condition(
        self,
        segment_id: str,
        current_speed: float | None = None,
        predicted_speed: float | None = None,
        is_closed: bool | None = None,
        active_incident: bool | None = None,
        incident_delay_s: float | None = None,
        flow_count: int | None = None,
    ) -> bool:
        """Update live operating parameters of an existing road link."""
        seg = self.segments.get(segment_id)
        if seg is None:
            return False
        if current_speed is not None:
            seg.current_speed_kmh = float(current_speed)
        if predicted_speed is not None:
            seg.predicted_speed_kmh = float(predicted_speed)
        if is_closed is not None:
            seg.is_closed = bool(is_closed)
        if active_incident is not None:
            seg.active_incident = bool(active_incident)
        if incident_delay_s is not None:
            seg.incident_delay_s = float(incident_delay_s)
        if flow_count is not None:
            seg.flow_count = int(flow_count)
        return True

    def find_shortest_path_dijkstra(
        self,
        origin: str,
        destination: str,
        vehicle_type: str = "car",
        avoid_segments: set[str] | None = None,
    ) -> PathResult:
        """Compute minimum travel-time path using Dijkstra's algorithm."""
        return self._dijkstra(
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            avoid_segments=avoid_segments or set(),
            heuristic=None,
        )

    def find_shortest_path_astar(
        self,
        origin: str,
        destination: str,
        vehicle_type: str = "car",
        avoid_segments: set[str] | None = None,
    ) -> PathResult:
        """Compute minimum travel-time path using A* with Euclidean distance heuristic."""
        dest_node = self.nodes.get(destination)
        if not dest_node:
            raise UnreachableDestinationError(f"Destination node {destination!r} does not exist in graph")

        # Max velocity in network for admissible heuristic (in m/s)
        max_speed_kmh = max((s.speed_limit_kmh for s in self.segments.values()), default=100.0)
        max_speed_mps = (max_speed_kmh * 1000.0) / 3600.0

        def heuristic(node_id: str) -> float:
            cur = self.nodes.get(node_id)
            if not cur or (cur.lat == 0.0 and cur.lon == 0.0):
                return 0.0
            # Euclidean distance proxy in meters
            dlat = (dest_node.lat - cur.lat) * 111000.0
            dlon = (dest_node.lon - cur.lon) * 111000.0 * math.cos(math.radians(cur.lat))
            dist_m = math.sqrt(dlat * dlat + dlon * dlon)
            return dist_m / max_speed_mps

        return self._dijkstra(
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            avoid_segments=avoid_segments or set(),
            heuristic=heuristic,
        )

    def compute_turn_penalty_seconds(
        self,
        prev_seg_id: str | None,
        current_node: str,
        next_seg_id: str,
    ) -> float:
        """Compute realistic intersection turn delay based on maneuver angle."""
        if not prev_seg_id or prev_seg_id not in self.segments or next_seg_id not in self.segments:
            return 0.0

        prev_seg = self.segments[prev_seg_id]
        next_seg = self.segments[next_seg_id]

        p_node = self.nodes.get(prev_seg.from_node)
        u_node = self.nodes.get(current_node)
        v_node = self.nodes.get(next_seg.to_node)

        if not p_node or not u_node or not v_node:
            return 0.0

        dx1 = u_node.lon - p_node.lon
        dy1 = u_node.lat - p_node.lat
        dx2 = v_node.lon - u_node.lon
        dy2 = v_node.lat - u_node.lat

        if (dx1 == 0 and dy1 == 0) or (dx2 == 0 and dy2 == 0):
            return 0.0

        angle1 = math.degrees(math.atan2(dy1, dx1))
        angle2 = math.degrees(math.atan2(dy2, dx2))
        d_angle = (angle2 - angle1 + 180.0) % 360.0 - 180.0

        # Straight maneuver (-30 deg to +30 deg): nominal signal passage delay
        if abs(d_angle) <= 30.0:
            return 0.5
        # Left turn (+30 deg to +120 deg): crossing oncoming traffic lane delay (in right-hand drive)
        if 30.0 < d_angle <= 120.0:
            return 12.0
        # Right turn (-120 deg to -30 deg): yield/deceleration delay
        if -120.0 <= d_angle < -30.0:
            return 4.0
        # U-turn (> 150 deg): major intersection maneuver
        if abs(d_angle) > 150.0:
            return 25.0
        return 6.0

    def _dijkstra(
        self,
        origin: str,
        destination: str,
        vehicle_type: str,
        avoid_segments: set[str],
        heuristic: Callable[[str], float] | None = None,
        enable_turn_penalties: bool = True,
    ) -> PathResult:
        if origin not in self.nodes:
            raise UnreachableDestinationError(f"Origin node {origin!r} does not exist in graph")
        if destination not in self.nodes:
            raise UnreachableDestinationError(f"Destination node {destination!r} does not exist in graph")

        if origin == destination:
            return PathResult(
                origin=origin,
                destination=destination,
                route_id=f"route_{origin}_{destination}",
                nodes=[origin],
                segments=[],
                total_distance_m=0.0,
                total_travel_time_s=0.0,
            )

        # Priority queue item: (f_score, g_score, current_node, previous_segment_id)
        pq: list[tuple[float, float, str, str | None]] = [(0.0, 0.0, origin, None)]
        # Edge-expanded state tracking: (node_id, incoming_seg_id) -> best_g
        g_scores: dict[tuple[str, str | None], float] = {(origin, None): 0.0}
        # Predecessor map: (node_id, incoming_seg_id) -> (predecessor_node, predecessor_incoming_seg)
        came_from: dict[tuple[str, str | None], tuple[str, str | None]] = {}

        while pq:
            f, g, u, prev_seg = heapq.heappop(pq)

            if u == destination:
                # Reconstruct path by tracing predecessor states
                nodes = [destination]
                segments = []
                total_dist = 0.0
                curr_node = destination
                curr_seg = prev_seg

                while curr_seg is not None:
                    segments.append(curr_seg)
                    total_dist += self.segments[curr_seg].length_m
                    p_state = came_from.get((curr_node, curr_seg))
                    if not p_state:
                        break
                    p_node, p_prev_seg = p_state
                    nodes.append(p_node)
                    curr_node = p_node
                    curr_seg = p_prev_seg

                nodes.reverse()
                segments.reverse()
                return PathResult(
                    origin=origin,
                    destination=destination,
                    route_id=f"route_{origin}_{destination}_{len(segments)}",
                    nodes=nodes,
                    segments=segments,
                    total_distance_m=round(total_dist, 2),
                    total_travel_time_s=round(g, 2),
                )

            if g > g_scores.get((u, prev_seg), float("inf")):
                continue

            for seg_id in self._adj_out.get(u, []):
                if seg_id in avoid_segments:
                    continue

                seg = self.segments[seg_id]
                # Enforce closures and access restrictions
                if seg.is_closed and vehicle_type != "emergency":
                    continue
                if vehicle_type not in seg.access_restrictions:
                    continue
                # Check prohibited turn restrictions
                if prev_seg is not None and (prev_seg, u, seg_id) in self.turn_restrictions:
                    continue

                v = seg.to_node
                base_time = seg.compute_travel_time_seconds()
                turn_delay = (
                    self.compute_turn_penalty_seconds(prev_seg, u, seg_id)
                    if (enable_turn_penalties and vehicle_type != "emergency")
                    else 0.0
                )
                new_g = g + base_time + turn_delay

                state = (v, seg_id)
                if new_g < g_scores.get(state, float("inf")):
                    g_scores[state] = new_g
                    came_from[state] = (u, prev_seg)
                    h = heuristic(v) if heuristic else 0.0
                    heapq.heappush(pq, (new_g + h, new_g, v, seg_id))

        raise UnreachableDestinationError(
            f"No viable route found from {origin!r} to {destination!r} for vehicle type {vehicle_type!r}"
        )

    def find_k_alternative_routes(
        self,
        origin: str,
        destination: str,
        k: int = 3,
        vehicle_type: str = "car",
    ) -> list[PathResult]:
        """Generate up to K viable alternative routes using Yen's algorithm."""
        if k < 1:
            return []

        try:
            first_path = self.find_shortest_path_astar(origin, destination, vehicle_type=vehicle_type)
        except UnreachableDestinationError:
            return []

        paths = [first_path]
        candidates: list[PathResult] = []
        candidate_signatures: set[tuple[str, ...]] = {tuple(first_path.segments)}

        for i in range(1, k):
            prev_path = paths[i - 1]
            for j in range(len(prev_path.segments)):
                spur_node = prev_path.nodes[j]
                root_path_nodes = prev_path.nodes[: j + 1]
                root_path_segments = prev_path.segments[:j]

                # Segments to temporarily avoid
                avoid: set[str] = set()
                for p in paths:
                    if len(p.segments) > j and p.segments[:j] == root_path_segments:
                        avoid.add(p.segments[j])

    def compute_path_travel_time(
        self,
        segments: list[str],
        vehicle_type: str = "car",
    ) -> tuple[float, float]:
        """Compute exact cumulative distance and travel time including all turn penalties."""
        dist = 0.0
        time_s = 0.0
        for idx, seg_id in enumerate(segments):
            seg = self.segments[seg_id]
            dist += seg.length_m
            p_seg = segments[idx - 1] if idx > 0 else None
            turn_delay = (
                self.compute_turn_penalty_seconds(p_seg, seg.from_node, seg_id)
                if vehicle_type != "emergency"
                else 0.0
            )
            time_s += seg.compute_travel_time_seconds() + turn_delay
        return round(dist, 2), round(time_s, 2)

    def find_k_alternative_routes(
        self,
        origin: str,
        destination: str,
        k: int = 3,
        vehicle_type: str = "car",
    ) -> list[PathResult]:
        """Generate up to K viable alternative routes using Yen's algorithm."""
        if k < 1:
            return []

        try:
            first_path = self.find_shortest_path_astar(origin, destination, vehicle_type=vehicle_type)
        except UnreachableDestinationError:
            return []

        paths = [first_path]
        candidates: list[PathResult] = []
        candidate_signatures: set[tuple[str, ...]] = {tuple(first_path.segments)}

        for i in range(1, k):
            prev_path = paths[i - 1]
            for j in range(len(prev_path.segments)):
                spur_node = prev_path.nodes[j]
                root_path_nodes = prev_path.nodes[: j + 1]
                root_path_segments = prev_path.segments[:j]

                # Segments to temporarily avoid
                avoid: set[str] = set()
                for p in paths:
                    if len(p.segments) > j and p.segments[:j] == root_path_segments:
                        avoid.add(p.segments[j])

                try:
                    spur_path = self._dijkstra(
                        origin=spur_node,
                        destination=destination,
                        vehicle_type=vehicle_type,
                        avoid_segments=avoid,
                    )
                    total_nodes = root_path_nodes[:-1] + spur_path.nodes
                    total_segs = root_path_segments + spur_path.segments
                    sig = tuple(total_segs)

                    if sig not in candidate_signatures:
                        candidate_signatures.add(sig)
                        calc_dist, calc_time = self.compute_path_travel_time(total_segs, vehicle_type=vehicle_type)
                        cand = PathResult(
                            origin=origin,
                            destination=destination,
                            route_id=f"alt_route_{i}_{len(candidates)+1}",
                            nodes=total_nodes,
                            segments=total_segs,
                            total_distance_m=calc_dist,
                            total_travel_time_s=calc_time,
                        )
                        candidates.append(cand)
                except UnreachableDestinationError:
                    continue

            if not candidates:
                break
            candidates.sort(key=lambda p: p.total_travel_time_s)
            paths.append(candidates.pop(0))

        # Guarantee non-decreasing travel times across candidate routes
        paths.sort(key=lambda p: p.total_travel_time_s)
        return paths
