from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    lpad,
    substring,
    countDistinct,
    desc,
    row_number,
    sum as _sum,
)
from pyspark.sql.window import Window
import logging


def main():
    # ==========================================================
    # 1. SETUP SESSIONE SPARK
    # ==========================================================
    spark = (
        SparkSession.builder
        .appName("rtp-analysis")
        .enableHiveSupport()
        .getOrCreate()
    )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("rtp-analysis-job")

    logger.info("=== JOB rtp-analysis AVVIATO ===")

    # ==========================================================
    # 2. Caricamento tabelle Silver GPD
    # ==========================================================
    logger.info("Caricamento tabelle Hive: rpt_pt_report, payment_option, payment_position, transfer")

    rpt = spark.table("pagopa_dev.rtp_pt_report")
    po  = spark.table("pagopa.silver_gpd_payment_option").select("after.*")
    pp  = spark.table("pagopa.silver_gpd_payment_position").select("after.*")
    t   = spark.table("pagopa.silver_gpd_transfer").select("after.*")

    logger.info("Tabelle caricate ✔")

    # ==========================================================
    # 3. FILTRO SUI TRANSFER (categoria 9/.../) (F1)
    # ==========================================================
    logger.info("Step 3 - filtro TRANSFER: category like '9/.../'")
    # logger.info("transfer totale prima del filtro F1: %d", t.count())
    t_f1 = t.filter(
        col("category").rlike(r"^9/.+/$")
    )

    # logger.info("transfer totale dopo il filtro F1: %d", t_f1.count())
    logger.info("Step 3 completato (t_f1 creato)")

    # ==========================================================
    # 4. FILTRO PAYMENT_OPTION derivato dai TRANSFER filtrati (F2)
    # ==========================================================
    logger.info("Step 4 - filtro PAYMENT_OPTION dai TRANSFER filtrati")
    # logger.info("payment_option totale prima del filtro F2: %d", po.count())
    po_ids_from_t = t_f1.select("payment_option_id").distinct()

    po_f1 = po.join(
        po_ids_from_t,
        po.id == po_ids_from_t.payment_option_id,
        "inner"
    ).drop(po_ids_from_t.payment_option_id)

    po_f1 = po_f1.withColumnRenamed("id", "po_id")

    # logger.info("payment_option totale dopo il filtro F2: %d", po_f1.count())
    logger.info("Step 4 completato (po_f1 creato)")

    # ==========================================================
    # 5. FILTRO PAYMENT_POSITION
    #     (GPD / ACA NO prefix + status VALID/PARTIALLY_PAID) (F3)
    # ==========================================================
    logger.info("Step 5 - filtro PAYMENT_POSITION per type/status e propagazione da PO")
    # logger.info("payment_position totale prima del filtro F3: %d", pp.count())
    pp_base = pp.filter(
        ~col("iupd").like("ACA_%")
    ).filter(
        col("status").isin("VALID", "PARTIALLY_PAID")
    )

    # logger.info("payment_position totale dopo il filtro F3: %d", pp_base.count())

    # Filtro F4: propagazione da PAYMENT_OPTION alle PAYMENT_POSITION
    logger.info("Propagazione filtro da PAYMENT_OPTION alle PAYMENT_POSITION")
    pp_ids_from_po = po_f1.select("payment_position_id").distinct()
    pp_f1 = pp_base.join(
        pp_ids_from_po,
        pp_base.id == pp_ids_from_po.payment_position_id,
        "inner"
    ).drop(pp_ids_from_po.payment_position_id)

    # logger.info("payment_position totale dopo il filtro F4: %d", pp_f1.count())
    logger.info("Step 5 completato (pp_f1 creato)")

    # ==========================================================
    # 6. FILTRO PAYMENT_OPTION basato sulle PP filtrate (F5)
    # ==========================================================
    logger.info("Step 6 - ulteriore filtro PAYMENT_OPTION basato sulle PP filtrate")

    po_ids_from_pp = pp_f1.select("id").distinct()

    po_f2 = po_f1.join(
        po_ids_from_pp,
        po_f1.payment_position_id == po_ids_from_pp.id,
        "inner"
    ).drop(po_ids_from_pp.id)

    # logger.info("payment_option totale dopo il filtro F5: %d", po_f2.count())
    logger.info("Step 6 completato (po_f2 creato)")

    # ==========================================================
    # 7. FILTRO TRANSFER basato sulle PO filtrate
    # ==========================================================
    logger.info("Step 7 - filtro TRANSFER finale basato sulle PO filtrate")

    po2_ids = po_f2.select("po_id").distinct()

    t_f2 = t_f1.join(
        po2_ids,
        t_f1.payment_option_id == po2_ids.po_id,
        "inner"
    )

    # logger.info("transfer totale dopo il filtro F6: %d", t_f2.count())
    logger.info("Step 7 completato (t_f2 creato)")

    # ==========================================================
    # 8. NORMALIZZAZIONE CHIAVI
    # ==========================================================
    logger.info("Step 8 - normalizzazione chiavi (seg_key, iuv_prefix)")

    rpt2 = rpt.withColumn("seg_key", lpad(col("segregazione").cast("string"), 2, "0"))

    po_norm = po_f2.withColumn("iuv_prefix", substring(col("iuv"), 1, 2))

    logger.info("Step 8 completato (rpt2, po_norm creati)")

    # ==========================================================
    # 9. JOIN
    # ==========================================================
    logger.info("Step 9.1 - JOIN rpt → payment_option")

    j1 = rpt2.alias("r").join(
        po_norm.alias("po"),
        col("r.seg_key") == col("po.iuv_prefix"),
        "inner"
    )

    logger.info("Step 9.1 completato (j1 creato)")

    logger.info("Step 9.2 - JOIN payment_option → payment_position")

    j2 = j1.join(
        pp_f1.alias("pp"),
        col("po.payment_position_id") == col("pp.id"),
        "inner"
    )

    logger.info("Step 9.2 completato (j2 creato)")

    logger.info("Step 9.3 - JOIN con TRANSFER filtrati")

    j_services = j2.join(
        t_f2.alias("t"),
        col("po.po_id") == col("t.payment_option_id"),
        "left"
    )

    logger.info("Step 9.3 completato (j_services creato)")

    # ==========================================================
    # 10. ANALISI
    # ==========================================================
    logger.info("Step 10.1 - Top 10 partner tecnologici per numero posizioni")

    partner_positions = (
        j2.groupBy("r.id_intermediario_pa")
        .agg(countDistinct("pp.iupd").alias("num_posizioni"))
    )

    top10_partner = partner_positions.orderBy(desc("num_posizioni")).limit(10)

    logger.info("Top 10 partner tecnologici (primi 10):")
    top10_partner.show(truncate=False)

    logger.info("Step 10.2 - Top 2 enti per partner")

    partner_enti = (
        j2.groupBy("r.id_intermediario_pa", "r.id_dominio")
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

    logger.info("=== JOB rtp-analysis COMPLETATO CON SUCCESSO ===")
    spark.stop()


if __name__ == "__main__":
    main()
