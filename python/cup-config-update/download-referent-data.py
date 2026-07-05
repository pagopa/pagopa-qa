import requests
import os
import csv
import pandas as pd

# API details
INSTITUTIONS_API_URL = os.getenv("API-INSTITUTION-URL")
USERS_API_URL = os.getenv("API-USERS-URL")
HEADERS = {"Ocp-Apim-Subscription-Key": os.getenv("API-KEY")}

# File configuration
IPA_FILE = os.getenv("IPA-FILE", "enti.xlsx")
IPA_FILE_PATH = os.getcwd() + "/python/cup-config-update/input/" + IPA_FILE

# EC Config table file configuration
EC_CONFIG_TABLE_FILE = "bck_20260329_pagopapcanoneunicosaecconfigtable.csv"
EC_CONFIG_TABLE_PATH = os.getcwd() + "/python/cup-config-update/input/" + EC_CONFIG_TABLE_FILE

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

def get_pa_referent_data (ec_fiscal_code, ec_config_table):
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
        if pa_referent_email is None or pa_referent_email == "":
            pa_referent_email = ""
        if pa_referent_name is None or pa_referent_name == "":
            pa_referent_name = ""
    else:
        print(f"Failed to fetch institution data for fiscal code {ec_fiscal_code}. Status code: {institution_resp.status_code}")
        
    return pa_referent_email, pa_referent_name


def write_referent_data_to_csv(df: pd.DataFrame):
    output_path = os.getcwd() + "/python/cup-config-update/input/referent-data.csv"
    df.to_csv(output_path, index=False, sep=';', encoding='utf-8')
    print(f"File salvato in {output_path} con {len(df)} righe.")


def main():
    # === LOAD EC CONFIG TABLE ===
    print("Loading EC config table...")
    ec_config_table = load_ec_config_table()
    
    # === LOAD IPA DATA ===
    print(f"Loading IPA data from: {IPA_FILE_PATH}")
    df = pd.read_excel(IPA_FILE_PATH, dtype=str)
    
    # === FILTER BY CATEGORY ===
    # Only L5 = Province, L6 = Comuni
    print(f"Number of records before filtering: {len(df)}")
    df = df[df["Codice_Categoria"].isin(["L5", "L6"])]
    df = df.dropna(subset=["Codice_fiscale_ente"])
    print(f"Number of records after filtering: {len(df)}")
    
    inserted = 0
    not_found = 0
    df_referent_data = pd.DataFrame(columns=["ec_fiscal_code", "referent_name", "referent_email"])
    for _, row in df.iterrows():
        pa_referent_email, pa_referent_name = get_pa_referent_data(row["Codice_fiscale_ente"], ec_config_table)
        
        if pa_referent_email == "" and pa_referent_name == "":
            not_found += 1
            print(f"Referent data not found for fiscal code {row['Codice_fiscale_ente']}. Setting empty values.")
        
        df_referent_data.loc[len(df_referent_data)] = {
            "ec_fiscal_code": row["Codice_fiscale_ente"],
            "referent_name": pa_referent_name,
            "referent_email": pa_referent_email
        }
        
        inserted += 1    
        if inserted % 100 == 0:
            print(f"{inserted} entities processed...")

    print(f"Total entities not found: {not_found}")
    write_referent_data_to_csv(df_referent_data)


if __name__ == "__main__":
    main()
