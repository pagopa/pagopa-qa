import os
import json
import time
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from azure.eventhub import EventHubProducerClient, EventData
from datetime import datetime, date, timedelta
import time

import argparse
import re

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
for name in ["uamqp", "uamqp.connection", "uamqp.send", "uamqp.management_link", "azure"]:
    logger = logging.getLogger(name)
    logger.setLevel(logging.WARNING)
    logger.propagate = False

# Env variables for configuration
DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": os.environ["DB_PORT"],
    "dbname": os.environ["DB_NAME"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
}

PAYMENT_POSITION_OUTPUT_EVENTHUB_CONN_STRING = os.environ["PAYMENT_POSITION_OUTPUT_EVENTHUB_CONN_STRING"]
PAYMENT_OPTION_OUTPUT_EVENTHUB_CONN_STRING = os.environ["PAYMENT_OPTION_OUTPUT_EVENTHUB_CONN_STRING"]
TRANSFER_OUTPUT_EVENTHUB_CONN_STRING = os.environ["TRANSFER_OUTPUT_EVENTHUB_CONN_STRING"]
TOPIC_PAYMENT_POSITION = os.environ["TOPIC_PAYMENT_POSITION"]
TOPIC_PAYMENT_OPTION = os.environ["TOPIC_PAYMENT_OPTION"]
TOPIC_TRANSFER = os.environ["TOPIC_TRANSFER"]
BATCH_SIZE = int(os.environ["BATCH_SIZE"])
EVH_CHUNK_SIZE = int(os.environ["EVH_CHUNK_SIZE"])
RETRY_LIMIT = int(os.environ["RETRY_LIMIT"])

def current_timestamps():
    now = time.time()
    ts_ms = int(now * 1000)
    ts_us = int(now * 1_000_000)
    ts_ns = int(now * 1_000_000_000)
    return ts_ms, ts_us, ts_ns

def create_event_hub_producer(event_hub_conn_str, topic_name):
    return EventHubProducerClient.from_connection_string(
        conn_str=event_hub_conn_str,
        eventhub_name=topic_name
    )

def to_millis(value):
    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        dt = value
    elif isinstance(value, str):
        try:
            # Separa data e ora
            date_part = value.split("T")[0] if "T" in value else value.split(" ")[0]
            year = int(date_part.split("-")[0])
            if year > 9999:
                # Rimpiazza l'anno con 9999
                value = value.replace(str(year), "9999", 1)
            dt = datetime.fromisoformat(value)
        except Exception as e:
            raise ValueError(f"❌ Invalid date string: {value}") from e
    else:
        raise TypeError(f"Unsupported type: {type(value)}. Expected str or datetime/date or None.")

    return int(dt.timestamp() * 1000)

def transform_payment_position(row):
    ts_ms, ts_us, ts_ns = current_timestamps()
    pp = {
        "after": {
            "id": row["id"],
            "iupd": row["iupd"],
            "province": row["province"],
            "status": row["status"],
            "type": row["type"],
            "fiscal_code": row["fiscal_code"],
            "postal_code": row["postal_code"],
            "max_due_date": to_millis(row["max_due_date"]),
            "min_due_date": to_millis(row["min_due_date"]),
            "organization_fiscal_code": row["organization_fiscal_code"],
            "company_name": row["company_name"],
            "publish_date": to_millis(row["publish_date"]),
            "validity_date": to_millis(row["validity_date"]),
            "switch_to_expired": row["switch_to_expired"],
            "payment_date": to_millis(row["payment_date"]),
            "last_updated_date": to_millis(row["last_updated_date"]),
            "inserted_date": to_millis(row["inserted_date"]),
            "service_type": row["service_type"]
        },
        "op": "c",
        "ts_ms": ts_ms,
        "ts_us": ts_us,
        "ts_ns": ts_ns
    }
    
    logging.debug(f"🐛 transform_payment_position - transform_payment_position - massage [{json.dumps(pp)}]")
    return pp

def transform_payment_option(row):
    ts_ms, ts_us, ts_ns = current_timestamps()
    po = {
        "after": {
            "id": row["id"],
            "amount": row["amount"],
            "description": row["description"],
            "fee": row["fee"],
            "iuv": row["iuv"],
            "status": row["status"],
            "province": row["province"],
            "type": row["type"],
            "payment_position_id": row["payment_position_id"],
            "due_date": to_millis(row["due_date"]),
            "receipt_id": row["receipt_id"],
            "inserted_date": to_millis(row["inserted_date"]),
            "is_partial_payment": row["is_partial_payment"],
            "organization_fiscal_code": row["organization_fiscal_code"],
            "payment_date": to_millis(row["payment_date"]),
            "payment_method": row["payment_method"],
            "psp_company": row["psp_company"],
            "retention_date": to_millis(row["retention_date"]),
            "notification_fee": row["notification_fee"],
            "fiscal_code": row["fiscal_code"],
            "postal_code": row["postal_code"]
        },
        "op": "c",
        "ts_ms": ts_ms,
        "ts_us": ts_us,
        "ts_ns": ts_ns
    }
    logging.debug(f"🐛 transform_payment_option - transform_payment_option - massage [{json.dumps(po)}]")
    return po


