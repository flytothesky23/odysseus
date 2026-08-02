import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_naive_database_timestamps_are_parsed_as_utc_before_relative_display():
    script = """
      const mod = await import(process.argv[1]);
      const values = [
        mod.parseOdysseusTimestamp('2026-08-02 10:13:38.120535').toISOString(),
        mod.parseOdysseusTimestamp('2026-08-02T19:13:38+09:00').toISOString(),
      ];
      process.stdout.write(JSON.stringify(values));
    """
    module_uri = (ROOT / "static/js/time.js").as_uri()
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, module_uri],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == [
        "2026-08-02T10:13:38.120Z",
        "2026-08-02T10:13:38.000Z",
    ]


def test_library_relative_times_use_the_database_timestamp_parser():
    document_library = (ROOT / "static/js/documentLibrary.js").read_text(encoding="utf-8")
    sessions = (ROOT / "static/js/sessions.js").read_text(encoding="utf-8")

    assert "import { parseOdysseusTimestamp } from './time.js';" in document_library
    assert "import { parseOdysseusTimestamp } from './time.js';" in sessions
    assert "parseOdysseusTimestamp(isoString).getTime()" in document_library
    assert "parseOdysseusTimestamp(iso).getTime()" in document_library
    assert "parseOdysseusTimestamp(iso).getTime()" in sessions
