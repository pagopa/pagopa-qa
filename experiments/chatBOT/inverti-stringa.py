from PIL import Image, ImageDraw, ImageFont
import imageio
import os

# --- Dati ---
testo_originale = "supercalifragilistichespiralidoso"

# Definisci i token come li vuoi tu.
# NOTA: L'esempio fornito ("su", "per", ...) non copre perfettamente
#       l'intera parola. Adatta questa lista se necessario.
tokens = ["su", "per", "cali", "fragili", "sti", "che", "spirali", "doso"]
tokens_invertiti = tokens[::-1]
testo_tokenizzato = " ".join(tokens)
testo_token_invertito = " ".join(tokens_invertiti)
# testo_ricomposto_token = "".join(tokens_invertiti) # Puoi aggiungere questo frame se vuoi

lettere = list(testo_originale)
lettere_invertite = lettere[::-1]
testo_lettere = " ".join(lettere)
testo_lettere_invertite = " ".join(lettere_invertite)
testo_invertito_completo = "".join(lettere_invertite)

# --- Parametri GIF ---
width, height = 1000, 150 # Dimensioni immagine (larghezza, altezza)
bg_color = "white"
text_color = "black"
font_size = 40

# !!! IMPORTANTE: IMPOSTA UN FONT VALIDO PER IL TUO SISTEMA !!!
# Lascia None per usare il font di default (spesso piccolo/brutto)
# Esempi per MacOS: "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"
# Esempi per Windows: "C:/Windows/Fonts/arial.ttf"
# Esempi per Linux: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font_path = "/System/Library/Fonts/Supplemental/AmericanTypewriter.ttc"

output_gif = "string_animation_variable_duration.gif" # Nome del file GIF finale
frames_dir = "frames_temp" # Cartella temporanea per i frame

# --- Caricamento Font con gestione errori ---
try:
    if font_path and os.path.exists(font_path): # Controlla se il path è specificato ed esiste
        font = ImageFont.truetype(font_path, font_size)
        print(f"Using font: {font_path}")
    else:
        if font_path: # Path specificato ma non trovato
             print(f"Attenzione: Font non trovato in '{font_path}'. Uso font di default.")
        else: # Nessun path specificato
             print("Nessun percorso font specificato, uso font di default (potrebbe essere piccolo/pixelato).")
        font = ImageFont.load_default()
except IOError:
    print(f"Errore durante l'apertura del font in '{font_path}'. Uso font di default.")
    font = ImageFont.load_default()
except Exception as e:
    print(f"Errore imprevisto nel caricamento del font: {e}")
    print("Uso font di default.")
    font = ImageFont.load_default()


# --- Funzione per creare un singolo frame ---
def crea_frame(testo, frame_num):
    img = Image.new('RGB', (width, height), color=bg_color)
    d = ImageDraw.Draw(img)
    # Calcola posizione testo per centrarlo
    try:
        # Metodo più moderno per font TrueType (Pillow >= 9.3.0)
        bbox = d.textbbox((0, 0), testo, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
         # Fallback per font di default o vecchie versioni di Pillow
        try:
             text_width = d.textlength(testo, font=font)
        except AttributeError: # Ancora più vecchio? Stima basata sui caratteri
             text_width = len(testo) * font_size * 0.6 # Stima molto grezza
        text_height = font_size # Stima
        print(f"Nota: textbbox non disponibile per il font {font}, centratura potrebbe essere imprecisa.")


    x = (width - text_width) / 2
    y = (height - text_height) / 2
    # Assicurati che x, y non siano negativi (se il testo è troppo largo)
    x = max(x, 5) # Lascia un piccolo margine
    y = max(y, 5)

    d.text((x, y), testo, fill=text_color, font=font)
    frame_path = os.path.join(frames_dir, f"frame_{frame_num:03d}.png")
    img.save(frame_path)
    return frame_path

# --- Genera i frame ---
# Assicurati che la cartella temporanea esista
if not os.path.exists(frames_dir):
    os.makedirs(frames_dir)

frame_paths = []
i = 0
# Definisci la sequenza di testi da mostrare
testi_per_frame = [
    testo_originale,
    testo_tokenizzato,
    testo_token_invertito,
    # testo_ricomposto_token, # Decommenta questa linea se vuoi aggiungere questo passaggio
    testo_originale, # Ritorno all'originale per separare i due processi
    testo_lettere,
    testo_lettere_invertite,
    testo_invertito_completo
]

print("Generazione frame...")
for testo in testi_per_frame:
    frame_paths.append(crea_frame(testo, i))
    print(f" Creato frame {i}: {os.path.basename(frame_paths[-1])}")
    i += 1
print(f"Generati {len(frame_paths)} frames.")

# --- DEFINISCI DURATE SPECIFICHE PER OGNI FRAME (in secondi) ---
# La lunghezza di questa lista DEVE corrispondere esattamente
# al numero di frame generati (cioè alla lunghezza di 'testi_per_frame').
# Modifica questi valori secondo le tue preferenze per il ritmo dell'animazione:
durations = [
    0.1,  # 1. Originale
    0.1,  # 2. Tokenizzato (più tempo per leggere i token)
    0.1,  # 3. Token Invertiti (più tempo)
    # 2.0,  # Durata per 'testo_ricomposto_token' (se lo hai aggiunto sopra)
    0.1,  # 4. Ritorno all'originale (breve)
    0.1,  # 5. Lettere Separate (probabilmente serve più tempo)
    0.1,  # 6. Lettere Invertite (più tempo)
    0.1   # 7. Finale Invertito (risultato finale)
]

# Controllo di sicurezza
if len(durations) != len(frame_paths):
    raise ValueError(f"Errore Critico: Il numero di durate ({len(durations)}) non corrisponde al numero di frame ({len(frame_paths)})! Controlla la lista 'durations' e 'testi_per_frame'.")

# --- Crea la GIF ---
images = []
print("Caricamento immagini per GIF...")
for filename in frame_paths:
    images.append(imageio.imread(filename))

print(f"Creazione GIF ('{output_gif}') con {len(images)} frames e durate variabili...")

# Usa imageio per salvare la GIF animata, passando la LISTA di durate
# loop=0 significa che la GIF si ripeterà all'infinito
try:
    imageio.mimsave(output_gif, images, duration=durations, loop=0)
    print(f"GIF creata con successo: {output_gif}")
except Exception as e:
    print(f"Errore durante la creazione della GIF con imageio: {e}")


# --- Pulizia (opzionale) ---
# Decommenta le righe seguenti se vuoi cancellare i frame temporanei dopo la creazione della GIF
# import shutil
# try:
#     shutil.rmtree(frames_dir)
#     print(f"Cartella frame temporanea '{frames_dir}' rimossa.")
# except OSError as e:
#     print(f"Errore nella rimozione della cartella temporanea: {e}")