from __future__ import annotations

from decimal import Decimal

import pytest

from retailmetrics_s3.experiments.contract import contract_report
from retailmetrics_s3.models import decimal_to_cents
from retailmetrics_s3.proto import retailmetrics_pb2 as pb
from scripts.generate_proto import verify


def test_proto_compiles_to_committed_generated_modules():
    assert verify()


def test_descriptor_contains_real_services_and_streaming_rpc():
    report = contract_report()
    assert report["service_count"] == 5
    assert report["method_count"] == 16
    methods = [m for service in report["services"] for m in service["methods"]]
    assert any(m["name"] == "StreamSessionMetrics" and m["kind"] == "server-streaming" for m in methods)


def test_generated_message_round_trip():
    original = pb.SalesSummary(session_count=10, order_count=2, revenue_cents=12345)
    restored = pb.SalesSummary.FromString(original.SerializeToString(deterministic=True))
    assert restored == original


def test_money_to_cents_is_decimal_exact_and_rejects_float():
    assert decimal_to_cents(Decimal("19.99")) == 1999
    assert decimal_to_cents(Decimal("0.105")) == 11
    with pytest.raises(TypeError): decimal_to_cents(19.99)

