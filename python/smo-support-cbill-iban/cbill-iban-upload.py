import sys
import requests

# Configurazione globale
CONFIG = {
    "uat": {
        "base_url": "https://api.uat.platform.pagopa.it",
        "subscription_key": "909d3363590745908189968449a41977"
    },
    "prod": {
        "base_url": "https://api.platform.pagopa.it",
        "subscription_key": "d4d8a9a924044e3f89dfe4ca0af05eeb"
    },
    "endpoints": {
        "cbill": "/apiconfig/auth/api/v1/creditorinstitutions/cbill?incremental=true",
        "iban": "/apiconfig/auth/api/v1/creditorinstitutions/ibans/csv"
    }
}

def upload_file(api_url, file_path, subscription_key):
    """
    Carica un file su un endpoint API e gestisce la risposta.

    Args:
        api_url (str): URL dell'API da chiamare.
        file_path (str): Percorso del file da caricare.
        subscription_key (str): Chiave di sottoscrizione per l'API.

    Returns:
        bool: True se l'upload ha avuto successo, False altrimenti.
    """
    try:
        # Legge il file in memoria
        with open(file_path, 'rb') as file_data:
            files = {'file': file_data}
            headers = {
                'Ocp-Apim-Subscription-Key': subscription_key
            }
            
            # Esegue la richiesta POST
            response = requests.post(api_url, headers=headers, files=files)
            
            # Controlla lo status code
            if response.status_code == 200:
                print("Upload riuscito!")
                return True
            else:
                print(f"Errore nella chiamata API. Status code: {response.status_code}")
                print("Messaggio di errore:", response.text)
                return False
    except FileNotFoundError:
        print("Errore: file non trovato.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Errore durante la chiamata API: {e}")
        return False


def main():
    if len(sys.argv) != 4:
        print("Uso corretto: python script.py <ambiente> <tipo> <file_path>")
        print("  <ambiente>: 'uat' o 'prod'")
        print("  <tipo>: 'cbill' o 'iban'")
        sys.exit(1)
    
    ambiente = sys.argv[1].lower()
    tipo = sys.argv[2].lower()
    file_path = sys.argv[3]

    # Verifica ambiente
    if ambiente not in CONFIG:
        print("Errore: ambiente sconosciuto. Usa 'uat' o 'prod'.")
        sys.exit(1)

    # Verifica tipo
    if tipo not in CONFIG["endpoints"]:
        print("Errore: tipo sconosciuto. Usa 'cbill' o 'iban'.")
        sys.exit(1)

    # Costruisce l'URL dell'API
    base_url = CONFIG[ambiente]["base_url"]
    endpoint = CONFIG["endpoints"][tipo]
    api_url = f"{base_url}{endpoint}"

    # Recupera la subscription key
    subscription_key = CONFIG[ambiente]["subscription_key"]

    # Carica il file
    upload_file(api_url, file_path, subscription_key)

if __name__ == "__main__":
    main()
