import requests
import json
import os
from collections import defaultdict

# URL della tua API per le manutenzioni con parametri
api_url = 'https://api.platform.pagopa.it/backoffice/helpdesk/v1/station-maintenances?state=SCHEDULED_AND_IN_PROGRESS'
# Token BetterStack (sostituisci con il tuo)
betterstack_token = os.getenv('BETTERSTACK_TOKEN')
# Chiave di autenticazione per la tua API custom
subscription_key = os.getenv('PAGOPA_SUBSCRIPTION_KEY')
# Endpoint BetterStack per creare manutenzioni programmate
betterstack_url = 'https://uptime.betterstack.com/api/v2/status-pages/198298/status-reports'

# Chiave di autenticazione BO Ext per ottenere elenco PA sotto stazione
subscription_key_backoffice_ext_pa = os.getenv('PAGOPA_SUBSCRIPTION_KEY_GET_PA')

# Endpoint BetterStack per creare manutenzioni programmate
betterstack_url = 'https://uptime.betterstack.com/api/v2/status-pages/198298/status-reports'

# Headers per le chiamate API
betterstack_headers = {
    "Authorization": f"Bearer {betterstack_token}",
    "Content-Type": "application/json"
}

# Funzione per ottenere le manutenzioni esistenti su BetterStack
def get_existing_betterstack_maintenances():
   
    response = requests.get(betterstack_url, headers=betterstack_headers)
    if response.status_code == 200:
        return response.json()['data']
    else:
        print(f"Errore nel recuperare manutenzioni esistenti: {response.status_code}")
        return None

# Funzione per recuperare le manutenzioni programmate
def get_scheduled_maintenances():
    url = api_url
    headers = {
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
  
    return response.json()

# Funzione per recuperare le PA per un determinato broker
def get_pa_for_broker(broker_code):
    page = 0
    limit = 10
    base_url = f"https://api.platform.pagopa.it/backoffice/external/ec/v1/brokers/{broker_code}/creditor_institutions"
    
    headers = {
        'Ocp-Apim-Subscription-Key': subscription_key_backoffice_ext_pa
    }
    
    all_creditor_institutions = []

    while True:
        params = {'page': page, 'limit': limit}
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        creditor_institutions = data.get('creditorInstitutions', [])
        all_creditor_institutions.extend(creditor_institutions)

        total_pages = data.get('pageInfo', {}).get('totalPages', 1)
        if page >= total_pages - 1:
            break
        page += 1

    return all_creditor_institutions


def create_betterstack_maintenance(data):
    
    headers = {
        'Authorization': betterstack_token,
        'Content-Type': 'application/json'
    }
    
    response = requests.post(betterstack_url, headers=headers, data=json.dumps(data))
    if response.status_code == 201:
        print(f"Manutenzione creata con successo")
    else:
        print(f"Errore nella creazione: {response.status_code}, {response.text}")

# Funzione per verificare se una manutenzione esiste già su BetterStack
def is_maintenance_existing(new_maintenance, existing_maintenances):
    for maintenance in existing_maintenances:
        existing_title = maintenance['attributes']['title']
        existing_start = maintenance['attributes']['starts_at']
        existing_end = maintenance['attributes']['ends_at']
        
        # Confronta il titolo e la data/ora di inizio e fine
        if (existing_title == new_maintenance['title'] and
            existing_start == new_maintenance['starts_at'] and
            existing_end == new_maintenance['ends_at']):
            return True
    return False

def create_maintenance_description(broker_name, stations, pa_list):
    description = f"{broker_name} ha pianificato una manutenzione programmata nella fascia oraria indicata.\n\n"
    description += "Non sarà possibile effettuare pagamenti verso i seguenti Enti Creditori:\n"
    
    for pa_name, pa_tax in pa_list:  # Itera direttamente sugli elementi della tupla
        description += f"- {pa_name} - {pa_tax}\n"
    
    description += "\nDi seguito le stazioni impattate:\n"
    #print(f"Stazioni passate: {stations}")  # Stampa le stazioni per il debug
   
    for station in stations:
        #print(f"Stazione in formato finale: {station}")  # Verifica formato della stazione   
         # Sostituisci '_' con ' ' per BetterStack
        formatted_station = station.replace('_', ' ')
        description += f"- {formatted_station}\n"
    
    return description

def process_maintenance():
    maintenances = get_scheduled_maintenances()
    # Recupera tutte le manutenzioni esistenti su BetterStack
    existing_maintenances = get_existing_betterstack_maintenances()

    maintenance_groups = {}

    # Raggruppa le manutenzioni per broker_code e fascia oraria
    for maintenance in maintenances['station_maintenance_list']:
        key = (maintenance['broker_code'], maintenance['start_date_time'], maintenance['end_date_time'])
        if key not in maintenance_groups:
            maintenance_groups[key] = {
                "broker_code": maintenance['broker_code'],
                "start_date_time": maintenance['start_date_time'],
                "end_date_time": maintenance['end_date_time'],
                "stations": []
            }
        maintenance_groups[key]['stations'].append(maintenance['station_code'])

    for group in maintenance_groups.values():
        broker_code = group['broker_code']
        start_time = group['start_date_time']
        end_time = group['end_date_time']
        stations = group['stations']

        # Ottieni informazioni PA e nome broker per tutte le stazioni nel gruppo
         # Set per raccogliere PA uniche
        pa_set = set()
        broker_name = ""
        for station in stations:
            pa_data = get_pa_for_broker(broker_code)
            broker_name = pa_data['creditorInstitutions'][0]['brokerCompanyName']
            filtered_pa_list = [
                pa for pa in pa_data['creditorInstitutions']
                if pa['stationId'] in stations
            ]
             # Aggiungi le PA al set per evitare duplicati
            for pa in filtered_pa_list:
                pa_set.add((pa['companyName'], pa['taxCode']))

             # Converti il set in una lista ordinata
            unique_pa_list = sorted(pa_set)

        # Crea descrizione per il gruppo di manutenzioni
        description = create_maintenance_description(broker_name, stations, unique_pa_list)

        # Anteprima della manutenzione
        new_maintenance = {
            "report_type": "maintenance",
            "starts_at": start_time,
            "ends_at": end_time,
            #"title": f"{broker_name} - {broker_code} - Manutenzione Programmata",
            "title": f"{broker_name} - Manutenzione Programmata",
            "message": description
        }
        #print("Anteprima della manutenzione che verrà creata:")
        #print(data)

         # Verifica se la manutenzione esiste già
        if is_maintenance_existing(new_maintenance, existing_maintenances):
                print(f"Manutenzione già esistente")
                return
        
        response = requests.post(betterstack_url, headers=betterstack_headers, data=json.dumps(new_maintenance))
        if response.status_code == 201:
            print(f"Manutenzione aggregata creata con successo per il broker {broker_code}")
        else:
            print(f"Errore nella creazione della manutenzione aggregata: {response.status_code}, {response.text}")

# Esegui il programma
if __name__ == "__main__":
    try:
        process_maintenance()
    except requests.exceptions.RequestException as e:
        print(f"Si è verificato un errore durante l'esecuzione: {e}")
