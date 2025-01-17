import os
import pandas as pd
from datetime import datetime, timedelta
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from azure.kusto.data.helpers import dataframe_from_result_table

# Azure Data Explorer configuration
KUSTO_CLUSTER = "https://pagopapdataexplorer.westeurope.kusto.windows.net"
KUSTO_DATABASE = "re"

# Kusto query
KUSTO_QUERY = """
let start = "{start}";
let end = "{end}";
ReEvent
| where insertedTimestamp between (todatetime(start) .. todatetime(end))
| where psp == "BCITITMM"
| where tipoEvento == "pspNotifyPaymentV2"
| where sottoTipoEvento == "REQ"
| extend payloadDec = base64_decode_tostring(payload)
| extend payloadDec = replace_regex(replace_regex(payloadDec, '</.{{0,10}}?:','</'), '<.{{0,10}}?:','<')
| extend responseBody = parse_xml(payloadDec)
| extend fee = responseBody['Envelope']['Body']['pspNotifyPaymentV2']['fee']
| extend timestampOperation = responseBody['Envelope']['Body']['pspNotifyPaymentV2']['timestampOperation']
| extend amount = responseBody['Envelope']['Body']['pspNotifyPaymentV2']['totalAmount']
| extend mapEntry = responseBody['Envelope']['Body']['pspNotifyPaymentV2']['additionalPaymentInformations']['metadata']['mapEntry']
| mv-expand mapEntry
| extend methodKey = tostring(mapEntry['key'])
| extend method = tostring(mapEntry['value'])
| where methodKey == "tipoVersamento" and method == "CP"
| extend payments = responseBody['Envelope']['Body']['pspNotifyPaymentV2']['paymentList']['payment']
| extend iuv = tostring(payments['creditorReferenceId'])
| extend ec = tostring(payments['fiscalCodePA'])
| extend key = tostring(payments['metadata']['mapEntry']['key'])
| extend codConv = tostring(payments['metadata']['mapEntry']['value'])
| where key == "codiceConvenzione"
| project timestampOperation, ec, iuv, amount, fee, codConv, ccp
"""


OUTPUT_FILE = os.getcwd() + "/python/payments-with-agreement-report/output/report.csv"
FILTERED_OUTPUT_FILE = os.getcwd() + "/python/payments-with-agreement-report/output/report_filtered.csv"

# Authentication (remember az login --use-device)
KCSB = KustoConnectionStringBuilder.with_az_cli_authentication(KUSTO_CLUSTER)
client = KustoClient(KCSB)

def query_spr (ec, iuv, ccp, client, database):
    """
    Query the Kusto database for the given `ec` and `iuv` values and return the outcome.
    """
    query = f"""
    ReEvent
    | where sottoTipoEvento == "REQ"
    | where tipoEvento == "sendPaymentResult-v2"
    | where idDominio contains "{ec}"
    | where iuv == "{iuv}"
    | where ccp == "{ccp}"
    | extend payloadDec = base64_decode_tostring(payload)
    | extend payloadJson = parse_json(payloadDec)
    | extend outcome = payloadJson.outcome
    | project idDominio, iuv, payloadJson, outcome
    """
    try:
        response = client.execute(database, query)
        df = dataframe_from_result_table(response.primary_results[0])
        if not df.empty:
            return df.iloc[0]["outcome"]  # Return the first outcome
    except Exception as e:
        print(f"Error querying Kusto for ec={ec}, iuv={iuv}: {e}")
    return None

def filter_ko_payments (input_csv, output_csv, kusto_client, database):

    # Read the input CSV
    df = pd.read_csv(input_csv)

    # Filter rows based on Kusto query
    rows_to_keep = []
    for index, row in df.iterrows():
        ec = row["ec"]
        iuv = row["iuv"]
        ccp = row["ccp"]
        outcome = query_spr(ec, iuv, ccp, kusto_client, database)

        # Keep the row only if the outcome is not "KO"
        if outcome != "KO":
            rows_to_keep.append(row)
            print(f"Filtering - row added: {row["ec"]} - {row["iuv"]} - {row["fee"]} - {row["codConv"]}")
        else:
            print(f"Filtering - row discarded: {row}")

    # Create a new DataFrame with the filtered rows
    filtered_df = pd.DataFrame(rows_to_keep)

    # Save the filtered DataFrame to the output CSV
    filtered_df.to_csv(output_csv, index=False)
    
def execute_query(start_date: str, end_date: str):
    try:
        # Execute the query
        query = KUSTO_QUERY.format(start=start_date, end=end_date)
        response = client.execute(KUSTO_DATABASE, query)
        # Convert the response to a pandas DataFrame
        return dataframe_from_result_table(response.primary_results[0])
    except KustoServiceError as ex:
        print(f"An error occurred: {ex}")
        return pd.DataFrame()

def main(start_date: str, end_date: str, interval_hours: int):
    # Parse input dates
    start = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

    # Initialize the output file with headers
    with open(OUTPUT_FILE, "w") as f:
        f.write("timestampOperation,ec,iuv,amount,fee,codConv,ccp\n")

    # Loop over the date range in intervals of interval_hours hours
    current = start
    while current < end:
        interval_start = current.strftime("%Y-%m-%d %H:%M:%S")
        interval_end = (current + timedelta(hours=interval_hours)).strftime("%Y-%m-%d %H:%M:%S")

        if datetime.strptime(interval_end, "%Y-%m-%d %H:%M:%S") > end:
            interval_end = end.strftime("%Y-%m-%d %H:%M:%S")

        print(f"Querying data for: {interval_start} - {interval_end}")

        # Execute the query for the current interval
        df = execute_query(interval_start, interval_end)

        # Append results to the output report file
        if not df.empty:
            df.to_csv(OUTPUT_FILE, mode="a", header=False, index=False)

        # Move to the next interval
        current += timedelta(hours=interval_hours)
    
    filter_ko_payments(OUTPUT_FILE, FILTERED_OUTPUT_FILE, client, "re")
        
if __name__ == "__main__":
    main("2024-11-13 00:00:00", "2024-12-31 23:59:59", 6)
