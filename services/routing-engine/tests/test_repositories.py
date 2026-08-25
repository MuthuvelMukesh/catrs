from app.data.repositories import TrafficRepository, WeightScheduleRepository


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, baseline=(55.5,)):
        self.baseline = baseline
        self.executed = []
        self.batch = None

    def execute(self, query, params):
        self.executed.append((query, params))
        return FakeResult(self.baseline)

    def executemany(self, query, values):
        self.batch = (query, list(values))


def test_traffic_repository_upserts_readings_with_contract_fields():
    connection = FakeConnection()
    repository = TrafficRepository(connection)

    repository.insert_readings([
        {
            "segment_id": "s1",
            "timestamp": "2026-08-26T12:00:00Z",
            "avg_speed": 42.0,
            "vehicle_count": 80,
        }
    ])

    assert connection.batch[1] == [("s1", "2026-08-26T12:00:00Z", 42.0, 80)]
    assert "traffic_readings" in connection.batch[0]


def test_traffic_repository_reads_historical_baseline():
    connection = FakeConnection()
    repository = TrafficRepository(connection)

    assert repository.get_baseline(segment_id="s1", weekday=2, hour=12) == 55.5
    assert connection.executed[0][1] == ("s1", 2, 12)


def test_weight_schedule_repository_inserts_version_without_update_path():
    connection = FakeConnection()
    repository = WeightScheduleRepository(connection)

    repository.insert_version({
        "version": "2026-08-26-v1",
        "effective_date": "2026-08-26",
        "weights": {"emergency": 10.0},
    })

    query, params = connection.executed[0]
    assert "INSERT INTO weight_schedules" in query
    assert params[0] == "2026-08-26-v1"
    assert "ON CONFLICT" not in query
