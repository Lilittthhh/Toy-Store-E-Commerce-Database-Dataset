from repositories.order_workflow_repository import PostgresOrderWorkflowRepository
from repositories.refund_workflow_repository import PostgresRefundWorkflowRepository


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        return {"count": 2}

    def fetchall(self):
        return []


class RecordingConnection:
    def __init__(self):
        self.recording_cursor = RecordingCursor()

    def cursor(self, **_):
        return self.recording_cursor


def test_order_action_queue_filters_actionable_states_and_uses_fifo_order() -> None:
    connection = RecordingConnection()

    PostgresOrderWorkflowRepository(connection).list_customer_orders(None, 25, 0, actionable_only=True)

    list_query, params = connection.recording_cursor.calls[1]
    assert "o.order_status IN ('pending','processing')" in list_query
    assert "ORDER BY o.created_at ASC, o.order_id ASC" in list_query
    assert params == [25, 0]


def test_refund_action_queue_filters_actionable_states_and_uses_fifo_order() -> None:
    connection = RecordingConnection()

    PostgresRefundWorkflowRepository(connection).list_staff_requests(None, 25, 0, actionable_only=True)

    list_query, params = connection.recording_cursor.calls[1]
    assert "rr.request_status IN ('pending','approved')" in list_query
    assert "ORDER BY rr.created_at ASC, rr.refund_request_id ASC" in list_query
    assert params == [25, 0]
