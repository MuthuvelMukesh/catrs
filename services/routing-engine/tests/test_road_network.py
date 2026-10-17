"""Unit and integration tests for realistic RoadGraph, Dijkstra, A*, and OSM routing."""
from __future__ import annotations

import pytest

from app.routing.osm_adapter import OSMAdapter
from app.routing.road_network import (
    RoadGraph,
    RoadNode,
    RoadSegment,
    UnreachableDestinationError,
)
from app.routing.route_generator import NetworkRouteService


def test_road_graph_construction_and_directionality():
    """Verify directed edge construction, one-way enforcement, and connectivity."""
    graph = RoadGraph("test_grid")
    graph.add_node("A", lat=37.77, lon=-122.42)
    graph.add_node("B", lat=37.77, lon=-122.41)
    graph.add_node("C", lat=37.77, lon=-122.40)

    # A -> B is one-way
    graph.add_segment("seg_A_B", from_node="A", to_node="B", length_m=1000.0, speed_limit_kmh=60.0, one_way=True)
    # B <-> C is bidirectional
    graph.add_segment("seg_B_C", from_node="B", to_node="C", length_m=1000.0, speed_limit_kmh=60.0, one_way=False)

    # Route A -> B should succeed
    path = graph.find_shortest_path_dijkstra("A", "B")
    assert path.nodes == ["A", "B"]
    assert path.total_distance_m == 1000.0
    assert path.total_travel_time_s == pytest.approx(60.0, rel=1e-2)

    # Route B -> A must fail because seg_A_B is one-way
    with pytest.raises(UnreachableDestinationError):
        graph.find_shortest_path_dijkstra("B", "A")

    # Route C -> B should succeed via reverse link
    path_cb = graph.find_shortest_path_dijkstra("C", "B")
    assert path_cb.nodes == ["C", "B"]


def test_dijkstra_and_astar_consistency():
    """Verify Dijkstra and A* produce identical optimal cost paths on a network with coordinates."""
    graph = OSMAdapter.create_sample_urban_network()

    dijkstra_path = graph.find_shortest_path_dijkstra("node_nw", "node_se")
    astar_path = graph.find_shortest_path_astar("node_nw", "node_se")

    # Both must find optimal paths with equivalent minimal travel time and distance
    assert dijkstra_path.total_distance_m == pytest.approx(astar_path.total_distance_m, rel=1e-2)
    assert dijkstra_path.total_travel_time_s == pytest.approx(astar_path.total_travel_time_s, rel=1e-2)
    assert dijkstra_path.origin == astar_path.origin == "node_nw"
    assert dijkstra_path.destination == astar_path.destination == "node_se"


def test_road_closure_and_incident_rerouting():
    """Verify graph dynamic impedance: closures and incidents force alternative path selection."""
    graph = OSMAdapter.create_sample_urban_network()

    # Find initial path
    initial_path = graph.find_shortest_path_astar("node_nw", "node_se")

    # Close first segment on initial path
    first_seg = initial_path.segments[0]
    graph.update_condition(first_seg, is_closed=True)

    # Find new path for passenger car: must not use closed segment
    rerouted_path = graph.find_shortest_path_astar("node_nw", "node_se", vehicle_type="car")
    assert first_seg not in rerouted_path.segments
    assert rerouted_path.total_travel_time_s > 0

    # Emergency vehicle should still be permitted through closed segment
    emergency_path = graph.find_shortest_path_astar("node_nw", "node_se", vehicle_type="emergency")
    assert emergency_path.total_travel_time_s > 0


def test_k_shortest_paths_diversity():
    """Verify Yen's algorithm generates K distinct viable routes."""
    graph = OSMAdapter.create_sample_urban_network()
    k_paths = graph.find_k_alternative_routes("node_nw", "node_se", k=3)

    assert len(k_paths) >= 2
    # Ensure all paths reach destination
    for p in k_paths:
        assert p.origin == "node_nw"
        assert p.destination == "node_se"
        assert len(p.segments) > 0

    # Ensure paths are distinct
    signatures = [tuple(p.segments) for p in k_paths]
    assert len(set(signatures)) == len(signatures)

    # Verify travel times are non-decreasing
    for i in range(len(k_paths) - 1):
        assert k_paths[i].total_travel_time_s <= k_paths[i + 1].total_travel_time_s + 1e-3


def test_turn_restriction_enforcement():
    """Verify turn restrictions prevent illegal maneuver."""
    graph = RoadGraph("restricted_intersection")
    graph.add_node("A")
    graph.add_node("B")
    graph.add_node("C")
    graph.add_node("D")

    # A -> B -> C (restricted turn)
    # A -> B -> D -> C (alternative valid detour)
    graph.add_segment("seg_A_B", "A", "B", length_m=100.0, one_way=True)
    graph.add_segment("seg_B_C", "B", "C", length_m=100.0, one_way=True)
    graph.add_segment("seg_B_D", "B", "D", length_m=150.0, one_way=True)
    graph.add_segment("seg_D_C", "D", "C", length_m=150.0, one_way=True)

    # Prohibit left turn from seg_A_B to seg_B_C at node B
    graph.add_turn_restriction("seg_A_B", "B", "seg_B_C")

    path = graph.find_shortest_path_dijkstra("A", "C")
    assert path.nodes == ["A", "B", "D", "C"]
    assert "seg_B_C" not in path.segments


def test_network_route_service_end_to_end():
    """Verify NetworkRouteService plans, ranks, and diversifies trips on physical road network."""
    service = NetworkRouteService()
    result = service.plan_trip(
        origin_node="node_nw",
        destination_node="node_se",
        trip_category="emergency",
        request_count=10,
        cap_fraction=0.6,
        k_alternatives=3,
    )

    assert result["origin"] == "node_nw"
    assert result["destination"] == "node_se"
    assert len(result["ranked_routes"]) >= 2
    assert sum(result["assignments"].values()) == 10
    assert "explanation" in result
    assert result["explanation"]["recommended_route"]["route_id"] == result["ranked_routes"][0]["route_id"]
