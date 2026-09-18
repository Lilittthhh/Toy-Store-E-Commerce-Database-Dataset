from retailmetrics_s3.experiments.payload import payload_report


def test_payload_measurements_use_real_positive_serializations(fake_core):
    rows = payload_report(fake_core)
    assert len(rows) == 8
    assert all(row["json_bytes"] > 0 and row["protobuf_bytes"] > 0 for row in rows)
    assert all("reduction_pct" in row for row in rows)

