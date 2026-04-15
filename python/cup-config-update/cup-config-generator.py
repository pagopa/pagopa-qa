import csv
import pandas as pd
from azure.data.tables import TableServiceClient
from datetime import datetime, timezone
import os
import psycopg2

# === CONFIG ===
DB_PARAMS = {
    "dbname": os.getenv("PG-DB-NAME"),
    "user": os.getenv("PG-USER-NAME"),
    "password": os.getenv("PG-USER-PASSWORD"),
    "host": os.getenv("PG-HOST"),
    "port": os.getenv("PG-PORT")
}
# API details
INSTITUTIONS_API_URL = os.getenv("API-INSTITUTION-URL")
USERS_API_URL = os.getenv("API-USERS-URL")
HEADERS = {"Ocp-Apim-Subscription-Key": os.getenv("API-KEY")}

# File configuration
IPA_FILE = os.getenv("IPA-FILE", "enti.xlsx")
REFERENT_DATA_FILE = os.getenv("REFERENT-DATA-FILE", "referent-data.csv")
IPA_FILE_PATH = os.getcwd() + "/python/cup-config-update/input/" + IPA_FILE
CSV_FILE_PATH = os.getcwd() + "/python/cup-config-update/output/pagopaucanoneunicosaecconfigtable.csv"
REFERENT_DATA_FILE_PATH = os.getcwd() + "/python/cup-config-update/input/" + REFERENT_DATA_FILE

def fetch_sql_data():
    query = """
    WITH IbanRanked AS (
        SELECT 
            im.fk_pa,
            i.obj_id AS iban_id,
            i.iban,
            ia.attribute_name,
            im.inserted_date,
            ROW_NUMBER() OVER (
                PARTITION BY im.fk_pa 
                ORDER BY im.inserted_date DESC
            ) AS rn
        FROM nodo.cfg.iban_master im
        INNER JOIN nodo.cfg.iban i ON im.fk_iban = i.obj_id 
        LEFT JOIN nodo.cfg.iban_attributes_master iam ON iam.fk_iban_master = im.obj_id
        LEFT JOIN nodo.cfg.iban_attributes ia ON ia.obj_id = iam.fk_iban_attribute
    )
    SELECT 
        p.ID_DOMINIO as RowKey,
        p.ragione_sociale as CompanyName,
        COALESCE(p.cbill, '') as PaIdCbill,
        COALESCE(iban1.iban, iban2.iban) AS Iban,
        COALESCE(iban1.attribute_name, iban2.attribute_name ) AS label
    FROM nodo.cfg.PA p
    INNER JOIN nodo.cfg.PA_STAZIONE_PA pspa ON pspa.FK_PA = p.OBJ_ID
    INNER JOIN nodo.cfg.STAZIONI s ON pspa.FK_STAZIONE = s.OBJ_ID
    INNER JOIN nodo.cfg.INTERMEDIARI_PA ip ON s.FK_INTERMEDIARIO_PA = ip.OBJ_ID 
    LEFT JOIN IbanRanked iban1 
        ON iban1.fk_pa = p.obj_id 
        AND iban1.attribute_name = '0201138TS'
    LEFT JOIN IbanRanked iban2 
        ON iban2.fk_pa = p.obj_id 
        AND iban2.rn = 1 
    WHERE 
        ip.ID_INTERMEDIARIO_PA = '15376371009'
        AND s.ID_STAZIONE = '15376371009_01'
        AND pspa.segregazione = '47'
        and p.enabled = 'Y';  
    """
    print(f"fetch_sql_data - executing query {query}")
    
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    cursor.execute(query)
    records = cursor.fetchall()
    cursor.close()
    conn.close()
    
    print(f"fetch_sql_data - query execution ok")
    
    # Map results to a dictionary for easier access
    data_map = {}
    
    for row in records:        
        row_key = row[0]
        
        # Populate the data map with the index fields
        data_map[row_key] = {
            "company_name": row[1],
            "cbill": row[2],
            "iban": row[3],
            "label": row[4]
        }
        
    return data_map

