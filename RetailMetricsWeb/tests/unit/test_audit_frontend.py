from streamlit.testing.v1 import AppTest

def _audit_page():
    from frontend.views.audit_trail import render

    class FakeAuditClient:
        def get(self, path, params=None):
            assert path == "/admin/audit-logs"
            assert params["limit"] == 25
            return {"items": [{"audit_log_id": 17, "created_at": "2026-09-19T10:00:00+08:00",
                               "actor_display": "Customer #12", "actor_role": "customer",
                               "action": "ORDER_CREATED", "entity_type": "order", "entity_id": "91",
                               "description": "Order created.", "old_values": None,
                               "new_values": {"order_status": "pending"}, "ip_address": "127.0.0.1"}],
                    "total": 1, "limit": 25, "offset": 0}

    render(FakeAuditClient())


def test_audit_page_is_read_only_and_shows_safe_event():
    app = AppTest.from_function(_audit_page).run(timeout=20)
    assert not app.exception
    assert "Audit Trail" in [title.value for title in app.title]
    assert {widget.label for widget in app.text_input} >= {"Search action or entity", "Action", "Entity type"}
    assert not [button for button in app.button if "delete" in button.label.lower() or "edit" in button.label.lower()]
