import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import time
from sqlalchemy import create_engine
import os
import json
from azure.data.tables import TableServiceClient, UpdateMode
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

# === Generate SAS url to access blob container files ===
def generate_sas_url(blob_name, container_name, account_name, account_key, expiry_minutes=60):
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=expiry_minutes)
    )
    return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d")

# === CONFIGURATIONS ===
# Postegres
apd_engine = create_engine(os.getenv("PG_APD_CONNECTION_STRING"))
nodo_engine = create_engine(os.getenv("PG_CFG_CONNECTION_STRING"))

# Storage Account
account_name = os.getenv("SA_ACCOUNT_NAME")
account_key = os.getenv("SA_ACCOUNT_KEY")
table_name = os.getenv("SA_BLOB_CONTAINER_NAME")

# === Date range management ===
start_str = os.getenv("START_DATE")
end_str = os.getenv("END_DATE")

if not start_str or not end_str or start_str.strip().lower() == 'yesterday' or end_str.strip().lower() == 'yesterday':
    base_day = datetime.today() - timedelta(days=1)
    start_date = base_day.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    print(f"✅ No valid date range provided, defaulting to yesterday: {start_date.date()}")
else:
    try:
        start_date = parse_date(start_str.strip()).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = parse_date(end_str.strip()).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    except ValueError as e:
        print(f"⚠️ Invalid date format: {e}. Defaulting to yesterday.")
        base_day = datetime.today() - timedelta(days=1)
        start_date = base_day.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)

print(f"📅 Execution from: {start_date} to: {end_date}")

# Main dataflow initialization
df = pd.DataFrame(columns=[
    'report_date','broker_id', 'broker_name', 'station_id', 'organization_fiscal_code', 'segregation_code', 'total'
])

# === Get data from APD ===
print(f"✅ Getting data from APD DB")
with apd_engine.connect() as apd_connection:
    current_day = start_date
    while current_day < end_date:
        base_day = current_day

        intervals = [
            (base_day.replace(hour=0, minute=0, second=0), base_day.replace(hour=6, minute=0, second=0)),
            (base_day.replace(hour=6, minute=0, second=0), base_day.replace(hour=12, minute=0, second=0)),
            (base_day.replace(hour=12, minute=0, second=0), base_day.replace(hour=18, minute=0, second=0)),
            (base_day.replace(hour=18, minute=0, second=0), base_day + timedelta(days=1))
        ]

        for from_dt, to_dt in intervals:
            query = f"""
            SELECT 
                po.organization_fiscal_code,
                SUBSTRING(po.iuv, 1, 2) AS segregation_code,
                COUNT(*) AS total
            FROM apd.payment_option po
            JOIN apd.payment_position pp ON po.payment_position_id = pp.id
            WHERE pp.service_type = 'ACA'
                AND pp.inserted_date >= '{from_dt.strftime('%Y-%m-%d %H:%M:%S')}'
                AND pp.inserted_date <  '{to_dt.strftime('%Y-%m-%d %H:%M:%S')}'
            GROUP BY po.organization_fiscal_code, segregation_code
            ORDER BY po.organization_fiscal_code, segregation_code
            """

            retries = 3
            success = False
            for attempt in range(1, retries + 1):
                try:
                    print(f"✅ Executing query on APD for range: {from_dt} - {to_dt}")
                    partial_df = pd.read_sql(query, apd_connection)
                    success = True
                    break
                except Exception as e:
                    print(f"⚠️ Attempt {attempt} failed due to error: {e}")
                    if attempt < retries:
                        wait = 2 ** attempt
                        print(f"⏳ Retry in {wait} seconds...")
                        time.sleep(wait)
                        apd_connection.close()
                        apd_connection = apd_engine.connect()
                    else:
                        print("❌ No more retry attempt. Raise exception")
                        raise e

            if success:
                partial_df['broker_id'] = None
                partial_df['station_id'] = None
                df = pd.concat([df, partial_df], ignore_index=True)

        current_day += timedelta(days=1)


# === Getting data from CFG ===
print(f"✅ Getting broker data from CFG DB")
with nodo_engine.connect() as nodo_connection:
    enrich_query = """
        SELECT 
            ip.id_intermediario_pa AS broker_id,
            ip.codice_intermediario as broker_name,
            s.id_stazione AS station_id,
            p.id_dominio AS organization_fiscal_code,
            LPAD(CAST(psp.segregazione AS TEXT), 2, '0') AS segregation_code
        FROM nodo.cfg.intermediari_pa ip
        INNER JOIN nodo.cfg.stazioni s ON s.fk_intermediario_pa = ip.obj_id  
        INNER JOIN nodo.cfg.pa_stazione_pa psp ON psp.fk_stazione = s.obj_id 
        INNER JOIN nodo.cfg.pa p ON p.obj_id = psp.fk_pa
        WHERE psp.segregazione IS NOT NULL

    """
    cfg_df = pd.read_sql(enrich_query, nodo_connection)

# Merge apd and cfg dataframes
df = df.drop(columns=['broker_id', 'broker_name', 'station_id'], errors='ignore')
df = df.merge(
    cfg_df,
    on=['organization_fiscal_code', 'segregation_code'],
    how='left'
)

missing = df[df['broker_id'].isnull()]
print(f"✅ Record not enriched: {len(missing)}")

# add report_date to dataframe
df["report_date"] = datetime.today()

# remove record with 'RF' segregation code
initial_len = len(df)
df = df[df["segregation_code"] != "RF"]
removed = initial_len - len(df)
print(f"🧹 Removed {removed} record equal to 'RF'")

# Getting data from the table (if exist)
existing_df = pd.DataFrame()
connection_string = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"
table_service = TableServiceClient.from_connection_string(conn_str=connection_string)
table_client = table_service.get_table_client(table_name)

