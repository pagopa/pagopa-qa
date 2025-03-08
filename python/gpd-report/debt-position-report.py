import json
import psycopg2
from datetime import datetime
import os

# Configurazione della connessione al database
DB_CONFIG = {
    "dbname": "apd",
    "user": os.getenv("PG_USER_NAME"),
    "password": os.getenv("PG_APD_PASSWORD"),
    "host": "gpd-db.p.internal.postgresql.pagopa.it",
    "port": "6432"
}

# Query per ottenere i dati
QUERY = """
SELECT 
    COUNT(*) AS TOTAL,
    COUNT(CASE WHEN service_type = 'GPD' THEN 1 END) AS GPD,
    COUNT(CASE WHEN service_type = 'WISP' THEN 1 END) AS WISP,
    COUNT(CASE WHEN iupd NOT LIKE 'ACA_%' AND service_type = 'ACA' THEN 1 END) AS gpd4aca,
    COUNT(CASE WHEN iupd LIKE 'ACA_%' AND service_type = 'ACA' THEN 1 END) AS paCreatePosition
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
        print(f"executing query {QUERY}")
        cursor.execute(QUERY)
        result = cursor.fetchone()
        print("query executed")
        
        # close connection
        cursor.close()
        conn.close()
        
        result = {
            "TOTAL": result[0],
            "GPD": result[1],
            "WISP": result[2],
            "gpd4aca": result[3],
            "paCreatePosition": result[4]
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
            {"type": "section", "text": {"type": "mrkdwn", "text": f":calendar: *Data Rilevamento:* {today}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":large_green_circle: *Totale PD:* {data['TOTAL']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":large_blue_circle: *PD GPD:* {data['GPD']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":large_yellow_circle: *PD WISP:* {data['WISP']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":large_violet_circle: *PD GPD4ACA:* {data['gpd4aca']:,}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":large_gray_circle: *PD paCreatePosition:* {data['paCreatePosition']:,}"}}
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