def transform_transfer(row):
    ts_ms, ts_us, ts_ns = current_timestamps()
    t = {
        "after": {
            "id": row["id"],
            "amount": row["amount"],
            "category": row["category"],
            "iuv": row["iuv"],
            "status": row["status"],
            "transfer_id": row["transfer_id"],
            "inserted_date": to_millis(row["inserted_date"]),
            "organization_fiscal_code": row["organization_fiscal_code"],
            "payment_option_id": row["payment_option_id"]
        },
        "op": "c",
        "ts_ms": ts_ms,
        "ts_us": ts_us,
        "ts_ns": ts_ns
    }
    logging.debug(f"🐛 transform_transfer - transform_transfer - massage [{json.dumps(t)}]")
    return t

def send_batch(producer, batch):
    eb = producer.create_batch()
    for event in batch:
        eb.add(EventData(json.dumps(event)))
    producer.send_batch(eb)
    

def chunked(iterable, size):
    """Yield successive chunks from iterable of a given size."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

def send_all_batches(batch_pp, batch_po, batch_tr, chunk_size=50):
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            logging.info(f"ℹ️ send_all_batches - Attempt {attempt}: sending events to Event Hub topics...")
            with create_event_hub_producer(PAYMENT_POSITION_OUTPUT_EVENTHUB_CONN_STRING, TOPIC_PAYMENT_POSITION) as prod_pp, \
                 create_event_hub_producer(PAYMENT_OPTION_OUTPUT_EVENTHUB_CONN_STRING, TOPIC_PAYMENT_OPTION) as prod_po, \
                 create_event_hub_producer(TRANSFER_OUTPUT_EVENTHUB_CONN_STRING, TOPIC_TRANSFER) as prod_tr:

                for chunk in chunked(batch_pp, chunk_size):
                    send_batch(prod_pp, chunk)
                for chunk in chunked(batch_po, chunk_size):
                    send_batch(prod_po, chunk)
                for chunk in chunked(batch_tr, chunk_size):
                    send_batch(prod_tr, chunk)

            logging.info("ℹ️ send_all_batches - All events sent successfully.")
            return
        except Exception as e:
            logging.warning(f"⚠️ send_all_batches - Attempt {attempt} failed: {e}")
            if attempt == RETRY_LIMIT:
                logging.error("❌ send_all_batches - All retry attempts failed. Aborting batch.")
                raise
            
            
def generate_report(data):
    print("generate_report - creating json report")
    today = datetime.now().strftime("%Y-%m-%d")
    report = {
        "text": "GPD - Data Lake Recovery Report",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "📊 Report recovery posizioni debitorie su Data Lake"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"📅 *Intervallo recuperato:* {data["start_date"]} - {data["end_date"]}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"⏱️ *Durata:* {data["duration"]}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟢 *Totale payment_position:* {data["payment_position"]}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟡 *Totale payment_position:* {data["payment_option"]}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🔵 *Totale payment_position:* {data["transfer"]}"}}
        ]
    }
    
    # write report to file
    with open("report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    
    print("generate_report - json report created")
    
    
def main(start_date, end_date):
    
    start_time = time.time()
    
    logging.info("ℹ️ main - Starting keyset-paginated batch processing from %s to %s", start_date, end_date)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_session(autocommit=True)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    last_inserted_date = start_date
    last_id = 0
    inserted_pp = 0
    inserted_po = 0
    inserted_t = 0
    while True:
        logging.info(f"ℹ️ main - Fetching payment_position, last_inserted_date: {last_inserted_date}, id: {last_id}") 
        
        pp_query = f"""
            SELECT 
                id,
                iupd,
                province,
                status,
                type,
                fiscal_code,
                postal_code,
                max_due_date::text,
                min_due_date::text,
                organization_fiscal_code,
                company_name,
                publish_date::text,
                validity_date::text,
                switch_to_expired,
                payment_date::text,
                last_updated_date::text,
                inserted_date::text,
                service_type
            FROM apd.apd.payment_position pp
            WHERE 
                (pp.inserted_date, pp.id) > ('{last_inserted_date}', {last_id})
                AND pp.inserted_date < '{end_date}'
            ORDER BY pp.inserted_date, pp.id
            LIMIT {BATCH_SIZE};
        """
        logging.debug(f"🐛 main - payment_position query: {pp_query}")
        
        for attempt in range(1, RETRY_LIMIT + 1):
            try:
                cur.execute(pp_query)
                pp_records = cur.fetchall()
            except Exception as e:
                logging.warning(f"⚠️ main - Attempt {attempt} to query payment_position failed: {e}")
                if attempt == RETRY_LIMIT:
                    logging.error("❌ main - All retry attempts to query payment_position failed. Aborting batch.")
                    raise
                
        if not pp_records:
            logging.info("ℹ️ main - No moere payment position to elaborate for current chunk, skip forward")
            break

        # getting last_inserted_date and last_id for next iteration
        last_inserted_date = pp_records[-1]["inserted_date"]
        last_id = pp_records[-1]["id"]

        # extracting the payment position ids
        pp_ids = tuple(r["id"] for r in pp_records)
        
        # executing query on payment_option
        po_query = f"""
            SELECT 
                id,
                amount,
                description,
                fee,
                iuv,
                status,
                province,
                type,
                payment_position_id,
                due_date::text,
                receipt_id,
                inserted_date::text,
                is_partial_payment,
                organization_fiscal_code,
                payment_date::text,
                payment_method,
                psp_company,
                retention_date::text,
                notification_fee,
                fiscal_code,
                postal_code
            FROM apd.apd.payment_option
            WHERE payment_position_id IN %s;
        """
        
        for attempt in range(1, RETRY_LIMIT + 1):
            try:
                cur.execute(po_query, (pp_ids,))
                po_records = cur.fetchall()
            except Exception as e:
                logging.warning(f"⚠️ main - Attempt {attempt} to query payment_option failed: {e}")
                if attempt == RETRY_LIMIT:
                    logging.error("❌ main - All retry attempts to query payment_option failed. Aborting batch.")
                    raise
        
        # extracting payment option ids    
        po_ids = tuple(r["id"] for r in po_records)
                
        # query the transfer table
        tr_query = f"""
            SELECT 
                id,
                amount,
                category,
                iuv,
                status,
                transfer_id,
                inserted_date::text,
                organization_fiscal_code,
                payment_option_id
            FROM apd.apd.transfer
            WHERE payment_option_id IN %s;        
        """

        if po_ids:
            for attempt in range(1, RETRY_LIMIT +1):
                try:
                    cur.execute(tr_query, (po_ids,))
                    tr_records = cur.fetchall()
                except Exception as e:
                    logging.warning(f"⚠️ main - Attempt {attempt} to query transfer failed: {e}")
                    if attempt == RETRY_LIMIT:
                        logging.error("❌ main - All retry attempts to query transfer failed. Aborting batch.")
                        raise
        else:
            logging.warning(f"⚠️ main - no payment option found for the current chunk")
            tr_records = []

        # creating batch messages to send to evh
        batch_pp = [transform_payment_position(r) for r in pp_records]
        batch_po = [transform_payment_option(r) for r in po_records]
        batch_tr = [transform_transfer(r) for r in tr_records]
        logging.info(f"ℹ️ main - Message batch sizes: payment_position: [{len(batch_pp)}] payment_option: [{len(batch_po)}] transfer: [{len(batch_tr)}]")

        # send messages to evh
        send_all_batches(batch_pp, batch_po, batch_tr)

        # update counters
        inserted_pp += len(batch_pp)
        inserted_po += len(batch_po)
        inserted_t += len(batch_tr)
    
    # closing db connection    
    cur.close()
    conn.close()
    
    logging.info("ℹ️ main - Keyset-paginated batch processing completed.")
    logging.info(f"ℹ️ main - Recovery report: payment_position[{inserted_pp}] payment_option[{inserted_po}] transfer[{inserted_t}]")
    
    # calculating elapsed
    elapsed = timedelta(seconds=round(time.time() - start_time))
    print(f"main - Execution time: {str(elapsed)}")
    
    report_data = {
        "start_date": start_date,
        "end_date": end_date,
        "payment_position": inserted_pp,
        "payment_option": inserted_po,
        "transfer": inserted_po,
        "duration": elapsed
    }
    generate_report(report_data)

def validate_iso8601_format(date_str):
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"
    if not re.match(pattern, date_str):
        raise ValueError(f"validate_iso8601_format - Invalid datetime format for '{date_str}'. Use YYYY-MM-DDTHH:MM:SS")
    
# Execution
if __name__ == "__main__":
    # parsing args
    parser = argparse.ArgumentParser(description="Send events from PostgreSQL to Azure Event Hub.")
    parser.add_argument("--start_date", required=True, help="Start datetime in ISO format (e.g. 2025-04-01T00:00:00)")
    parser.add_argument("--end_date", required=True, help="End datetime in ISO format (e.g. 2025-04-01T01:00:00)")
    args = parser.parse_args()
    
    validate_iso8601_format(args.start_date)
    validate_iso8601_format(args.end_date)

    # Pass as string, unchanged
    main(args.start_date, args.end_date)
