import requests
import json
import os

# Configurazioni
OPSGENIE_URL = 'https://api.opsgenie.com/v1/incidents'
BETTERSTACK_URL = 'https://uptime.betterstack.com/api/v2/incidents'
BETTERSTACK_URL_REPORTS = 'https://uptime.betterstack.com/api/v2/status-pages/198298/status-reports'

opsgenie_key = os.getenv('OPSGENIE_KEY')
betterstack_key = os.getenv('BETTER_STACK_TOKEN')

# Headers per le chiamate API
opsgenie_headers = {
    "Authorization": f"GenieKey {opsgenie_key}",
    "Content-Type": "application/json"
}

betterstack_headers = {
    "Authorization": f"Bearer {betterstack_key}",
    "Content-Type": "application/json"
}


def get_opsgenie_incidents():
    """Recupera la lista degli incidenti da Opsgenie con il tag 'toStatusPage'."""
    print("Recupero incidenti da Opsgenie...")
    response = requests.get(OPSGENIE_URL, headers=opsgenie_headers)
    response.raise_for_status()
    incidents = response.json().get("data", [])
    print(f"Incidenti trovati su Opsgenie: {len(incidents)}")

    # Filtra gli incidenti con il tag "toStatusPage"
    filtered_incidents = [
        incident for incident in incidents if "toStatusPage" in incident.get("tags", [])
    ]
    print(f"Incidenti filtrati con tag 'toStatusPage': {len(filtered_incidents)}")
    return filtered_incidents

def get_betterstack_incidents():
    """Recupera la lista degli incidenti da Betterstack."""
    print("Recupero incidenti da Better Uptime...")
    response = requests.get(BETTERSTACK_URL, headers=betterstack_headers)
    response.raise_for_status()
    incidents = response.json().get("data", [])
    print(f"Incidenti trovati su Better Uptime: {len(incidents)}")
    return {incident["id"]: incident for incident in incidents if incident.get("id")}

def get_betterstack_reports():
    """Recupera la lista dei reports da Betterstack."""
    print("Recupero reports da Better Uptime...")
    response = requests.get(BETTERSTACK_URL_REPORTS, headers=betterstack_headers)
    response.raise_for_status()
    reports = response.json().get("data", [])
    print(f"Reports trovati su Better Uptime: {len(reports)}")

  # Filtra i report con "report_type" uguale a "manual"
    filtered_reports = [
    report for report in reports if report.get("attributes", {}).get("report_type") == "manual"
    ]
    print(f"Reports filtrati con report_type 'manual': {len(filtered_reports)}")
    return filtered_reports

def get_betterstack_report_updates(report):
    
    #"""Recupera i report updates del report di Betterstack."""
    #print("Recupero report updates da Better Uptime...")
    #response = requests.get(BETTERSTACK_URL_REPORTS+report["id"]+"/status-updates", headers=betterstack_headers)
    #response.raise_for_status()
    #report_updates = response.json().get("data", [])
    #print(f"Report updates trovati su Better Uptime: {len(report_updates)}")
    
    # Restituisce una lista degli ID di tutti i report updates trovati
    #return [update.get("id") for update in report_updates]


    """Recupera gli aggiornamenti del report di Better Uptime specificato per ID."""
    print("Recupero report updates da Better Uptime...")
    response = requests.get(f"{BETTERSTACK_URL_REPORTS}/{report}/status-updates", headers=betterstack_headers)
    response.raise_for_status()
    report_updates = response.json().get("data", [])
    print(f"Report updates trovati su Better Uptime: {len(report_updates)}")
    return report_updates


def create_betterstack_report(incident):
    """Crea un report su Better Uptime."""
    title = f"Incident [ID: {incident['id']}] - {incident['message']}"
    payload = {
        "title": title,
        "message": incident["message"],
        "report_type": "manual",
        "affected_resources": [{"status_page_resource_id": "8489182", "status": "downtime"}]
    }

    response = requests.post(BETTERSTACK_URL_REPORTS, headers=betterstack_headers, json=payload)

    response.raise_for_status()
    
    betterstack_id = response.json().get("id")
    print(f"Incidente-Report creato su Better Uptime con ID: {betterstack_id}")
    return betterstack_id


def create_betterstack_incident(incident):
    """Crea un incidente su Better Uptime."""
    title = f"Incident [ID: {incident['id']}] - {incident['message']}"
    payload = {
        "name": title,
        "summary":incident["message"],
        "description":incident["description"],
        "requester_email": "cristiano.sticca@pagopa.it"
    }

    response = requests.post(BETTERSTACK_URL, headers=betterstack_headers, json=payload)

    response.raise_for_status()
    
    betterstack_id = response.json().get("id")
    print(f"Incidente creato su Better Uptime con ID: {betterstack_id}")
    return betterstack_id

def update_betterstack_incident(betterstack_id):
    """Risolve l'incidente su Better Uptime se lo stato di Opsgenie è 'resolved' o 'closed'."""
    
    # URL per risolvere l'incidente su Better Uptime
    resolve_url = f"{BETTERSTACK_URL}/{betterstack_id}/resolve"
        
    print(f"Risolvendo l'incidente su Better Uptime con ID: {betterstack_id}")
    response = requests.post(resolve_url, headers=betterstack_headers)
    response.raise_for_status()  # Verifica eventuali errori nella risposta
        
    print(f"Incidente con ID {betterstack_id} risolto correttamente su Better Uptime.")


