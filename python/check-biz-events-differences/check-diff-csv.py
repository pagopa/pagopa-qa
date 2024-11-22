import csv
import os

def read_csv(file_path, token_key, notice_key):
    """Legge un file CSV e restituisce un dizionario con i dati."""
    try:
        with open(file_path, 'r') as file:
            reader = csv.DictReader(file)
            data = {row[token_key]: row[notice_key] for row in reader}
        print(f"Letto file {file_path} con {len(data)} righe.")
        return data
    except Exception as e:
        print(f"Errore durante la lettura del file {file_path}: {e}")
        return {}

def write_csv(file_path, data, headers):
    """Scrive un dizionario in un file CSV."""
    try:
        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            for token, notice in data.items():
                writer.writerow([token, notice])
        print(f"File scritto: {file_path}, righe: {len(data)}")
    except Exception as e:
        print(f"Errore durante la scrittura del file {file_path}: {e}")

def main():
    # File paths
    file1 = 'risultati_query.csv'  # Primo CSV (dal programma Python precedente)
    file2 = 'csv_db_nodo.csv'    # Secondo CSV (dal DB del Nodo)

    # Chiavi dei campi da confrontare
    token_key_file1 = 'paymentToken'
    notice_key_file1 = 'noticeNumber'
    token_key_file2 = 'PAYMENT_TOKEN'
    notice_key_file2 = 'NOTICE_ID'

    # Leggi i dati dai file
    print("Inizio lettura dei file...")
    data1 = read_csv(file1, token_key_file1, notice_key_file1)
    data2 = read_csv(file2, token_key_file2, notice_key_file2)

    if not data1 or not data2:
        print("Uno dei due file è vuoto o non è stato letto correttamente.")
        return

    # Confronta i dati
    print("Confronto dei dati in corso...")
    only_in_file1 = {k: v for k, v in data1.items() if k not in data2}
    only_in_file2 = {k: v for k, v in data2.items() if k not in data1}

    print(f"Righe solo in file1: {len(only_in_file1)}")
    print(f"Righe solo in file2: {len(only_in_file2)}")

    # Scrivi i risultati in output
    output_dir = 'output_differenze'
    os.makedirs(output_dir, exist_ok=True)

    write_csv(os.path.join(output_dir, 'only_in_file1.csv'), only_in_file1, ['paymentToken', 'noticeNumber'])
    write_csv(os.path.join(output_dir, 'only_in_file2.csv'), only_in_file2, ['PAYMENT_TOKEN', 'NOTICE_ID'])

    print("Confronto completato. I risultati sono stati salvati nella cartella 'output_differenze'.")

if __name__ == "__main__":
    main()
