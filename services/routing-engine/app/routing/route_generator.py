"""Route generator service combining graph pathfinding, priority ranking, and diversification."""
from __future__ import annotations

from typing import Any
import math

from app.routing.osm_adapter import OSMAdapter
from app.routing.priority_routing import rank_routes, route_trip
from app.routing.road_network import PathResult, RoadGraph, UnreachableDestinationError
from app.routing.sensor_mapper import SensorRoadMapper


class NetworkRouteService:
    """End-to-end routing service operating on a topological RoadGraph."""

    def __init__(
        self,
        graph: RoadGraph | None = None,
        sensor_mapper: SensorRoadMapper | None = None,
    ) -> None:
        self.graph = graph or OSMAdapter.create_sample_urban_network()
        self.sensor_mapper = sensor_mapper or SensorRoadMapper()
        # Pre-bind graph segments to sensor stations
        self.sensor_mapper.bind_graph(self.graph)

    def plan_trip(
        self,
        *,
        origin_node: str,
        destination_node: str,
        trip_category: str = "commuter_general",
        request_count: int = 1,
        cap_fraction: float = 1.0,
        k_alternatives: int = 3,
        counter: Any | None = None,
        weight_schedule: dict[str, Any] | None = None,
        current_counts: dict[str, int] | None = None,
        predicted_speeds: dict[str, float] | list[float] | None = None,
    ) -> dict[str, Any]:
        """Find candidate routes across the physical network and allocate trips with diversification.

        Raises:
            UnreachableDestinationError: If no path connects origin and destination.
        """
        # Dynamically inject ML speed forecasts into physical graph links
        if predicted_speeds is not None:
            self.sensor_mapper.apply_predicted_speeds(self.graph, predicted_speeds)

        vehicle_type = "emergency" if trip_category == "emergency" else "car"
        paths: list[PathResult] = self.graph.find_k_alternative_routes(
            origin=origin_node,
            destination=destination_node,
            k=max(1, k_alternatives),
            vehicle_type=vehicle_type,
        )

        if not paths:
            raise UnreachableDestinationError(
                f"No viable route found from {origin_node!r} to {destination_node!r} for category {trip_category!r}"
            )

        # Convert PathResults to candidate RouteOptions
        candidate_options: list[dict[str, Any]] = []
        for i, path in enumerate(paths, start=1):
            # Base priority score favors high-capacity corridors and direct routes
            priority_score = 1.5 if "hwy" in path.route_id or "motorway" in str(path.segments) else 1.0
            candidate_options.append({
                "route_id": path.route_id,
                "travel_time_s": path.total_travel_time_s,
                "distance_m": path.total_distance_m,
                "priority_score": priority_score,
                "nodes": path.nodes,
                "segments": path.segments,
            })

        effective_schedule = weight_schedule or {
            "version": "default-v1",
            "effective_date": "2026-01-01",
            "weights": {trip_category: 1.0},
        }

        # Allocate trips across candidate options
        assignments, div_info = route_trip(
            trip_category=trip_category,
            route_options=candidate_options,
            request_count=request_count,
            current_counts=current_counts or {},
            cap_fraction=cap_fraction,
            counter=counter,
            weight_schedule=effective_schedule,
            return_diversification_info=True,
        )

        # Rank and generate full explanation
        ranked_payload = rank_routes(
            trip_category=trip_category,
            routes=candidate_options,
            weight_schedule=effective_schedule,
            include_explanation=True,
            diversification_context=div_info,
        )

        return {
            "origin": origin_node,
            "destination": destination_node,
            "trip_category": trip_category,
            "total_requests": request_count,
            "ranked_routes": ranked_payload["ranked_routes"],
            "assignments": assignments,
            "explanation": ranked_payload["explanation"],
            "candidate_paths": [
                {
                    "route_id": p.route_id,
                    "distance_m": p.total_distance_m,
                    "travel_time_s": p.total_travel_time_s,
                    "nodes": p.nodes,
                    "segments": p.segments,
                }
                for p in paths
            ],
        }