def update_betterstack_report_update(betterstack_report_id,betterstack_report_update_id):
    """Risolve l'incidente/report su Better Uptime se lo stato di Opsgenie è 'resolved' o 'closed'."""
    
    # URL per risolvere l'incidente su Better Uptime
    resolve_url = BETTERSTACK_URL_REPORTS+"/"+betterstack_report_id+"/status-updates/"+betterstack_report_update_id
        
    payload = {
         "affected_resources": [{"status_page_resource_id": "8489182", "status": "resolved"}]
    }

    print(f"Risolvendo l'incidente\report su Better Uptime con ID: {betterstack_report_id}")
    response = requests.patch(resolve_url, headers=betterstack_headers,json=payload )
    response.raise_for_status()  # Verifica eventuali errori nella risposta
        
    print(f"Incidente con ID {betterstack_report_id} risolto correttamente su Better Uptime.")


def find_betterstack_incident_by_title(opsgenie_id, betterstack_incidents):
    """Trova un incidente su Better Uptime basato sul titolo che contiene l'ID Opsgenie."""
    for incident in betterstack_incidents.values():
        if f"ID: {opsgenie_id}" in incident["attributes"]["name"]:
            return incident["id"], incident["attributes"]["status"]
    return None, None

def find_betterstack_report_by_title(opsgenie_id, betterstack_reports):
    """Trova un report su Better Uptime basato sul titolo che contiene l'ID Opsgenie."""
    for report in betterstack_reports:
        if f"ID: {opsgenie_id}" in report["attributes"]["title"]:
            return report["id"], report["attributes"]["aggregate_state"]
    return None, None

def sync_incidents():
    """Sincronizza gli incidenti tra Opsgenie e Better Uptime."""
    print("Inizio sincronizzazione incidenti...")
    opsgenie_incidents = get_opsgenie_incidents()
    betterstack_incidents = get_betterstack_incidents()

    for incident in opsgenie_incidents:
        opsgenie_id = incident["id"]
        opsgenie_status = incident["status"]

        # Trova l'incidente su Better Uptime usando il titolo che include l'ID Opsgenie
        betterstack_id, betterstack_status = find_betterstack_incident_by_title(opsgenie_id, betterstack_incidents)

        if betterstack_id is None:
            # Crea un nuovo incidente su Better Uptime
            print(f"Creazione dell'incidente {opsgenie_id} su Better Uptime.")
            create_betterstack_incident(incident)

        elif betterstack_status != opsgenie_status:
            # Aggiorna lo stato dell'incidente se necessario

             # Se lo stato dell'incidente su Better Uptime è già 'resolved', non fare nulla
            if betterstack_status == "Resolved":
                print(f"L'incidente con ID {betterstack_id} su Better Uptime è già risolto. Nessuna azione necessaria.")
                continue  # Passa all'incidente successivo

            # Altrimenti, se lo stato in Opsgenie è 'resolved', aggiorna Better Uptime per risolvere l'incidente
            if opsgenie_status == "resolved":

                
                update_betterstack_report_update(betterstack_id)
                print(f"Aggiornamento dello stato dell'incidente {opsgenie_id} su Better Uptime.")
        
    print("Sincronizzazione completata.")
   

def sync_report_incidents():
    """Sincronizza gli incidenti/reports tra Opsgenie e Better Uptime."""
    print("Inizio sincronizzazione incidenti/reports...")
    opsgenie_incidents = get_opsgenie_incidents()
    betterstack_reports = get_betterstack_reports()

    for incident in opsgenie_incidents:
        opsgenie_id = incident["id"]
        opsgenie_status = incident["status"]

        # Trova l'incidente su Better Uptime usando il titolo che include l'ID Opsgenie
        betterstack_report_id, betterstack_status = find_betterstack_report_by_title(opsgenie_id, betterstack_reports)

        if betterstack_report_id is None:
            # Crea un nuovo incidente su Better Uptime
            print(f"Creazione dell'incidente {opsgenie_id} su Better Uptime.")
            create_betterstack_report(incident)

        elif betterstack_status != opsgenie_status:
            # Aggiorna lo stato dell'incidente se necessario

             # Se lo stato dell'incidente su Better Uptime è già 'resolved', non fare nulla
            if betterstack_status == "Resolved":
                print(f"L'incidente con ID {betterstack_report_id} su Better Uptime è già risolto. Nessuna azione necessaria.")
                continue  # Passa all'incidente successivo

            # Altrimenti, se lo stato in Opsgenie è 'resolved', aggiorna Better Uptime per risolvere l'incidente
            if opsgenie_status == "resolved":
                betterstack_report_update_ids = get_betterstack_report_updates(betterstack_report_id)
                for betterstack_report_update_id in betterstack_report_update_ids:
                    report_udpate_i = betterstack_report_update_id["id"]
                    update_betterstack_report_update(betterstack_report_id,report_udpate_i)
                    print(f"Aggiornamento dello stato dell'incidente {opsgenie_id} su Better Uptime.")
        
    print("Sincronizzazione completata.")


if __name__ == "__main__":
    #sync_incidents()
    sync_report_incidents()

    
