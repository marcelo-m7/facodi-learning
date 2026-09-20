import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "facodi_learning" / "data" / "lesti_2026_27.json"
ALLOWED_PERIODS = {"semester_1", "semester_2", "annual", "other"}
ALLOWED_CLASSIFICATIONS = {"mandatory", "optional", "unspecified"}


def main():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reference = payload["reference"]
    source = urlparse(reference["source_url"])
    assert source.scheme == "https"
    assert source.hostname in {"ualg.pt", "www.ualg.pt", "ise.ualg.pt", "www.ise.ualg.pt"}
    assert reference["provider"] == "ualg"
    assert reference["external_programme_code"] == "1941"
    assert reference["academic_year"] == "2026/27"
    assert len(reference["source_hash"]) == 64

    seen = set()
    for index, unit in enumerate(payload["units"], start=1):
        code = str(unit["code"]).strip()
        assert code, f"unit {index}: empty code"
        assert code not in seen, f"unit {index}: duplicate code {code}"
        seen.add(code)
        assert str(unit["name"]).strip(), f"unit {code}: empty name"
        assert float(unit["credits"]) >= 0, f"unit {code}: negative ECTS"
        assert int(unit["year"]) >= 1, f"unit {code}: invalid year"
        assert unit["period"] in ALLOWED_PERIODS, f"unit {code}: invalid period"
        assert (
            unit["classification"] in ALLOWED_CLASSIFICATIONS
        ), f"unit {code}: invalid classification"

    assert len(seen) == 43, f"expected 43 distinct official unit codes, got {len(seen)}"
    print(f"Validated {len(seen)} LESTI unit codes from {reference['source_url']}")


if __name__ == "__main__":
    main()
