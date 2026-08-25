from pathlib import Path


def test_audit_service_does_not_import_routing_engine():
    source_root = Path(__file__).parents[1] / "app"
    forbidden = ("services.routing-engine", "app.routing", "routing_engine")

    for source_file in source_root.rglob("*.py"):
        source = source_file.read_text(encoding="utf-8")
        assert not any(pattern in source for pattern in forbidden)