try:
    entities = table_client.list_entities()
    existing_df = pd.DataFrame([dict(e) for e in entities])

    print(f"📥 Loaded {len(existing_df)} existing record from Table Storage.")
except Exception as e:
    print(f"⚠️ Table does not exist: {e}")

# Filtering expected columns
expected_cols = [
    "broker_id", "station_id", "segregation_code", "total",
    "report_date", "broker_name", "organization_fiscal_code"
]
for col in expected_cols:
    if col not in existing_df.columns:
        existing_df[col] = None

# Cast to expected type
existing_df["total"] = pd.to_numeric(existing_df["total"], errors="coerce").fillna(0).astype("int64")
df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0).astype("int64")

# Concat new and existing record
merged_df = pd.concat([existing_df, df], ignore_index=True)

# Merge results
merged_df = merged_df.groupby(
    ["broker_id", "station_id", "organization_fiscal_code", "segregation_code"],
    as_index=False
).agg({
    "total": "sum",
    "broker_name": "first",
    #"organization_fiscal_code": "first",
    "report_date": "max"  # aggiorna alla data più recente
})

print(f"✅ Existing and new dataframe merged")

# Build the table keys
merged_df["PartitionKey"] = merged_df["broker_id"].astype(str)
merged_df["RowKey"] = merged_df["station_id"].astype(str) + "|" + df["organization_fiscal_code"].astype(str) + "|" + df["segregation_code"].astype(str)

# Convert date format for iso compatibility
merged_df["report_date"] = pd.to_datetime(merged_df["report_date"], errors="coerce")
merged_df["report_date"] = merged_df["report_date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"✅ Data ready to be uploaded: {len(merged_df)} record")

# Create the table if does not exists
try:
    table_client.create_table()
    print("✅ Table storage created")
except Exception:
    print("⚠️ Table Storage already exists, proceed to upsert")

# === Upsert dei dati
print(f"🔄 Writing {len(merged_df)} record on Table Storage...")
for _, row in merged_df.iterrows():
    try:
        entity = {
            "PartitionKey": row["PartitionKey"],
            "RowKey": row["RowKey"],
            "broker_name": row["broker_name"],
            "organization_fiscal_code": row["organization_fiscal_code"],
            "segregation_code": row["segregation_code"],
            "total": int(row["total"]),
            "report_date": row["report_date"]
        }

        # Upsert = Insert or Merge
        table_client.upsert_entity(mode=UpdateMode.MERGE, entity=entity)
    except Exception as e:
        print(f"❌ Error while processing entity {row['PartitionKey']} - {row['RowKey']}: {e}")

print("✅ Record stored on Table Storage")

# === Report Management ===
csv_path = "broker_report.csv"
chart_path = "top_broker_piechart.png"

# set data for chart
chart_df = merged_df.groupby(
    ["broker_id", "broker_name"],
    as_index=False
).agg({
    "total": "sum"
})
chart_df = chart_df.sort_values(by='total', ascending=False).head(10)

# print chart
plt.figure(figsize=(8, 8))
plt.pie(
    chart_df['total'],
    labels=chart_df['broker_id'] + " - " + chart_df['broker_name'],
    autopct='%1.1f%%',
    startangle=140
)
plt.title("Top 10 Broker ID per numero posizioni debitorie ACA")
plt.axis('equal')
plt.tight_layout()
plt.show()
plt.savefig(chart_path)

# save data to csv format
merged_df.to_csv(csv_path, index=False)

# upload files to blob ocontainer
container_name = "gpdreportcontainer"
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client(container_name)

# if blob container not exists ti will be created
try:
    container_client.create_container()
    print(f"📦 Blob container '{container_name}' created")
except Exception as e:
    if "ContainerAlreadyExists" in str(e):
        print(f"✅ Container '{container_name}' already exists")
    else:
        print(f"❌ Error while creating blob container: {e}")
        raise
    
# Upload CSV
with open(csv_path, "rb") as data:
    container_client.upload_blob(
        name=csv_path,
        data=data,
        overwrite=True,
        content_settings=ContentSettings(content_type="text/csv")
    )

# Upload PNG
with open(chart_path, "rb") as data:
    container_client.upload_blob(
        name=chart_path,
        data=data,
        overwrite=True,
        content_settings=ContentSettings(content_type="image/png")
    )

print(f"✅ Files '{csv_path}' and '{chart_path}' uploaded to blob storage")

print(f"✅ Creating SAS URL to download the files")
csv_url = generate_sas_url(
    blob_name=csv_path,
    container_name=container_name,
    account_name=account_name,
    account_key=account_key,
    expiry_minutes=60 
)

chart_url = generate_sas_url(
    blob_name=chart_path,
    container_name=container_name,
    account_name=account_name,
    account_key=account_key,
    expiry_minutes=60
)
print(f"🔗 CSV URL: {csv_url}")
print(f"🔗 Chart URL: {chart_url}")

# generate slack message payload
top10_text = "\n".join([
    f"{i+1}. `{row['broker_id']}` - *{row['broker_name']}*: {row['total']:,} ACA"
    for i, row in chart_df.reset_index(drop=True).iterrows()
])


slack_payload = {
    "text": "📊 *GPD Broker Report aggiornato!*",
    "attachments": [
        {
            "fallback": "Grafico dei top broker",
            "title": "Download CSV",
            "title_link": csv_url,
            "text": "Scarica il report aggiornato in formato CSV.",
            "image_url": chart_url,
            "fields": [
                {
                    "title": "Top 10 Broker",
                    "value": top10_text,
                    "short": False
                }
            ]
        }
    ]
}

with open("payload.json", "w") as f:
    json.dump(slack_payload, f, indent=2)
    
print("✅ Process successfully terminated!")