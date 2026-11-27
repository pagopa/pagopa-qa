"""Imposta send_sync = true su apd.payment_option per i NAV presenti nel CSV.

Variabili d'ambiente: PGHOST, PGPORT (default 5432), PGUSER, PGPASSWORD.
Uso:
    python update_send_sync.py --dry-run
    python update_send_sync.py
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg2

ORG_FISCAL_CODE = "00136380805"
DB_NAME = "apd"
SCHEMA = "apd"
DEFAULT_CSV = Path(__file__).with_name("debiti_non_pagati.csv")


def read_navs(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        navs = [row["numero_avviso"].strip() for row in csv.DictReader(f)]
    return list(dict.fromkeys(n for n in navs if n))


def chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true",
                        help="Esegue gli update e fa rollback finale (nessuna modifica persistita)")
    args = parser.parse_args()

    navs = read_navs(args.csv)
    print(f"NAV letti dal CSV: {len(navs)}")

    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=DB_NAME,
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
    )

    query = (
        f"UPDATE {SCHEMA}.payment_option SET send_sync = false "
        "WHERE organization_fiscal_code = %s AND nav = ANY(%s) "
        "AND send_sync IS DISTINCT FROM false"
    )

    total = 0
    try:
        with conn.cursor() as cur:
            for n, batch in enumerate(chunks(navs, args.batch_size), start=1):
                cur.execute(query, (ORG_FISCAL_CODE, batch))
                total += cur.rowcount
                if not args.dry_run:
                    conn.commit()
                print(f"batch {n}: {cur.rowcount}/{len(batch)} aggiornati (totale {total})")
        if args.dry_run:
            conn.rollback()
            print("DRY RUN: rollback eseguito")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Record aggiornati: {total} su {len(navs)} NAV")
    return 0


if __name__ == "__main__":
    sys.exit(main())
