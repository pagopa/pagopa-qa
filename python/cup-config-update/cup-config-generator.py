import csv
import pandas as pd
from azure.data.tables import TableServiceClient
from datetime import datetime, timezone
import requests
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
EC_CONFIG_TABLE_FILE = os.getenv("EC-CONFIG-TABLE")
IPA_FILE = os.getenv("IPA-FILE", "enti.xlsx")
CSV_FILE_PATH = os.getcwd() + "/python/cup-config-update/output/pagopaucanoneunicosaecconfigtable.csv"
EC_CONFIG_TABLE_PATH = os.getcwd() + "/python/cup-config-update/input/" + EC_CONFIG_TABLE_FILE
IPA_FILE_PATH = os.getcwd() + "/python/cup-config-update/input/" + IPA_FILE

# Table storage
STORAGE_CONN_STRING = "DefaultEndpointsProtocol=..."
STAGING_TABLE = "organizations_staging"

# Dictionary for ec config table
ec_config_table = {}

def get_pa_referent_data (ec_fiscal_code):
    api_url = INSTITUTIONS_API_URL.format(ec_fiscal_code=ec_fiscal_code)
    institution_resp = requests.get(api_url, headers=HEADERS)
    pa_referent_email, pa_referent_name = "", ""

    if institution_resp.status_code == 200:
        # read response body
        institutions_data = institution_resp.json()
        institutions_list = institutions_data.get("institutions", [])

        # get institution id
        institution_id = institutions_list[0].get("id", "") if institutions_list else ""
        if institution_id != "":
            api_url = USERS_API_URL.format(institution_id=institution_id)
            users_resp = requests.get(api_url, headers=HEADERS)
            if users_resp.status_code == 200:
                users_data = users_resp.json()
                pa_referent_email = users_data[0].get("email", "") if users_data else ""
                pa_referent_name = f"{users_data[0].get('name', '')} {users_data[0].get('surname', '')}" if users_data else ""

        if pa_referent_email == "" or pa_referent_name == "":
            print("trying to retrieve referent email and referent name from ec config table")
            pa_referent_email = ec_config_table[ec_fiscal_code][14] if ec_fiscal_code in ec_config_table else ""
            pa_referent_name = ec_config_table[ec_fiscal_code][16] if ec_fiscal_code in ec_config_table else ""
        if pa_referent_email is None:
            pa_referent_email = ""
        if pa_referent_name is None:
            pa_referent_name = ""
    return pa_referent_email, pa_referent_name

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
    
    # TRASFORMAZIONE DEI DATI
    # Creo un dizionario vuoto
    data_map = {}
    
    for row in records:
        # Mappo le colonne in base all'ordine della SELECT:
        # 0: RowKey (ID_DOMINIO)
        # 1: CompanyName
        # 2: PaIdCbill
        # 3: Iban
        # 4: Label
        
        row_key = row[0]
        
        # Popolo il dizionario usando row_key come chiave
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
        
        # [IMPORTANTE] Forzo l'ordine delle colonne per farlo coincidere con il tuo header
        # Questo scarta eventuali colonne extra e ordina quelle presenti
        df_output = df_output[header]
        
        # Scrittura su file (senza indice)
        df_output.to_csv(CSV_FILE_PATH, index=False, sep=';', encoding='utf-8')
        
        print(f"File salvato con {len(df_output)} righe.")
    else:
        print("Nessun dato da scrivere.")
        
def write_to_table_storage(entities_list: list):
    service = TableServiceClient.from_connection_string(STORAGE_CONN_STRING)
    table = service.get_table_client(STAGING_TABLE)
    
    for entity in entities_list:
        table.upsert_entity(entity=entity)
    
    print(f"Entità caricate in STAGING: {len(entities_list)}")

def load_ec_config_table():
    ec_config_table = {}
    try:
        with open(EC_CONFIG_TABLE_PATH, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile, delimiter=';')
            next(reader)
            for row in reader:
                if len(row) >= 15:
                    #ec_config_table[row[1]] = [row[14], row[15]] 
                    ec_config_table[row[1]] = row
        return ec_config_table
    except FileNotFoundError:
        print("ec config table codes file not found.")    

def main():
    
    # === LOAD IPA DATA ===
    print(f"Loading IPA data from: {IPA_FILE_PATH}")
    df = pd.read_excel(IPA_FILE_PATH, dtype=str)

    # === LOAD EC CONFIG TABLE ===
    print("Loading EC config table...")
    ec_config_table = load_ec_config_table()

    # === FILTER BY CATEGORY ===
    # Only L5 = Province, L6 = Comuni
    print(f"Number of records before filtering: {len(df)}")
    df = df[df["Codice_Categoria"].isin(["L5", "L6"])]
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

    # === CONNECT TO TABLE STORAGE ===
    # service = TableServiceClient.from_connection_string(STORAGE_CONN_STRING)
    # table = service.get_table_client(STAGING_TABLE)

    # get current timestamp
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # === Iterate over DataFrame rows and create entities ===
    print("Fetching PA data from SQL...")
    pa_data = fetch_sql_data()
    
    inserted = 0
    entities_list = []
    for _, row in df.iterrows():
        pa_referent_email, pa_referent_name = get_pa_referent_data(row["RowKey"])
        iban_val = pa_data.get(row["RowKey"], {}).get("iban", "")
        cbill_val = pa_data.get(row["RowKey"], {}).get("cbill", "")
        
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

    print(f"Number of entity loaded: {inserted}")
    
    # === WRITE TO CSV ===
    write_to_csv(entities_list)

if __name__ == "__main__":
    main()
