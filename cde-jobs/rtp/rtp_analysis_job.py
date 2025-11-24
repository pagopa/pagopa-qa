#!/usr/bin/env python3
# rtp_analysis_job.py

import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    lpad,
    substring,
    countDistinct,
    desc,
    row_number,
    sum as _sum
)
from pyspark.sql.window import Window

# ==========================================================
# LOGGING SETUP
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
log = logging.getLogger("rtp-analysis")

# ==========================================================
# 1. SPARK SESSION (stile CDE già usato)
# ==========================================================
log.info("Avvio SparkSession...")
spark = (
    SparkSession.builder
    .appName("rtp-analysis")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
log.info("SparkSession avviata.")

# ==========================================================
# 2. LETTURA TABELLE
# ==========================================================
log.info("Lettura tabelle sorgenti...")

rpt = spark.table("pagopa_dev.rtp_pt_report")
po_raw = spark.table("pagopa.silver_gpd_payment_option").select("after.*")
pp_raw = spark.table("pagopa.silver_gpd_payment_position").select("after.*")
t_raw  = spark.table("pagopa.silver_gpd_transfer").select("after.*")

log.info("Tabelle lette:")
log.info(f" - rpt_pt_report schema: {rpt.schema.simpleString()}")
log.info(f" - payment_option schema: {po_raw.schema.simpleString()}")
log.info(f" - payment_position schema: {pp_raw.schema.simpleString()}")
log.info(f" - transfer schema: {t_raw.schema.simpleString()}")

# ⚠️ I count qui possono essere pesanti, tienili solo se ti servono veramente
# log.info(f" - rpt_pt_report count: {rpt.count()}")
# log.info(f" - payment_option count: {po_raw.count()}")
# log.info(f" - payment_position count: {pp_raw.count()}")
# log.info(f" - transfer count: {t_raw.count()}")

# ==========================================================
# 3. FILTRI SU PAYMENT POSITION (type + status)
# ==========================================================
log.info("Applico filtri su payment_position (type + status)...")

pp_f1 = pp_raw.filter(
    (col("type") == "GPD")
    | ((col("type") == "ACA") & (~col("iupd").like("ACA_%")))
)

pp_f2 = pp_f1.filter(col("status").isin("VALID", "PARTIALLY_PAID"))

pp_f2_count = pp_f2.count()
log.info(f"payment_position dopo filtraggio type/status: {pp_f2_count} record.")

pp_ids = pp_f2.select("id").distinct()
log.info("ID payment_position filtrate estratti (distinct).")

# ==========================================================
# 4. PROPAGAZIONE FILTRO A PAYMENT_OPTION
# ==========================================================
log.info("Propago il filtro PP -> PO (join su payment_position_id)...")

po_f1 = po_raw.join(
    pp_ids.withColumnRenamed("id", "pp_id"),
    po_raw.payment_position_id == col("pp_id"),
    "inner"
).drop("pp_id")

po_f1 = po_f1.withColumnRenamed("id", "po_id")

po_f1_count = po_f1.count()
log.info(f"payment_option dopo propagazione da PP: {po_f1_count} record.")

# ==========================================================
# 5. FILTRO TRANSFER PER CATEGORY 9/.../ + PROPAGAZIONE
# ==========================================================
log.info("Filtro transfer per category nel formato 9/.../ ...")

t_f1 = t_raw.filter(
    col("category").rlike(r"^9/.+/$")
)
t_f1_count = t_f1.count()
log.info(f"transfer dopo filtro category 9/.../: {t_f1_count} record.")

log.info("Propago filtro PO -> transfer (solo transfer collegati a PO filtrate)...")
po_ids = po_f1.select("po_id").distinct()

t_f2 = t_f1.join(
    po_ids,
    t_f1.payment_option_id == po_ids.po_id,
    "inner"
).drop("po_id")

t_f2_count = t_f2.count()
log.info(f"transfer finali dopo propagazione da PO: {t_f2_count} record.")

# ==========================================================
# 6. NORMALIZZAZIONE CHIAVI (segregazione & IUV prefix)
# ==========================================================
log.info("Normalizzo chiavi: segregazione -> seg_key, IUV -> iuv_prefix...")

rpt2 = rpt.withColumn(
    "seg_key",
    lpad(col("segregazione").cast("string"), 2, "0")
)

po2 = po_f1.withColumn(
    "iuv_prefix",
    substring(col("iuv"), 1, 2)
)

log.info("Normalizzazione chiavi completata.")

# ==========================================================
# 7. JOIN rpt -> po -> pp
# ==========================================================
log.info("Inizio JOIN 1: rpt <-> payment_option (seg_key <-> iuv_prefix)...")

r  = rpt2.alias("r")
poA = po2.alias("po")
ppA = pp_f2.alias("pp")

j1 = r.join(
    poA,
    col("r.seg_key") == col("po.iuv_prefix"),
    "inner"
)

j1_count = j1.count()
log.info(f"JOIN 1 completata. Record in j1: {j1_count}")

log.info("Inizio JOIN 2: payment_option <-> payment_position...")

j2 = j1.join(
    ppA,
    col("po.payment_position_id") == col("pp.id"),
    "inner"
)

j2_count = j2.count()
log.info(f"JOIN 2 completata. Record in j2: {j2_count}")

# ==========================================================
# 8. TOP 10 PARTNER TECNOLOGICI (per numero di posizioni)
# ==========================================================
log.info("Calcolo TOP 10 partner tecnologici per numero di posizioni...")

partner_positions = (
    j2.groupBy("r.id_intermediario_pa")
    .agg(countDistinct("pp.iupd").alias("num_posizioni"))
)

top10_partner = (
    partner_positions
    .orderBy(desc("num_posizioni"))
    .limit(10)
)

log.info("Scrivo risultato TOP 10 partner su pagopa_dev.rtp_top10_partner_posizioni...")
top10_partner.write.mode("overwrite").saveAsTable(
    "pagopa_dev.rtp_top10_partner_posizioni"
)
log.info("Scrittura TOP 10 partner completata.")

# ==========================================================
# 9. TOP 2 ENTI PER OGNI PARTNER
# ==========================================================
log.info("Calcolo TOP 2 enti per ogni partner...")

partner_enti = (
    j2.groupBy("r.id_intermediario_pa", "r.id_dominio")
    .agg(countDistinct("pp.iupd").alias("num_posizioni"))
)

w_enti = Window.partitionBy("id_intermediario_pa").orderBy(desc("num_posizioni"))

top2_enti = (
    partner_enti
    .withColumn("rank", row_number().over(w_enti))
    .filter(col("rank") <= 2)
)

log.info("Scrivo risultato TOP 2 enti per partner su pagopa_dev.rtp_top2_enti_per_partner...")
top2_enti.write.mode("overwrite").saveAsTable(
    "pagopa_dev.rtp_top2_enti_per_partner"
)
log.info("Scrittura TOP 2 enti completata.")

# ==========================================================
# 10. TOP SERVIZI PER PARTNER (via transfer filtrati)
# ==========================================================
log.info("JOIN con transfer filtrati per analisi dei servizi...")

tA = t_f2.alias("t")

j_services = j2.join(
    tA,
    col("po.po_id") == col("t.payment_option_id"),
    "left"
)

j_services_count = j_services.count()
log.info(f"JOIN servizi completata. Record in j_services: {j_services_count}")

log.info("Calcolo TOP servizi (category) per partner...")

partner_services = (
    j_services.groupBy("r.id_intermediario_pa", "t.category")
    .agg(_sum("t.amount").alias("totale_importi"))
)

w_serv = Window.partitionBy("id_intermediario_pa").orderBy(desc("totale_importi"))

top_services = (
    partner_services
    .withColumn("rank", row_number().over(w_serv))
    .filter(col("rank") <= 3)
)

log.info("Scrivo risultato TOP servizi per partner su pagopa_dev.rtp_top_servizi_per_partner...")
top_services.write.mode("overwrite").saveAsTable(
    "pagopa_dev.rtp_top_servizi_per_partner"
)
log.info("Scrittura TOP servizi completata.")

log.info("Job rtp-analysis completato con successo, stop Spark.")
spark.stop()
