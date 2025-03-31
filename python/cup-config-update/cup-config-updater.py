import psycopg2
import requests
import csv
import os

# Database connection parameters
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
EC_CONFIG_TABLE_FILE = os.getenv("EC-CONFIG-TABLE")
STATISTICAL_CODES_FILE = os.getenv("STATISTICAL-CODES")

# Output CSV file
CSV_FILE = os.getcwd() + "/python/cup-config-update/output.csv"
STATISTICAL_CODES_PATH = os.getcwd() + "/python/cup-config-update/" + STATISTICAL_CODES_FILE
EC_CONFIG_TABLE_PATH = os.getcwd() + "/python/cup-config-update/" + EC_CONFIG_TABLE_FILE

# Dictionary to cache statistical codes
statistical_codes = {}

# Dictionary for ec config table
ec_config_table = {}

def load_statistical_codes():
    try:
        with open(STATISTICAL_CODES_PATH, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile, delimiter=';')
            next(reader)
            for row in reader:
                if len(row) > 19:
                    statistical_codes[row[19]] = row[4] 
    except FileNotFoundError:
        print("Statistical codes file not found.")
    
    print("load_statistical_codes - statistical code file loaded")

def load_ec_config_table():
    try:
        with open(EC_CONFIG_TABLE_PATH, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile, delimiter=';')
            next(reader)
            for row in reader:
                if len(row) >= 15:
                    #ec_config_table[row[1]] = [row[14], row[15]] 
                    ec_config_table[row[1]] = row 
    except FileNotFoundError:
        print("ec config table codes file not found.")    
    
    
def get_pa_id_istat(pa_id_catasto):
    return statistical_codes.get(pa_id_catasto, "")

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
        AND pspa.segregazione = '47';  
    """
    print(f"fetch_sql_data - executing query {query}")
    
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    cursor.execute(query)
    records = cursor.fetchall()
    cursor.close()
    conn.close()
    
    print(f"fetch_sql_data - query execution ok")
    return records

def fetch_api_data(ec_fiscal_code):
    
    api_url = INSTITUTIONS_API_URL.format(ec_fiscal_code=ec_fiscal_code)
    institution_resp = requests.get(api_url, headers=HEADERS)
    
    if institution_resp.status_code == 200:
        # read response body
        institutions_data = institution_resp.json()  
        institutions_list = institutions_data.get("institutions", [])
        
        # get institution id
        institution_id = institutions_list[0].get("id", "") if institutions_list else ""
        
        # get id catasto
        pa_id_catasto = institutions_list[0].get("originId", "") if institutions_list else ""
        pa_id_catasto = pa_id_catasto.split("_")[1].upper() if "_" in pa_id_catasto else pa_id_catasto.upper()
        if pa_id_catasto == "" or pa_id_catasto == "CL":
            pa_id_catasto = ec_config_table[ec_fiscal_code][6] if ec_fiscal_code in ec_config_table else ""
        if pa_id_catasto is None:
            pa_id_catasto = ""
        
        # get ec pec
        pa_pec_email = institutions_list[0].get("digitalAddress", "") if institutions_list else ""
        if pa_pec_email == "":
            pa_pec_email = ec_config_table[ec_fiscal_code][12] if ec_fiscal_code in ec_config_table else ""
        if pa_pec_email is None:
            pa_pec_email = ""
        
        # get ec id istat
        # pa_id_istat_list = institutions_list[0].get("geographicTaxonomies", []) if len(institutions_list) > 0 else []
        # pa_id_istat = pa_id_istat_list[0].get("code") if len(pa_id_istat_list) > 0 else ""
        pa_id_istat = institutions_list[0].get("istatCode") if len(institutions_list) > 0 else ""
        if pa_id_istat == 'ITA' or pa_id_istat == "":
            pa_id_istat = get_pa_id_istat(pa_id_catasto)
            if pa_id_istat == "":
                pa_id_istat = ec_config_table[ec_fiscal_code][10] if ec_fiscal_code in ec_config_table else ""
        if pa_id_istat is None:
            pa_id_istat = ""
        
        # get ec referent data 
        pa_referent_email, pa_referent_name = "", ""
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
        
        return pa_id_catasto, pa_id_istat, pa_pec_email, pa_referent_email, pa_referent_name

    else: # error occurred invoking SelfCare service
        print(f"fetch_api_data - error fetching values from selfcare api for {ec_fiscal_code}")
        print("fetch_api_data - trying to retrieve the entire row from ec config table")
        if ec_fiscal_code in ec_config_table:
            pa_id_catasto = ec_config_table[6] if ec_config_table[6] is not None else ""
            pa_pec_email = ec_config_table[12] if ec_config_table[12] is not None else ""
            pa_id_istat = ec_config_table[10] if ec_config_table[10] is not None else ""
            pa_referent_email = ec_config_table[14] if ec_config_table[14] is not None else ""
            pa_referent_name = ec_config_table[15] if ec_config_table[15] is not None else ""
            return pa_id_catasto, pa_id_istat, pa_pec_email, pa_referent_email, pa_referent_name
        else:    
            print("fetch_api_data - no way to retrieve data, neither from Selfcare, nor from previous ec config table")
            return "", "", "", "", ""

def generate_csv():
    load_statistical_codes()
    load_ec_config_table()
    records = fetch_sql_data()
    
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        header = [
            "PartitionKey", "RowKey", "CompanyName", "CompanyName@type", "Iban", "Iban@type", "PaIdCatasto", "PaIdCatasto@type", 
            "PaIdCbill", "PaIdCbill@type", "PaIdIstat", "PaIdIstat@type", "PaPecEmail", "PaPecEmail@type", "PaReferentEmail", "PaReferentEmail@type", 
            "PaReferentName", "PaReferentName@type"
        ]
        writer.writerow(header)
        
        for row in records:
            row_key, company_name, pa_id_cbill, iban, label = row
            pa_id_catasto, pa_id_istat, pa_pec_email, pa_referent_email, pa_referent_name = fetch_api_data(row_key)
            print(f"generate_csv - writing row for ec {row_key}")
            writer.writerow(["org", row_key, company_name, "String", iban, "String", pa_id_catasto, "String", pa_id_cbill, "String", pa_id_istat, "String", pa_pec_email, "String", pa_referent_email, "String", pa_referent_name, "String"])
    
    print(f"CSV file '{CSV_FILE}' generated successfully.")

# Run the script
generate_csv()
