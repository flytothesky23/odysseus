from pathlib import Path

from routes.history import history_routes


def test_history_wire_timestamps_use_shared_kst_serializer():
    source = Path(history_routes.__file__).read_text(encoding="utf-8")

    assert source.count("_message_timestamp_iso(m.timestamp)") == 2
    assert 'm.timestamp.isoformat() + "Z"' not in source
