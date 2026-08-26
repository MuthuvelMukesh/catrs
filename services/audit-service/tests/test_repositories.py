from app.repositories import AuditResultRepository, PolicyRepository


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))
        return FakeResult(self.row)


def test_policy_repository_reads_latest_effective_policy():
    connection = FakeConnection(("v2", "2026-08-26", {"emergency": 12.0}))
    repository = PolicyRepository(connection)

    policy = repository.get_effective(effective_at="2026-08-27")

    assert policy == {
        "version": "v2",
        "effective_date": "2026-08-26",
        "weights": {"emergency": 12.0},
    }
    assert "ORDER BY effective_date DESC" in connection.executed[0][0]


def test_policy_repository_reads_pinned_policy_version():
    connection = FakeConnection(("v2", "2026-08-26", {"emergency": 12.0}))
    repository = PolicyRepository(connection)

    assert repository.get_version(version="v2") == {
        "version": "v2",
        "effective_date": "2026-08-26",
        "weights": {"emergency": 12.0},
    }
    assert "WHERE version = %s" in connection.executed[0][0]


def test_audit_result_repository_writes_result_to_audit_table():
    connection = FakeConnection(None)
    repository = AuditResultRepository(connection)

    repository.insert({
        "route_id": "r1",
        "outcome_at": "2026-08-27T12:00:00Z",
        "weight_schedule_version": "v2",
        "valid": True,
        "failures": [],
    })

    query, params = connection.executed[0]
    assert "INSERT INTO audit_results" in query
    assert params[0:4] == ("r1", "2026-08-27T12:00:00Z", "v2", True)
