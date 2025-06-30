import json
import psycopg2
from datetime import datetime
import os
import time

# Configurazione della connessione al database
DB_CONFIG = {
    "dbname": os.getenv("PG_DB_NAME"),
    "user": os.getenv("PG_USER_NAME"),
    "password": os.getenv("PG_APD_PASSWORD"),
    "host": os.getenv("PG_HOST"),
    "port": os.getenv("PG_PORT")
}

# Query per ottenere i dati
QUERY = """
SELECT 
    COUNT(*) AS TOTAL,
    COUNT(CASE WHEN service_type = 'GPD' THEN 1 END) AS GPD,
    COUNT(CASE WHEN service_type = 'GPD' AND status in ('VALID', 'PARTIALLY_PAID') THEN 1 END) AS GPD_PAYABLE,
    COUNT(CASE WHEN service_type = 'WISP' THEN 1 END) AS WISP,
    COUNT(CASE WHEN iupd NOT LIKE 'ACA_%' AND service_type = 'ACA' THEN 1 END) AS gpd4aca,
    COUNT(CASE WHEN iupd NOT LIKE 'ACA_%' AND service_type = 'ACA' AND status in ('VALID', 'PARTIALLY_PAID') THEN 1 END) AS ACA_GPD4ACA_PAYABLE,
    COUNT(CASE WHEN iupd LIKE 'ACA_%' AND service_type = 'ACA' THEN 1 END) AS paCreatePosition,
    COUNT(CASE WHEN iupd LIKE 'ACA_%' AND service_type = 'ACA' AND status in ('VALID', 'PARTIALLY_PAID') THEN 1 END) AS ACA_GPD_CREATE_POSITION_PAYABLE
FROM apd.payment_position;
"""

def fetch_data():
    try:
        # db connection
        print("creating db connection")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("db connection created")
        
        # execute query
        retries = 1
        for attempt in range(1, retries + 1):
            try:                
                print(f"attempt {attempt} to executing query {QUERY}")
                cursor.execute(QUERY)
                result = cursor.fetchone()
                print("query executed")
                break
            except Exception as e:
                print(f"⚠️ Attempt {attempt} failed due to error: {e}")
                conn.close()
                if attempt < retries:
                    wait = 2 ** attempt
                    print(f"⏳ Retry in {wait} seconds...")
                    time.sleep(wait)
                else:
                    print("❌ No more retry attempt. Raise exception")
                    raise e
                    
        # close connection
        cursor.close()
        conn.close()
        
        result = {
            "TOTAL": result[0],
            "GPD": result[1],
            "GPD_PAYABLE": result[2],
            "WISP": result[3],
            "GPD4ACA": result[4],
            "GPD4ACA_PAYABLE": result[5],
            "PA_CREATE_POSITION": result[6],
            "PA_CREATE_POSITION_PAYABLE": result[7]
        }

        print(f"report data {result}")
        return result
    
    except Exception as e:
        print(f"Error during database access: {e}")
        return None

def generate_report(data):
    print("creating json report")
    today = datetime.now().strftime("%Y-%m-%d")
    report = {
        "text": "Report numeriche GPD",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "📊 Statistiche Posizioni Debitorie GPD"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"📅 *Data Rilevamento:* {today}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟢 *Totale PD:* {data['TOTAL']:,}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🔵 *PD GPD:* {data['GPD']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🔵 *PD GPD PAGABILI:* {data['GPD_PAYABLE']:,}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟣 *PD GPD4ACA:* {data['GPD4ACA']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟣 *PD GPD4ACA PAGABILI:* {data['GPD4ACA_PAYABLE']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟣 *PD paCreatePosition:* {data['PA_CREATE_POSITION']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟣 *PD paCreatePosition: PAGABILI* {data['PA_CREATE_POSITION_PAYABLE']:,}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"🟡 *PD WISP:* {data['WISP']:,}"}}
        ]
    }
    print("json report created")
    
    # write report to file
    with open("report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    
    print(f"report susscessfully generated: {report}")

if __name__ == "__main__":
    data = fetch_data()
    if data:
        generate_report(data)
