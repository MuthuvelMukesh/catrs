"""OpenStreetMap (OSM) and GeoJSON road network adapter for CATRS.

Imports road networks from OpenStreetMap Overpass JSON, GeoJSON LineStrings, or generates
realistic calibrated urban topologies for local simulation and integration tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import math

from app.routing.road_network import RoadGraph


class OSMAdapter:
    """Adapter for importing real-world road networks from OpenStreetMap and GeoJSON."""

    DEFAULT_SPEED_LIMITS = {
        "motorway": 100.0,
        "trunk": 80.0,
        "primary": 60.0,
        "secondary": 50.0,
        "tertiary": 40.0,
        "residential": 30.0,
        "service": 20.0,
    }

    DEFAULT_CAPACITIES = {
        "motorway": 2000.0,
        "trunk": 1600.0,
        "primary": 1200.0,
        "secondary": 900.0,
        "tertiary": 600.0,
        "residential": 400.0,
    }

    @classmethod
    def from_geojson(cls, data: dict[str, Any] | str | Path) -> RoadGraph:
        """Parse a GeoJSON FeatureCollection into a RoadGraph."""
        if isinstance(data, (str, Path)):
            with open(data, "r", encoding="utf-8") as f:
                geojson = json.load(f)
        else:
            geojson = data

        graph = RoadGraph(name=geojson.get("name", "osm_geojson_network"))
        features = geojson.get("features", [])

        # 1. Process Point features (intersections)
        for feat in features:
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            if geom.get("type") == "Point":
                coords = geom.get("coordinates", [0.0, 0.0])
                node_id = str(props.get("id") or props.get("node_id") or f"node_{len(graph.nodes)}")
                graph.add_node(node_id=node_id, lon=coords[0], lat=coords[1], **props)

        # 2. Process LineString features (road segments)
        for feat in features:
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            if geom.get("type") == "LineString":
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue

                u_id = str(props.get("from") or props.get("u") or f"pt_{coords[0][0]}_{coords[0][1]}")
                v_id = str(props.get("to") or props.get("v") or f"pt_{coords[-1][0]}_{coords[-1][1]}")

                if u_id not in graph.nodes:
                    graph.add_node(u_id, lon=coords[0][0], lat=coords[0][1])
                if v_id not in graph.nodes:
                    graph.add_node(v_id, lon=coords[-1][0], lat=coords[-1][1])

                highway = str(props.get("highway", "primary")).lower()
                speed_limit = float(props.get("maxspeed", cls.DEFAULT_SPEED_LIMITS.get(highway, 50.0)))
                one_way = bool(props.get("oneway", False) or props.get("one_way", False))
                lanes = int(props.get("lanes", 1))
                capacity = float(props.get("capacity", cls.DEFAULT_CAPACITIES.get(highway, 1000.0))) * lanes

                # Estimate length in meters if not provided
                length_m = props.get("length_m")
                if length_m is None:
                    length_m = cls._calculate_linestring_length_m(coords)

                seg_id = str(props.get("id") or props.get("segment_id") or f"seg_{u_id}_{v_id}")
                graph.add_segment(
                    segment_id=seg_id,
                    from_node=u_id,
                    to_node=v_id,
                    length_m=float(length_m),
                    speed_limit_kmh=speed_limit,
                    road_class=highway,
                    one_way=one_way,
                    lanes=lanes,
                    capacity_vph=capacity,
                    geometry=coords,
                )

        return graph

    @classmethod
    def _calculate_linestring_length_m(cls, coords: list[list[float]]) -> float:
        """Compute geodesic distance along coordinate chain."""
        total = 0.0
        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i][:2]
            lon2, lat2 = coords[i + 1][:2]
            dlat = (lat2 - lat1) * 111000.0
            dlon = (lon2 - lon1) * 111000.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
            total += math.sqrt(dlat * dlat + dlon * dlon)
        return max(10.0, total)

    @classmethod
    def create_sample_urban_network(cls) -> RoadGraph:
        """Generate a realistic downtown urban corridor network with highway arterials."""
        graph = RoadGraph(name="metropolitan_downtown_arterial")

        # Define 12 realistic city nodes (Downtown Grid + Ring Expressway)
        # Coordinates modeled around central business district
        nodes = {
            "node_nw": (37.780, -122.420),
            "node_n": (37.780, -122.410),
            "node_ne": (37.780, -122.400),
            "node_w": (37.770, -122.420),
            "node_center": (37.770, -122.410),
            "node_e": (37.770, -122.400),
            "node_sw": (37.760, -122.420),
            "node_s": (37.760, -122.410),
            "node_se": (37.760, -122.400),
            # Perimeter Highway bypass nodes
            "hwy_west": (37.770, -122.435),
            "hwy_east": (37.770, -122.385),
            "hwy_north": (37.795, -122.410),
        }

        for nid, (lat, lon) in nodes.items():
            graph.add_node(nid, lat=lat, lon=lon)

        # 1. Downtown Arterials (Bidirectional, 50 km/h, 1200 m)
        grid_links = [
            ("node_nw", "node_n", 800.0, "primary", False),
            ("node_n", "node_ne", 800.0, "primary", False),
            ("node_w", "node_center", 800.0, "primary", False),
            ("node_center", "node_e", 800.0, "primary", False),
            ("node_sw", "node_s", 800.0, "primary", False),
            ("node_s", "node_se", 800.0, "primary", False),
            ("node_nw", "node_w", 1100.0, "secondary", False),
            ("node_w", "node_sw", 1100.0, "secondary", False),
            ("node_ne", "node_e", 1100.0, "secondary", False),
            ("node_e", "node_se", 1100.0, "secondary", False),
        ]
        for u, v, length, r_class, oneway in grid_links:
            graph.add_segment(
                segment_id=f"art_{u}_{v}",
                from_node=u,
                to_node=v,
                length_m=length,
                speed_limit_kmh=50.0,
                road_class=r_class,
                one_way=oneway,
                lanes=2,
            )

        # 2. One-Way Downtown Main Street corridor (North -> South through center)
        graph.add_segment(
            segment_id="corridor_main_ns1",
            from_node="node_n",
            to_node="node_center",
            length_m=1100.0,
            speed_limit_kmh=45.0,
            road_class="primary",
            one_way=True,
            lanes=3,
            capacity_vph=1800.0,
        )
        graph.add_segment(
            segment_id="corridor_main_ns2",
            from_node="node_center",
            to_node="node_s",
            length_m=1100.0,
            speed_limit_kmh=45.0,
            road_class="primary",
            one_way=True,
            lanes=3,
            capacity_vph=1800.0,
        )

        # 3. High-Speed Outer Highway Bypass (85 km/h, 2500 m)
        hwy_links = [
            ("node_nw", "hwy_north", 1800.0),
            ("hwy_north", "node_ne", 1800.0),
            ("node_w", "hwy_west", 1400.0),
            ("hwy_west", "node_sw", 1400.0),
            ("node_e", "hwy_east", 1400.0),
            ("hwy_east", "node_se", 1400.0),
        ]
        for u, v, length in hwy_links:
            graph.add_segment(
                segment_id=f"hwy_{u}_{v}",
                from_node=u,
                to_node=v,
                length_m=length,
                speed_limit_kmh=85.0,
                road_class="motorway",
                one_way=False,
                lanes=3,
                capacity_vph=2400.0,
            )

        # Prohibit illegal U-turn / sharp turn maneuver
        graph.add_turn_restriction("corridor_main_ns1", "node_center", "art_node_center_node_e_rev")

        return graph
