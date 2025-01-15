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
| project timestampOperation, ec, iuv, amount, fee, codConv
"""


OUTPUT_FILE = os.getcwd() + "/python/payments-with-agreement-report/output/report.csv"

# Authentication (remember az login --use-device)
KCSB = KustoConnectionStringBuilder.with_az_cli_authentication(KUSTO_CLUSTER)
client = KustoClient(KCSB)

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
        f.write("timestampOperation,ec,iuv,amount,fee,codConv\n")

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
        
if __name__ == "__main__":
    main("2024-11-01 00:00:00", "2024-12-31 23:59:59", 6)
