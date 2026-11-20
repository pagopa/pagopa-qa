#!/usr/bin/env python3
"""Send CSV payment notices to the GPD internal configuration API."""

import argparse
import csv
import http.client
import json
import logging
import math
import os
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Iterator

# HOST = "api.platform.pagopa.it"
HOST = "weuprod.gps.internal.platform.pagopa.it"
# API_PATH = "/gpd/api/v1/internal/config/send"
API_PATH = "/pagopa-gpd-core/internal/config/send"
BATCH_SIZE = 100
LOGGER = logging.getLogger("gpd_send_sync")


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Value must be greater than zero.")
    return number


def positive_timeout(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Timeout must be finite and greater than zero.")
    return number


def read_batches(
    path: Path, organization_field: str, notice_field: str, delimiter: str
) -> Iterator[list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, delimiter=delimiter, strict=True)
        header = next(reader, None)
        if not header:
            raise ValueError("CSV file is empty or has no header.")
        for field in (organization_field, notice_field):
            if header.count(field) != 1:
                raise ValueError(f"CSV header must contain exactly one '{field}' column.")
        organization_index = header.index(organization_field)
        notice_index = header.index(notice_field)
        batch: list[dict[str, str]] = []
        for record_number, row in enumerate(reader, start=1):
            if len(row) != len(header):
                raise ValueError(
                    f"CSV record {record_number} (line {reader.line_num}): "
                    f"expected {len(header)} columns, found {len(row)}."
                )
            organization = row[organization_index].strip()
            notice = row[notice_index].strip()
            if not organization or not notice:
                raise ValueError(
                    f"CSV record {record_number} (line {reader.line_num}): "
                    f"'{organization_field}' and '{notice_field}' must not be empty."
                )
            batch.append({"organizationFiscalCode": organization, "nav": notice})
            if len(batch) == BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch


def send_batch(
    batch_number: int,
    batch: list[dict[str, str]],
    subscription_key: str,
    timeout: float,
    dry_run: bool,
) -> int:
    first_record = (batch_number - 1) * BATCH_SIZE + 1
    last_record = first_record + len(batch) - 1
    payload = json.dumps(batch, ensure_ascii=True).encode("utf-8")
    LOGGER.info(
        "Batch %d: records %d-%d, items=%d, mode=%s",
        batch_number, first_record, last_record, len(batch),
        "DRY RUN" if dry_run else "POST",
    )
    LOGGER.debug("Batch %d request body: %s", batch_number, payload.decode("utf-8"))
    if dry_run:
        return len(batch)

    started = time.monotonic()
    connection = http.client.HTTPSConnection(HOST, timeout=timeout)
    headers = {"Content-Type": "application/json"}
    if subscription_key:
        headers["Ocp-Apim-Subscription-Key"] = subscription_key
    try:
        # A separate connection per batch avoids sharing HTTP state across threads.
        connection.request(
            "POST",
            API_PATH,
            body=payload,
            headers=headers,
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        LOGGER.info(
            "Batch %d: HTTP %d %s, elapsed=%.3fs",
            batch_number, response.status, response.reason, time.monotonic() - started,
        )
        LOGGER.info("Batch %d response body: %s", batch_number, body)
        if not 200 <= response.status < 300:
            LOGGER.error("Batch %d failed with HTTP %d.", batch_number, response.status)
            raise RuntimeError(f"Batch {batch_number}: HTTP {response.status}.")
        return len(batch)
    except (OSError, http.client.HTTPException):
        LOGGER.exception(
            "Batch %d: transport failure after %.3fs; outcome may be unknown.",
            batch_number, time.monotonic() - started,
        )
        raise
    finally:
        connection.close()


def process_batches(
    batches: Iterator[list[dict[str, str]]],
    workers: int,
    subscription_key: str,
    timeout: float,
    dry_run: bool,
) -> tuple[int, int]:
    pending: dict[Future[int], int] = {}
    submitted_batches = 0
    completed_batches = 0
    completed_records = 0
    exhausted = False
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gpd-send") as executor:
        try:
            while pending or not exhausted:
                # Bound in-flight work to the worker count, even for very large CSV files.
                while not exhausted and len(pending) < workers:
                    batch = next(batches, None)
                    if batch is None:
                        exhausted = True
                        break
                    submitted_batches += 1
                    future = executor.submit(
                        send_batch, submitted_batches, batch, subscription_key, timeout, dry_run
                    )
                    pending[future] = submitted_batches
                if not pending:
                    break
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    completed_records += future.result()
                    completed_batches += 1
                    del pending[future]
        finally:
            for future, batch_number in pending.items():
                if future.cancel():
                    LOGGER.warning("Batch %d cancelled before sending.", batch_number)
            if pending:
                LOGGER.warning(
                    "Processing interrupted; waiting for already running batches. "
                    "Some requests may already have been accepted. Check batch logs "
                    "before restarting."
                )
    return completed_batches, completed_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="Input CSV file (UTF-8, optional BOM).")
    parser.add_argument("--organization-field", default="creditortaxid")
    parser.add_argument("--notice-field", default="noticecode")
    parser.add_argument("--delimiter", default=",", help="CSV delimiter (default: comma).")
    parser.add_argument("--workers", type=positive_int, default=1)
    parser.add_argument("--timeout", type=positive_timeout, default=60.0,
                        help="Socket timeout in seconds (default: 60).")
    parser.add_argument("--dry-run", action="store_true", help="Validate without sending.")
    parser.add_argument("--log-level", choices=("INFO", "DEBUG"), default="INFO")
    parser.add_argument("--log-file", type=Path, help="Also append logs to this file.")
    args = parser.parse_args()
    if len(args.delimiter) != 1 or args.delimiter in "\r\n\0":
        parser.error("--delimiter must be one character other than newline or NUL.")
    return args


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
    )
    try:
        if args.log_file:
            handler = logging.FileHandler(args.log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"
            ))
            LOGGER.addHandler(handler)
        subscription_key = os.environ.get("SUBSCRIPTION_KEY", "").strip()
        if subscription_key and any(
            not 33 <= ord(character) <= 126 for character in subscription_key
        ):
            raise ValueError("SUBSCRIPTION_KEY must contain only printable ASCII without spaces.")
        LOGGER.info(
            "Starting: file=%s, endpoint=https://%s%s, workers=%d, batch_size=%d, "
            "organization_field=%s, notice_field=%s, dry_run=%s",
            args.csv_file, HOST, API_PATH, args.workers, BATCH_SIZE,
            args.organization_field, args.notice_field, args.dry_run,
        )
        started = time.monotonic()
        batches = read_batches(
            args.csv_file, args.organization_field, args.notice_field, args.delimiter
        )
        try:
            batch_count, record_count = process_batches(
                batches, args.workers, subscription_key, args.timeout, args.dry_run
            )
        finally:
            batches.close()
        if not record_count:
            raise ValueError("CSV file contains no data records.")
        LOGGER.info(
            "Completed: mode=%s, batches=%d, records=%d, elapsed=%.3fs",
            "DRY RUN (no requests sent)" if args.dry_run else "SEND",
            batch_count, record_count, time.monotonic() - started,
        )
        return 0
    except (OSError, ValueError, csv.Error, http.client.HTTPException, RuntimeError):
        LOGGER.exception("Processing failed. No automatic retries will be attempted.")
        return 1
    except KeyboardInterrupt:
        LOGGER.warning(
            "Interrupted by user. Running requests may have completed; "
            "check batch logs before restarting."
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
