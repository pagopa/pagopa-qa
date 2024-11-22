from azure.cosmos import CosmosClient
import csv

# Configurazione Cosmos DB
url = "https://pagopa-p-weu-bizevents-ds-cosmos-account.documents.azure.com:443"
key = "*******************************"
database_name = "db"
container_name = "biz-events"

# Inizializza il client
client = CosmosClient(url, credential=key)
database = client.get_database_client(database_name)
container = database.get_container_client(container_name)

# Esegui la query
query = """
SELECT 
    c.paymentInfo.paymentToken,
    c.debtorPosition.noticeNumber
FROM c
WHERE 
    c.paymentInfo.paymentDateTime >= "2024-11-07T10:00:00" 
    AND c.paymentInfo.paymentDateTime < "2024-11-07T11:59:59"
    AND c.debtorPosition.modelType = "2"
"""

results = container.query_items(query=query, enable_cross_partition_query=True)

# Salva in CSV
output_file = 'risultati_query.csv'
with open(output_file, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(["paymentToken", "noticeNumber"])  # Intestazioni del CSV
    for result in results:
        writer.writerow([result["paymentToken"], result["noticeNumber"]])

print(f"Esportazione completata in '{output_file}'")
