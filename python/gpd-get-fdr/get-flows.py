import requests
import base64
import os
import csv
import sys
import xml.etree.ElementTree as ET
from azure.storage.blob import BlobServiceClient
import re
from requests import Response
from azure.data.tables import TableServiceClient, TableEntity
from datetime import datetime, timedelta


FR_NEW_CONN_SUBKEY_PRD: str = os.environ.get("FR_NEW_CONN_SUBKEY_PRD")
FR_NEW_CONN_SUBKEY_UAT: str = os.environ.get("FR_NEW_CONN_SUBKEY_UAT")
FR_SA_CONN_STRING_UAT: str = os.environ.get("FR_SA_CONN_STRING_UAT")
FR_SA_CONN_STRING_PRD: str = os.environ.get("FR_SA_CONN_STRING_PRD")
FR_CSV_NAME: str = os.environ.get("FR_CSV_NAME")
FR_ENV: str = os.environ.get("FR_ENV")
FR_DATE: str = os.environ.get("FR_DATE")
FR_BASE_DIR: str = os.environ.get("GITHUB_WORKSPACE")

headers_chiedi_flusso_prod = {
    'Ocp-Apim-Subscription-Key': FR_NEW_CONN_SUBKEY_PRD,
    'SOAPAction': 'nodoChiediFlussoRendicontazione',
    'X-Request-Id': 'pippo',
    'Content-Type': 'application/xml'
}

headers_chiedi_flusso_uat = {
    'Ocp-Apim-Subscription-Key': FR_NEW_CONN_SUBKEY_UAT,
    'SOAPAction': 'nodoChiediFlussoRendicontazione',
    'X-Request-Id': 'pippo',
    'Content-Type': 'application/xml'
}

headers_chiedi_elenco_flussi_prod = {
    'Ocp-Apim-Subscription-Key': FR_NEW_CONN_SUBKEY_PRD,
    'SOAPAction': 'nodoChiediElencoFlussiRendicontazione',
    'X-Request-Id': 'pippo',
    'Content-Type': 'application/xml'
}

headers_chiedi_elenco_flussi_uat = {
    'Ocp-Apim-Subscription-Key': FR_NEW_CONN_SUBKEY_UAT,
    'SOAPAction': 'nodoChiediElencoFlussiRendicontazione',
    'X-Request-Id': 'pippo',
    'Content-Type': 'application/xml'
}


def get_reporting_list(domain_id: str, broker_id, broker_station_id, password, date):

    try:
        body = f'''<?xml version="1.0" encoding="utf-8"?>
                    <Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">
                        <Body>
                            <nodoChiediElencoFlussiRendicontazione xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://ws.pagamenti.telematici.gov/">
                                <identificativoIntermediarioPA xmlns="">{broker_id}</identificativoIntermediarioPA>
                                <identificativoStazioneIntermediarioPA xmlns="">{broker_station_id}</identificativoStazioneIntermediarioPA>
                                <password xmlns=""></password>
                                <identificativoDominio xmlns="">{domain_id}</identificativoDominio>
                            </nodoChiediElencoFlussiRendicontazione>
                        </Body>
                    </Envelope>
                '''
                
        h = headers_chiedi_elenco_flussi_prod if FR_ENV == "prod" else headers_chiedi_elenco_flussi_uat
        environment = ".uat." if FR_ENV == "uat" else "."
        url = f'https://api{environment}platform.pagopa.it/nodo-auth/nodo-per-pa/v1'

        response: Response = requests.post(url, headers=h, data=body)
        response.raise_for_status()
        
        flows = []
        if response.status_code == 200:
            flows = xml_to_json(response.text)
        else:
            print(f"[{domain_id}] there was an error while getting the flow list, http status code [{response.status_code}]")
            sys.exit(response.status_code)
        
        if date is not None:
            filtered_data = [item for item in flows if item["flowDate"].startswith(date)]
            return filtered_data
        
        return flows
        
    except requests.exceptions.HTTPError as err:
        print(f"[{domain_id}] HTTP Error: {err}")
        sys.exit(response.status_code)
        

def xml_to_json(xml_data):
    # Parse the XML data
    xml_data_no_ns = re.sub(r'\sxmlns="[^"]+"', '', xml_data, count=1)
    root = ET.fromstring(xml_data_no_ns)
    
    # Extract the relevant elements from the XML
    flussi = []
    id_rendicontazione_elements = root.findall('.//idRendicontazione')
    for rendicontazione in id_rendicontazione_elements:
        flow_id = rendicontazione.find('identificativoFlusso').text
        flow_date = rendicontazione.find('dataOraFlusso').text
        
        flussi.append({
            "flowId": flow_id,
            "flowDate": flow_date
        })
    
    return flussi

