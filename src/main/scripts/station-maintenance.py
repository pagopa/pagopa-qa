import requests
import json
import os

# URL della tua API per le manutenzioni con parametri
api_url = 'https://api.uat.platform.pagopa.it/backoffice/helpdesk/v1/station-maintenances?state=SCHEDULED_AND_IN_PROGRESS'
# Token BetterStack (sostituisci con il tuo)
betterstack_token = os.getenv('BETTERSTACK_TOKEN')
# Chiave di autenticazione per la tua API custom
subscription_key = os.getenv('PAGOPA_SUBSCRIPTION_KEY')
# Endpoint BetterStack per creare manutenzioni programmate
betterstack_url = 'https://uptime.betterstack.com/api/v2/status-pages/198298/status-reports'

# Headers per le chiamate API
betterstack_headers = {
    "Authorization": f"Bearer {betterstack_token}",
    "Content-Type": "application/json"
}

# Funzione per ottenere le manutenzioni dall'API
def get_maintenance_data():
    headers = {
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        return response.json()['station_maintenance_list']
    else:
        print(f"Errore nel recuperare dati: {response.status_code}")
        return None

# Funzione per ottenere le manutenzioni esistenti su BetterStack
def get_existing_betterstack_maintenances():
    
    response = requests.get(betterstack_url, headers=betterstack_headers)
    if response.status_code == 200:
        return response.json()['data']
    else:
        print(f"Errore nel recuperare manutenzioni esistenti: {response.status_code}")
        return None

# Funzione per verificare se una manutenzione esiste già su BetterStack
def check_existing_maintenance(maintenance, existing_maintenances):
    for existing in existing_maintenances:
        if (existing['attributes']['title'] == f"Manutenzione broker {maintenance['broker_code']} - stazione {maintenance['station_code']} " and
            existing['attributes']['starts_at'] == maintenance['start_date_time'] and
            existing['attributes']['ends_at'] == maintenance['end_date_time']):
            return True
    return False

# Funzione per creare una manutenzione su BetterStack
def create_betterstack_maintenance(maintenance):
    data = {
        'report_type': "maintenance", 
        'starts_at': maintenance['start_date_time'],
        'ends_at': maintenance['end_date_time'],
        'title':f"Manutenzione broker {maintenance['broker_code']} - stazione {maintenance['station_code']} ",
        'message': f"E' stata definita sul Backoffice pagoPA una manutenzione programmata dal broker {maintenance['broker_code']} per la stazione {maintenance['station_code']}. \n\n\n Per maggiori info sulle manutenzioni programmate si faccia riferimento a (https://developer.pagopa.it/pago-pa/guides/manuale-bo-ec/manuale-operativo-back-office-pagopa-ente-creditore/funzionalita/stazioni/esportazione-massiva-ec)"
    }
   
    response = requests.post(betterstack_url, headers=betterstack_headers, data=json.dumps(data))
    if response.status_code == 201:
        print(f"Manutenzione creata con successo: {maintenance['maintenance_id']}")
    else:
        print(f"Errore nella creazione: {response.status_code}, {response.text}")

# Funzione principale
def main():
    maintenances = get_maintenance_data()
    if maintenances:
        # Recupera tutte le manutenzioni esistenti su BetterStack
        existing_maintenances = get_existing_betterstack_maintenances()
        
        if existing_maintenances is None:
            print("Impossibile recuperare le manutenzioni esistenti. Interruzione del processo.")
            return
        
        for maintenance in maintenances:
            # Verifica se la manutenzione esiste già
            if not check_existing_maintenance(maintenance, existing_maintenances):
                create_betterstack_maintenance(maintenance)
            else:
                print(f"Manutenzione già esistente: {maintenance['maintenance_id']}")

# Esegui il programma
if __name__ == "__main__":
    main()