def write_to_csv(entities_list: list):
    
    header = [
        "PartitionKey", "RowKey", "CompanyName", "CompanyName@type", 
        "Iban", "Iban@type", "PaIdCatasto", "PaIdCatasto@type", 
        "PaIdCbill", "PaIdCbill@type", "PaIdIstat", "PaIdIstat@type", 
        "PaPecEmail", "PaPecEmail@type", "PaReferentEmail", "PaReferentEmail@type", 
        "PaReferentName", "PaReferentName@type"
    ]
    
    if entities_list:
        df_output = pd.DataFrame(entities_list)
        
        df_output = df_output[header]
        df_output.to_csv(CSV_FILE_PATH, index=False, sep=';', encoding='utf-8')
        
        print(f"File saved with {len(df_output)} rows.")
    else:
        print("No data to write to CSV.")


def main():
    
    # === LOAD IPA DATA ===
    print(f"Loading IPA data from: {IPA_FILE_PATH}")
    df = pd.read_excel(IPA_FILE_PATH, dtype=str)    

    # === FILTER BY CATEGORY ===
    # Only L5 = Province, L6 = Comuni
    print(f"Number of records before filtering: {len(df)}")
    # df = df[df["Codice_Categoria"].isin(["L5", "L6", "L45"])]
    df = df[df["Codice_Categoria"].isin(["L45"])]
    print(f"Number of records after filtering: {len(df)}")

    # === RENAME COLUMNS ===
    print("Renaming columns...")
    df = df.rename(columns={
        "Codice_fiscale_ente": "RowKey",
        "Codice_comune_ISTAT": "PaIdIstat",
        "Codice_catastale_comune": "PaIdCatasto",
        "Mail1": "PaPecEmail",
        "Denominazione_ente": "CompanyName"
    })

    # === CLEANING ===
    print("Cleaning data...")
    df = df.dropna(subset=["RowKey"])

    # Trim spaces
    print("Trimming spaces...")
    df["RowKey"] = df["RowKey"].str.strip()
    df["PaPecEmail"] = df["PaPecEmail"].str.strip()
    
    # === LOAD REFERENT DATA ===
    print("Loading Referent Data file...")
    referent_data_df = pd.read_csv(REFERENT_DATA_FILE_PATH, sep=';', dtype=str)
    referent_data_df.fillna("", inplace=True)
    referent_data_map = referent_data_df.set_index("ec_fiscal_code")[["referent_email", "referent_name"]].to_dict("index")

    # get current timestamp
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # === Iterate over DataFrame rows and create entities ===
    print("Fetching PA data from SQL...")
    pa_data = fetch_sql_data()
    
    inserted = 0
    entities_list = []
    for _, row in df.iterrows():
        referent = referent_data_map.get(row["RowKey"], {})
        pa_referent_email = referent.get("referent_email") or ""
        pa_referent_name = referent.get("referent_name") or ""
        iban_val = pa_data.get(row["RowKey"], {}).get("iban", "n.a.")
        cbill_val = pa_data.get(row["RowKey"], {}).get("cbill", "n.a.")
        
        entity = {
            "PartitionKey": "org",
            "RowKey": row["RowKey"],
            
            "CompanyName": row["CompanyName"],
            "CompanyName@type": "String",
            
            "Iban": iban_val,
            "Iban@type": "String",
            
            "PaIdCatasto": row["PaIdCatasto"],
            "PaIdCatasto@type": "String",
            
            "PaIdCbill": cbill_val,
            "PaIdCbill@type": "String",
            
            "PaIdIstat": row["PaIdIstat"],
            "PaIdIstat@type": "String",
            
            "PaPecEmail": row["PaPecEmail"],
            "PaPecEmail@type": "String",
            
            "PaReferentEmail": pa_referent_email,
            "PaReferentEmail@type": "String",
            
            "PaReferentName": pa_referent_name,
            "PaReferentName@type": "String"
        }
        
        entities_list.append(entity)
        inserted += 1
        
        if inserted % 100 == 0:
            print(f"{inserted} entities processed...")  

    print(f"Number of entity loaded: {inserted}")
    
    # === WRITE TO CSV ===
    write_to_csv(entities_list)

if __name__ == "__main__":
    main()
