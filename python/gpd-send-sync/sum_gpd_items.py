#!/usr/bin/env python3
"""Sum configured item counts from GPD response-body log lines."""

import argparse
import re
from pathlib import Path


ITEMS_PATTERN = re.compile(r"response body: Configuration completed for (\d+) items\b")


def sum_configured_items(log_path: Path) -> tuple[int, int]:
    total = 0
    response_count = 0
    with log_path.open(encoding="utf-8", errors="replace") as log_file:
        for line in log_file:
            match = ITEMS_PATTERN.search(line)
            if match:
                total += int(match.group(1))
                response_count += 1
    return total, response_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log_file",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("gpd-send.log"),
        help="Log file to read (default: gpd-send.log next to this script).",
    )
    args = parser.parse_args()
    try:
        total, response_count = sum_configured_items(args.log_file)
    except OSError as error:
        parser.error(f"Cannot read '{args.log_file}': {error}")
    print(f"Totale item configurati: {total} (risposte conteggiate: {response_count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