def insert_row(partition_key, row_key, flow_date):

    connection_string = FR_SA_CONN_STRING_PRD
    table_name = "pagopapflowsatable"
    if FR_ENV != "prod":
        connection_string = FR_SA_CONN_STRING_UAT
        table_name = "pagopauflowsatable"

    table_service_client = TableServiceClient.from_connection_string(conn_str=connection_string)
    table_client = table_service_client.get_table_client(table_name)

    # Format the current timestamp in the required format
    current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Define the entity (row) to insert
    entity = TableEntity()
    entity["PartitionKey"] = partition_key
    entity["RowKey"] = row_key
    entity["FlowDate"] = flow_date
    entity["Timestamp"] = current_timestamp

    # Insert the entity into the table
    table_client.upsert_entity(entity=entity)
    print(f"[{partition_key}] Row inserted successfully.")

def get_report(domain_id, flow_id, broker_id, broker_station_id, password):
    
    body = f'''<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">
                <Body>
                    <nodoChiediFlussoRendicontazione xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://ws.pagamenti.telematici.gov/">
                    <identificativoIntermediarioPA xmlns="">{broker_id}</identificativoIntermediarioPA>
                    <identificativoStazioneIntermediarioPA xmlns="">{broker_station_id}</identificativoStazioneIntermediarioPA>
                    <password xmlns="">{password}</password>
                    <identificativoDominio xmlns="">{domain_id}</identificativoDominio>
                    <identificativoFlusso xmlns="">{flow_id}</identificativoFlusso>
                    </nodoChiediFlussoRendicontazione>
                </Body>
            </Envelope>'''

    h = headers_chiedi_flusso_prod if FR_ENV == "prod" else headers_chiedi_flusso_uat
    environment = ".uat." if FR_ENV == "uat" else "."
    url = f'https://api{environment}platform.pagopa.it/nodo-auth/nodo-per-pa/v1'
    response: Response = requests.post(url, headers=h, data=body)
    return response.text  


def get_flows_form_list(csv_name, date):
     # load the dictionary with the EC configurations
    #file_path = "/python/gpd-get-fdr/config/" + csv_name
    #file_path = os.path.join(os.getenv("GITHUB_WORKSPACE", ""), "/python/gpd-get-fdr/config/" + csv_name)
    #file_path = "/home/runner/work/pagopa-qa/pagopa-qa/python/gpd-get-fdr/config/" + csv_name
    file_path = FR_BASE_DIR + "/pagopa-qa/python/gpd-get-fdr/config/" + csv_name
    print(f"loading csv file [{file_path}]")
    data_dict = {}
    with open(file_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        # next(reader, None)  # skip the headers
        for row in reader:
            data_dict[row['id_dominio']] = {
                'broker_id': row['broker_id'],
                'broker_station_id': row['broker_station_id']
            }

    # iterate over the dictionary
    for domain_id, values in data_dict.items():
        get_flows(domain_id, values['broker_id'], values['broker_station_id'], '', date)
    
def get_flows(domain_id, broker_id, broker_station_id, password, date):

    flow_ids_data = get_reporting_list(domain_id, broker_id, broker_station_id, password, date)
    
    # for each flowId upload the relative xml file to storage account
    for flow_data in flow_ids_data:
        flow_id = flow_data['flowId']
        flow_date = flow_data['flowDate']

        response_api2 = get_report(domain_id, flow_id, broker_id, broker_station_id, password)
        
        # extract the rendicontazione xml file
        start_tag = "<xmlRendicontazione>"
        end_tag = "</xmlRendicontazione>"
        start_idx = response_api2.find(start_tag) + len(start_tag)
        end_idx = response_api2.find(end_tag)
        
        if start_idx != -1 and end_idx != -1:
            # add the entry in the list table
            insert_row(domain_id, flow_id, flow_date)
            # add the xml report to blob storage
            encoded_xml = response_api2[start_idx:end_idx]
            decode_and_upload_xml(encoded_xml, flow_date, domain_id, flow_id)
        else:
            print(f"[{domain_id}] no flow found in the response for flow_id [{flow_id}] and flowDate [{flow_date}]")

def decode_and_upload_xml(encoded_data, flow_date, domain_id, flow_id):
    
    container_name = "pagopapflowsaflowscontainer"
    connection_string = FR_SA_CONN_STRING_PRD
    
    if FR_ENV != "prod":
        container_name = "pagopauflowsaflowscontainer"
        connection_string = FR_SA_CONN_STRING_UAT
    
    try:
        decoded_data = base64.b64decode(encoded_data)
        filename = f"{flow_date}##{domain_id}##{flow_id}.xml"
        
        # Write file to SA
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(filename)
        inserted = True
        try:
            blob_client.upload_blob(decoded_data)
        except Exception as exalready:
            print(f"[{domain_id}] file [{container_name}/{filename}] aready exists")
            inserted = False
                    
        if inserted:    
            print(f"[{domain_id}] file [{filename}] loaded")
        
    except Exception as ex:
        print(f"Error while loading file: {ex}")


def get_date(delta: int):
    yesterday = datetime.now() - timedelta(days=delta)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    return yesterday_str

def main():
    global FR_DATE
    if FR_DATE == "all":
        FR_DATE = None
    elif FR_DATE == "yesterday":
        FR_DATE = get_date(1)        

    print(f" loading flows for day [{FR_DATE}]")
    get_flows_form_list(FR_CSV_NAME, FR_DATE)

if __name__ == "__main__":
    main()