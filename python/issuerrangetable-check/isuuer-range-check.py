from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError
import os

# Configurazione dell'account Azure Storage
connection_string = os.getenv("AZ_CONNECTION_STRING")
table_name = "pagopapweuafmsaissuerrangetable"

def check_overlapping_ranges():
    print(f"[check_overlapping_ranges] creating az table storage connection")
    table_service_client = TableServiceClient.from_connection_string(conn_str=connection_string)
    table_client = table_service_client.get_table_client(table_name)
    print(f"[check_overlapping_ranges] az table storage connection created")

    entities = table_client.query_entities("")
    print(f"[check_overlapping_ranges] query entity executed")

    records_by_abi = {}
    all_records = []

    
    print(f"[check_overlapping_ranges] grouping entity by abi code")
    for entity in entities:
        abi = entity["ABI"]
        low_range = int(entity["LOW_RANGE"])
        high_range = int(entity["HIGH_RANGE"])

        if abi not in records_by_abi:
            records_by_abi[abi] = []
        
        records_by_abi[abi].append({
            "PartitionKey": entity["PartitionKey"],
            "RowKey": entity["RowKey"],
            "LOW_RANGE": low_range,
            "HIGH_RANGE": high_range,
            "ABI": abi
        })

        all_records.append({
            "PartitionKey": entity["PartitionKey"],
            "RowKey": entity["RowKey"],
            "LOW_RANGE": low_range,
            "HIGH_RANGE": high_range,
            "ABI": abi
        })

    overlapping_records_same_abi = []
    overlapping_records_different_abi = []
    
    print(f"[check_overlapping_ranges] looking for overlaps with the same ABI code")
    for abi, records in records_by_abi.items():
        
        # sorting entities by LOW_RANGE
        records.sort(key=lambda x: x["LOW_RANGE"])

        for i in range(len(records) - 1):
            record_a = records[i]
            record_b = records[i + 1]

            # check if range overlaps
            if record_a["HIGH_RANGE"] >= record_b["LOW_RANGE"]:
                overlapping_records_same_abi.append((abi, record_a, record_b))

    print(f"[check_overlapping_ranges] looking for overlaps with different ABI codes")
    all_records.sort(key=lambda x: x["LOW_RANGE"])
    for i in range(len(all_records)):
        record_a = all_records[i]
        for j in range(i + 1, len(all_records)):
            record_b = all_records[j]

            if record_b["LOW_RANGE"] > record_a["HIGH_RANGE"]:
                break

            # check if range overlaps
            if (record_a["HIGH_RANGE"] >= record_b["LOW_RANGE"] and
                record_a["ABI"] != record_b["ABI"]):
                overlapping_records_different_abi.append((record_a, record_b))


    # print results
    if overlapping_records_same_abi:
        print(f"[check_overlapping_ranges] found [{overlapping_records_same_abi.__len__()}] overlaps with the same ABI:")
        for abi, record_a, record_b in overlapping_records_same_abi:
            print(f"Record A - ABI: {record_a['ABI']}, PartitionKey: {record_a['PartitionKey']}, RowKey: {record_a['RowKey']}, "
                  f"LOW_RANGE: {record_a['LOW_RANGE']}, HIGH_RANGE: {record_a['HIGH_RANGE']}")
            print(f"Record B - ABI: {record_a['ABI']}, PartitionKey: {record_b['PartitionKey']}, RowKey: {record_b['RowKey']}, "
                  f"LOW_RANGE: {record_b['LOW_RANGE']}, HIGH_RANGE: {record_b['HIGH_RANGE']}")
            print()

    if overlapping_records_different_abi:
        print(f"[check_overlapping_ranges] found [{overlapping_records_different_abi.__len__()}] overlaps with distinct ABI:")
        for record_a, record_b in overlapping_records_different_abi:
            print(f"Record A - ABI: {record_a['ABI']}, PartitionKey: {record_a['PartitionKey']}, RowKey: {record_a['RowKey']}, "
                  f"LOW_RANGE: {record_a['LOW_RANGE']}, HIGH_RANGE: {record_a['HIGH_RANGE']}")
            print(f"Record B - ABI: {record_b['ABI']}, PartitionKey: {record_b['PartitionKey']}, RowKey: {record_b['RowKey']}, "
                  f"LOW_RANGE: {record_b['LOW_RANGE']}, HIGH_RANGE: {record_b['HIGH_RANGE']}")
            print()

    if not overlapping_records_same_abi and not overlapping_records_different_abi:
        print("[check_overlapping_ranges] Nessuna sovrapposizione trovata.")

# Esegui la funzione
check_overlapping_ranges()
