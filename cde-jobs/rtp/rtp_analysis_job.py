# process_kpi_to_gold.py
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    trim,
    lpad,
    substring,
    countDistinct,
    desc,
    row_number,
    sum as _sum,
    when,
)
from pyspark.sql.window import Window
from time import time

# ----------------------
# Logging configuration
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rtp-analysis-job")

# Definisci le colonne MINIME necessarie da ogni tabella.
# Questo riduce il traffico I/O iniziale.
COLS_PO = ["id", "payment_position_id", "iuv"]
COLS_PP = ["id", "iupd", "status", "organization_fiscal_code"] # Aggiunta organization_fiscal_code per completezza
COLS_T = ["payment_option_id", "category", "amount"]
COLS_RPT = ["segregazione", "id_intermediario_pa", "id_dominio"]

# ==========================================================
# 1. SETUP SESSIONE SPARK (La sessione è già corretta)
# ==========================================================
def main():
    start_time = time()
    spark = (
        SparkSession.builder
        .appName("rtp-analysis")
        .enableHiveSupport()
        .getOrCreate()
    )

    logger.info("=== JOB rtp-analysis AVVIATO ===")

    # ==========================================================
    # 2. Caricamento tabelle Silver GPD (Filtro colonne e Rinomina subito)
    # ==========================================================
    logger.info("Caricamento e PROIEZIONE colonne necessarie.")

    # Usiamo 'alias' per proiettare subito solo le colonne necessarie (Filter-Projection)
    rpt = spark.table("pagopa_dev.rtp_pt_report").select(*COLS_RPT)

    # Proiettiamo le colonne dal campo 'after' in modo efficiente
    # Le ridenominiamo subito per evitare ambiguità nei join successivi
    po  = spark.table("pagopa.silver_gpd_payment_option").select(
        col("after.id").alias("po_id"),
        col("after.payment_position_id"),
        col("after.iuv")
    ).cache() # <-- CRITICAL: Cache i dati dopo la prima proiezione e pulizia

    pp  = spark.table("pagopa.silver_gpd_payment_position").select(
        col("after.id").alias("pp_id"),
        col("after.iupd"),
        col("after.status"),
        col("after.organization_fiscal_code")
    )

    t   = spark.table("pagopa.silver_gpd_transfer").select(
        col("after.payment_option_id"),
        col("after.category"),
        col("after.amount")
    )

    logger.info("Tabelle caricate e cache PO attivata ✔")


    # ==========================================================
    # 3. FILTRO SUI TRANSFER (categoria 9/.../) (F1)
    # ==========================================================
    logger.info("Step 3 - filtro TRANSFER: category rlike '^9/.+/$'")
    # Filtro applicato subito sulla tabella più grande (Filter Early)
    t_f1 = t.filter(
        col("category").rlike(r"^9/.+/$")
    ).cache() # <-- CRITICAL: Cache del risultato dopo la prima grande riduzione (t_f1 sarà riutilizzato)
    logger.info("Step 3 completato (t_f1 creato e in cache)")

    # --------------------------------------------------------------------------------
    # 4. FILTRO CASCATA E REDUCE SULLE TABELLE DI DIMENSIONE
    # --------------------------------------------------------------------------------

    # 4a. Ottieni PO IDs dai TRANSFER (t_f1)
    po_ids_from_t = t_f1.select("payment_option_id").distinct()

    # 4b. Filtra PAYMENT_OPTION (po) - Esegui la prima GIUNZIONE per ridurre PO
    logger.info("Step 4 - Riduzione PAYMENT_OPTION dai TRANSFER filtrati")
    po_f1 = po.join(
        po_ids_from_t,
        po.po_id == po_ids_from_t.payment_option_id,
        "inner"
    ).drop(po_ids_from_t.payment_option_id) # Elimina la colonna di join superflua

    # Esegui la prima azione FORZATA per materializzare e ridurre il dataset PO
    po_f1.cache().count() # <-- FORZA L'ESECUZIONE e la cache (ottimale)
    logger.info(f"Step 4 completato. payment_option filtrati e in cache: {po_f1.count()}")


    # ==========================================================
    # 5. FILTRO PAYMENT_POSITION
    # ==========================================================
    logger.info("Step 5 - Filtro PAYMENT_POSITION per type/status e propagazione da PO")

    # 5a. Filtro F3: applicato subito sulla tabella PP
    pp_f1 = pp.filter(
        ~col("iupd").like("ACA_%")
    ).filter(
        col("status").isin("VALID", "PARTIALLY_PAID")
    )

    # 5b. Ottieni PP IDs dalle PO filtrate
    pp_ids_from_po = po_f1.select("payment_position_id").distinct()

    # 5c. Filtro F4: propagazione da PO alle PP (Inner Join)
    pp_final = pp_f1.join(
        pp_ids_from_po,
        pp_f1.pp_id == pp_ids_from_po.payment_position_id,
        "inner"
    ).drop(pp_ids_from_po.payment_position_id)

    pp_final.cache().count() # <-- FORZA L'ESECUZIONE e la cache
    logger.info(f"Step 5 completato. payment_position finali e in cache: {pp_final.count()}")


    # ==========================================================
    # 6. ULTERIORI FILTRI PER PULIZIA FINALE (Non strettamente necessari se le chiavi sono già ridotte)
    #    Questo step è stato semplificato/ridotto perché i dataset PO e PP sono già filtrati.
    # ==========================================================

    # 6a. Filtra PO per garantire che matchino solo i PP finali
    po_ids_final = pp_final.select("pp_id").distinct()

    po_final = po_f1.join(
        po_ids_final,
        po_f1.payment_position_id == po_ids_final.pp_id,
        "inner"
    ).drop(po_ids_final.pp_id)

    po_final.cache()
    logger.info(f"Step 6 completato. payment_option finali: {po_final.count()}")


    # 7. FILTRO TRANSFER basato sulle PO filtrate
    logger.info("Step 7 - filtro TRANSFER finale basato sulle PO filtrate")

    po2_ids = po_final.select("po_id").distinct()

    # T_F1 (già ridotto e in cache) si giunge con i PO IDs filtrati finali
    t_final = t_f1.join(
        po2_ids,
        t_f1.payment_option_id == po2_ids.po_id,
        "inner"
    ).drop(po2_ids.po_id)

    t_final.cache()
    logger.info(f"Step 7 completato. transfer finali: {t_final.count()}")


    # ==========================================================
    # 8. NORMALIZZAZIONE CHIAVI
    # ==========================================================
    logger.info("Step 8 - normalizzazione chiavi (seg_key, iuv_prefix)")

    # Rinomina la colonna ID in PP per il join
    pp_final = pp_final.withColumnRenamed("pp_id", "id_posiz_pagamento")

    # Normalizzazione per JOIN rpt
    rpt_norm = rpt.withColumn("seg_key", lpad(col("segregazione").cast("string"), 2, "0"))
    po_norm = po_final.withColumn("iuv_prefix", substring(col("iuv"), 1, 2))

    logger.info("Step 8 completato (rpt_norm, po_norm creati)")

    # ==========================================================
    # 9. JOIN FINALE (Utilizziamo solo i DataFrame finali, più piccoli)
    # ==========================================================
    logger.info("Step 9.1 - JOIN rpt → payment_option")

    # Join su RPT, che è piccolo
    j1 = rpt_norm.alias("r").join(
        po_norm.alias("po"),
        col("r.seg_key") == col("po.iuv_prefix"),
        "inner"
    )

    logger.info("Step 9.1 completato (j1 creato)")

    logger.info("Step 9.2 - JOIN payment_option → payment_position")

    # Giunzione su PP finale (già ridotto)
    j2 = j1.join(
        pp_final.alias("pp"),
        col("po.payment_position_id") == col("pp.id_posiz_pagamento"),
        "inner"
    )

    logger.info("Step 9.2 completato (j2 creato)")

    logger.info("Step 9.3 - JOIN con TRANSFER filtrati")

    # Giunzione su TRANSFER finale (già ridotto)
    j_services = j2.join(
        t_final.alias("t"),
        col("po.po_id") == col("t.payment_option_id"),
        "left"
    )

    logger.info("Step 9.3 completato (j_services creato)")

    # ==========================================================
    # 10. ANALISI FINALE (Le analisi ora usano un DataFrame molto più piccolo)
    # ==========================================================
    logger.info("Step 10.1 - Top 10 partner tecnologici per numero posizioni")

    # Utilizziamo j2 che contiene i PP e i dati rpt
    partner_positions = (
        j2.groupBy(col("r.id_intermediario_pa").alias("id_intermediario_pa"))
        .agg(countDistinct("pp.iupd").alias("num_posizioni"))
    )
    # Le azioni .show() e .count() sono ora veloci
    top10_partner = partner_positions.orderBy(desc("num_posizioni")).limit(10)
    logger.info("Top 10 partner tecnologici (primi 10):")
    top10_partner.show(truncate=False)

    logger.info("Step 10.2 - Top 2 enti per partner")

    partner_enti = (
        j2.groupBy("r.id_intermediario_pa", "pp.organization_fiscal_code")
        .agg(countDistinct("pp.iupd").alias("num_posizioni"))
    )

    w = Window.partitionBy("id_intermediario_pa").orderBy(desc("num_posizioni"))

    top2_enti = (
        partner_enti
        .withColumn("rank", row_number().over(w))
        .filter(col("rank") <= 2)
    )

    logger.info("Top 2 enti per ciascun partner:")
    top2_enti.show(truncate=False)

    logger.info("Step 10.3 - Top servizi (t.category) per partner")

    partner_services = (
        j_services.groupBy("r.id_intermediario_pa", "t.category")
        .agg(_sum("t.amount").alias("totale_importi"))
    )

    w2 = Window.partitionBy("id_intermediario_pa").orderBy(desc("totale_importi"))

    top_services = (
        partner_services
        .withColumn("rank", row_number().over(w2))
        .filter(col("rank") <= 3)
    )

    logger.info("Top 3 servizi per ciascun partner:")
    top_services.show(truncate=False)

    end_time = time()
    logger.info(f"Tempo totale di esecuzione: {end_time - start_time:.2f} secondi")
    logger.info("=== JOB rtp-analysis COMPLETATO CON SUCCESSO ===")
    spark.stop()


if __name__ == "__main__":
    main()