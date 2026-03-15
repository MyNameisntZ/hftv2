from __future__ import annotations

import json
import sys
from urllib.request import urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def fetch_json(url: str) -> dict:
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL

    health = fetch_json(f"{base_url}/health")
    overview = fetch_json(f"{base_url}/system/overview")
    engines = fetch_json(f"{base_url}/system/engines")

    print(f"health.status={health['status']}")
    print(f"overview.event_bus_backend={overview['event_bus_backend']}")
    print(f"overview.healthy_engines={overview['healthy_engines']}/{overview['engine_count']}")
    print(f"engines.count={len(engines['engines'])}")

    for engine in engines["engines"]:
        print(f"engine.{engine['name']}={engine['status']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

