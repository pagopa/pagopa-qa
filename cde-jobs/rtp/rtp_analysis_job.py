# process_kpi_to_gold_optimized.py
import logging
from time import time
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, lpad, substring, countDistinct, desc,
    row_number, sum as _sum, broadcast
)
from pyspark.sql.window import Window

# ----------------------
# Configuration & Logging
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rtp-analysis-job")

# Colonne minime (Projection Pushdown manuale)
COLS_PO = ["id", "payment_position_id", "iuv"]
COLS_PP = ["id", "iupd", "status", "organization_fiscal_code"]
COLS_T = ["payment_option_id", "category", "amount"]
COLS_RPT = ["segregazione", "id_intermediario_pa", "id_dominio"]

def main():
    start_time = time()

    # 1. SETUP SESSIONE SPARK CDE (Spark 3.x)
    # Abilitiamo AQE (Adaptive Query Execution) fondamentale su Cloudera
    spark = (
        SparkSession.builder
        .appName("rtp-analysis")
        .enableHiveSupport()
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        # Rimuoviamo il shuffle.partitions fisso a 1000, lasciamo fare ad AQE o usiamo un default sensato
        .config("spark.sql.shuffle.partitions", "auto")
        .getOrCreate()
    )

    logger.info("=== JOB rtp-analysis OPTIMIZED AVVIATO ===")

    # ==========================================================
    # 2. Caricamento Dati (Lazy)
    # ==========================================================
    logger.info("Caricamento tabelle e proiezione colonne...")

    # RPT è piccola: la prepariamo subito
    rpt = spark.table("pagopa_dev.rtp_pt_report").select(*COLS_RPT)

    # PO: Payment Option
    po = spark.table("pagopa.silver_gpd_payment_option").select(
        col("after.id").alias("po_id"),
        col("after.payment_position_id"),
        col("after.iuv")
    )

    # PP: Payment Position
    pp = spark.table("pagopa.silver_gpd_payment_position").select(
        col("after.id").alias("pp_id"),
        col("after.iupd"),
        col("after.status"),
        col("after.organization_fiscal_code")
    )

    # T: Transfer
    t = spark.table("pagopa.silver_gpd_transfer").select(
        col("after.payment_option_id"),
        col("after.category"),
        col("after.amount")
    )

    # ==========================================================
    # 3. FILTRAGGIO A CASCATA (WATERFALL)
    # ==========================================================

    # --- STEP 3A: Filtro Iniziale su TRANSFER ---
    logger.info("Filtro Transfer su category...")
    # Usiamo startswith se possibile (più veloce di rlike), altrimenti rlike va bene.
    # Assumiamo che category inizi con '9/'
    t_filtered = t.filter(col("category").rlike(r"^9/.+/$"))

    # Ottimizzazione: Non cachiamo subito t_filtered se è molto grande,
    # aspettiamo di ridurlo con le PO valide.

    # --- STEP 3B: Identificare PO candidate dai Transfer ---
    # Usiamo LEFT SEMI JOIN: tieni le righe di 'po' che hanno una corrispondenza in 't_filtered'
    # Questo evita di dover fare distinct() + inner join + drop colonna
    po_candidates = po.join(t_filtered, po.po_id == t_filtered.payment_option_id, "left_semi")

    # --- STEP 3C: Filtro PP (Business Logic) ---
    logger.info("Filtro Payment Position (Status e Type)...")
    pp_valid = pp.filter(
        (~col("iupd").like("ACA_%")) &
        (col("status").isin("VALID", "PARTIALLY_PAID"))
    )

    # --- STEP 3D: Intersezione Finale (Il cuore dell'ottimizzazione) ---
    # Ora dobbiamo assicurarci che la catena sia valida: T -> PO -> PP

    # 1. Troviamo le PP che sono collegate alle PO candidate (che a loro volta hanno Transfer validi)
    pp_final = pp_valid.join(
        po_candidates,
        pp_valid.pp_id == po_candidates.payment_position_id,
        "left_semi"
    ).cache() # Cache qui: PP finali sono la base della verità

    # Forziamo la materializzazione solo se necessario per logica di business o debug
    # logger.info(f"PP Finali: {pp_final.count()}")

    # 2. Troviamo le PO finali basate sulle PP finali
    # Nota: po_candidates conteneva PO con transfer validi, ma magari con PP invalide.
    # Ora filtriamo po_candidates tenendo solo quelle che puntano a pp_final.
    po_final = po_candidates.join(
        pp_final,
        po_candidates.payment_position_id == pp_final.pp_id,
        "left_semi"
    ).cache()

    # 3. Troviamo i Transfer finali basati sulle PO finali
    t_final = t_filtered.join(
        po_final,
        t_filtered.payment_option_id == po_final.po_id,
        "left_semi"
    ).cache()

    logger.info("Dataset finali (PP, PO, T) calcolati e in cache.")

    # ==========================================================
    # 4. PREPARAZIONE JOIN & ARRICCHIMENTO
    # ==========================================================

    # Preparazione chiavi di join (trasformazioni stringa)
    # È efficiente farlo ora sui dataset ridotti
    rpt_norm = rpt.withColumn("seg_key", lpad(col("segregazione").cast("string"), 2, "0"))
    po_final = po_final.withColumn("iuv_prefix", substring(col("iuv"), 1, 2))

    # ==========================================================
    # 5. JOIN MASTER
    # ==========================================================
    logger.info("Esecuzione Join Master...")

    # Join 1: RPT (Broadcast) -> PO
    # Usiamo broadcast(rpt_norm) esplicitamente. RPT è piccola, evita lo shuffle.
    join_po_rpt = po_final.alias("po").join(
        broadcast(rpt_norm).alias("r"),
        col("po.iuv_prefix") == col("r.seg_key"),
        "inner"
    )

    # Join 2: -> PP
    join_core = join_po_rpt.join(
        pp_final.alias("pp"),
        col("po.payment_position_id") == col("pp.pp_id"),
        "inner"
    )

    # Cache del core dataframe (PO + PP + RPT) usato per 2 su 3 KPI
    join_core.cache()

    # Join 3: -> Transfer (per il terzo KPI)
    # Nota: Left join perché vogliamo analizzare i servizi, ma il filtro a monte garantisce consistenza
    join_services = join_core.join(
        t_final.alias("t"),
        col("po.po_id") == col("t.payment_option_id"),
        "left"
    )

    # ==========================================================
    # 6. CALCOLO KPI
    # ==========================================================

    # KPI 1: Top 10 Partner
    logger.info("Calcolo KPI 1: Top 10 Partner...")
    (
        join_core
        .groupBy(col("r.id_intermediario_pa"))
        .agg(countDistinct("pp.iupd").alias("num_posizioni"))
        .orderBy(desc("num_posizioni"))
        .limit(10)
        .show(truncate=False)
    )

    # KPI 2: Top 2 Enti per Partner
    logger.info("Calcolo KPI 2: Top 2 Enti per Partner...")
    w_enti = Window.partitionBy("id_intermediario_pa").orderBy(desc("num_posizioni"))

    (
        join_core
        .groupBy("r.id_intermediario_pa", "pp.organization_fiscal_code")
        .agg(countDistinct("pp.iupd").alias("num_posizioni"))
        .withColumn("rank", row_number().over(w_enti))
        .filter(col("rank") <= 2)
        .show(truncate=False)
    )

    # KPI 3: Top 3 Servizi (Transfer) per Partner
    logger.info("Calcolo KPI 3: Top 3 Servizi per Partner...")
    w_serv = Window.partitionBy("id_intermediario_pa").orderBy(desc("totale_importi"))

    (
        join_services
        .groupBy("r.id_intermediario_pa", "t.category")
        .agg(_sum("t.amount").alias("totale_importi"))
        .withColumn("rank", row_number().over(w_serv))
        .filter(col("rank") <= 3)
        .show(truncate=False)
    )

    # Pulizia cache (opzionale ma educato)
    pp_final.unpersist()
    po_final.unpersist()
    t_final.unpersist()
    join_core.unpersist()

    end_time = time()
    logger.info(f"Tempo totale: {end_time - start_time:.2f} secondi")
    spark.stop()

if __name__ == "__main__":
    main()