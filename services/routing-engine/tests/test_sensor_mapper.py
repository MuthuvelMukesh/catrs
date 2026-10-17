"""Unit tests for SensorRoadMapper spatial KD-tree binding."""
from __future__ import annotations

import pytest

from app.routing.osm_adapter import OSMAdapter
from app.routing.sensor_mapper import SensorRoadMapper


def test_sensor_mapper_binds_graph_segments():
    """Verify that all segments in a road network are mapped to nearest sensor stations."""
    graph = OSMAdapter.create_sample_urban_network()
    mapper = SensorRoadMapper()

    mapping = mapper.bind_graph(graph)
    assert len(mapping) == len(graph.segments)

    # Every segment must have a valid mapped sensor ID
    for seg_id, sid in mapping.items():
        assert sid in mapper.sensor_ids
        assert mapper.get_segment_sensor(seg_id) == sid


def test_sensor_mapper_applies_predicted_speeds_to_edges():
    """Verify predicted speeds are injected into road graph segments."""
    graph = OSMAdapter.create_sample_urban_network()
    mapper = SensorRoadMapper()
    mapper.bind_graph(graph)

    # Inject simulated sensor speeds
    speeds = {sid: 35.0 for sid in mapper.sensor_ids}
    updated_count = mapper.apply_predicted_speeds(graph, speeds)

    assert updated_count == len(graph.segments)
    for seg in graph.segments.values():
        assert seg.predicted_speed_kmh == pytest.approx(35.0)
        assert seg.effective_speed_kmh == pytest.approx(35.0)
