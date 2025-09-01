# process_kpi_to_gold.py
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, trim, split, transform, array_sort, array_join, explode,
    coalesce, sum as fsum, max as fmax, when, lit, isnan, size, expr, round
)

# ----------------------
# Logging configuration
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("kpi-gold-job")

# -----------------------
# Parameters
# -----------------------
source_db   = spark.conf.get("job.source_db",  "pagopa")
source_tbl  = spark.conf.get("job.source_table","silver_kpi_psp")
agg_db      = spark.conf.get("job.agg_db",     "pagopa_any_registries_pda")
agg_tbl     = spark.conf.get("job.agg_table",  "contracts_crm")
target_db   = spark.conf.get("job.target_db",  "pagopa_dev")
target_tbl  = spark.conf.get("job.target_table","gold_kpi_pagamenti_psp")
sample_lim  = int(spark.conf.get("job.sample_limit", "0")) # only for test (0 = all)
target_loc  = spark.conf.get("job.target_location", "") # location for wherehouse (optional S3/ABFS prefix)

# preiod range
period_start = spark.conf.get("job.period_start", "")   # e.g. '2024-05-01T00:00:00Z'
period_end   = spark.conf.get("job.period_end", "")     # e.g. '2024-05-31T00:00:00Z'
use_range    = spark.conf.get("job.period_use_range", "false").lower() == "true"

# If True, a CRM "group" with a single member still counts as a group (default False to avoid duplicates)
count_groups_of_one = spark.conf.get("job.count_groups_of_one", "false").lower() == "true"

src_fqn = f"{source_db}.{source_tbl}"
agg_fqn = f"{agg_db}.{agg_tbl}"
tgt_fqn = f"{target_db}.{target_tbl}"

log.info(f"KPI source table: {src_fqn}")
log.info(f"PSP aggregations table: {agg_fqn}")
log.info(f"Aggregate kpis gold table: {tgt_fqn}")
if sample_lim > 0: log.info(f"Sampling source with LIMIT {sample_lim}")
if target_loc:     log.info(f"Target LOCATION: {target_loc}")
log.info(f"count_groups_of_one={count_groups_of_one}")


# ---------------------------------
# Create or append to Iceberg table
# ---------------------------------
def table_exists(db, tbl) -> bool:
    try:
        return spark.catalog.tableExists(db, tbl)
    except Exception:
        return False

def is_iceberg_table(db, tbl) -> bool:
    try:
        props = spark.sql(f"SHOW TBLPROPERTIES {db}.{tbl}").collect()
        for r in props:
            if (r[0] or "").lower() == "provider" and "iceberg" in (r[1] or "").lower():
                return True
        desc = spark.sql(f"DESCRIBE EXTENDED {db}.{tbl}").collect()
        return any("iceberg" in (str(c).lower()) for row in desc for c in row if c)
    except Exception:
        return False


# -----------------------
# Read source KPIs
# -----------------------
spark = SparkSession.builder.appName("kpi-gold-iceberg").getOrCreate()

# date/period filters
conds = []
if period_start and period_end and use_range:
    # inclusive range by strings (works for ISO8601 with Z)
    conds += [f"`start` >= '{period_start}'", f"`end` <= '{period_end}'"]
elif period_start and not use_range:
    conds += [f"`start` = '{period_start}'"]
    if period_end:  # optional guard
        conds += [f"`end` = '{period_end}'"]
elif period_start:
    conds += [f"`start` >= '{period_start}'"]
if period_end and not (period_start and not use_range):
    # add end <= if we didn't already add strict equality above
    conds += [f"`end` <= '{period_end}'"]

# quality guards (same ones you had)
conds += [
    "perc_kpi IS NOT NULL",
    "NOT isnan(perc_kpi)",
    "total_kpi_sample IS NOT NULL",
    "total_kpi_fault  IS NOT NULL"
]

where_sql = (" WHERE " + " AND ".join(conds)) if conds else ""
limit_sql = f" LIMIT {sample_lim}" if sample_lim > 0 else ""

src_sql = f"SELECT * FROM {src_fqn}{where_sql}{limit_sql}"
src = spark.sql(src_sql)

# src_sql = f"SELECT * FROM {src_fqn}" + (f" LIMIT {sample_lim}" if sample_lim > 0 else "")
# src = spark.sql(src_sql).filter(
#     col("perc_kpi").isNotNull() & ~isnan(col("perc_kpi")) &
#     col("total_kpi_sample").isNotNull() & col("total_kpi_fault").isNotNull()
# )

# # currently we don't have the grant to perform count()
# log.info(f"Source rows after filters: {src.count()}")

# -----------------------
# Build aggregation mapping from CRM
# - provider_names: single psp id OR comma-separated list
# - group_key: sorted, comma-joined members (canonical)
# - Only treat as group if size > 1 (unless count_groups_of_one=True)
# -----------------------
crm = spark.table(agg_fqn).select("provider_names").where(
    col("provider_names").isNotNull() & (trim(col("provider_names")) != "")
)

crm_norm = (
    crm
    .withColumn("members_array", transform(split(col("provider_names"), ","), lambda x: trim(x)))
    .withColumn("members_array", expr("filter(members_array, x -> x <> '')"))
)

if not count_groups_of_one:
    crm_norm = crm_norm.where(size(col("members_array")) > 1)

crm_norm = crm_norm.withColumn("group_key", array_join(array_sort(col("members_array")), ","))

# Map each member -> single canonical group_key (if member appears in multiple groups, pick the smallest)
mapping = (
    crm_norm
    .select("group_key", explode(col("members_array")).alias("psp_member"))
    .dropDuplicates(["psp_member", "group_key"])
    .groupBy("psp_member").agg(expr("min(group_key)").alias("group_key"))
)

# log.info(f"Aggregation mapping size (distinct members): {mapping.count()}")

# -----------------------
#   A) group members: PSPs present in mapping  -> aggregate by group_key
#   B) SINGLES      : PSPs NOT present in mapping -> keep single aggregation
#   If a PSP appears both alone and in a group, we keep only the group row.
# -----------------------

# A) groupe members
grp_rows = (
    src.join(mapping, src.psp_id == mapping.psp_member, "inner")
       .drop("psp_member")
       .withColumn("target_psp_id", col("group_key"))
)

# sum total_kpi_fault and total_kpi_sample, take max kpi_threshold
agg_grouped = (
    grp_rows.groupBy("kpi_id", "start", "end", "target_psp_id")
            .agg(
                fsum(col("total_kpi_fault").cast("long")).alias("sum_fault"),
                fsum(col("total_kpi_sample").cast("long")).alias("sum_sample"),
                fmax(col("kpi_threshold").cast("double")).alias("kpi_threshold")
            )
)

# compute perc_kpi and kpi_outcome
perc_g = when(col("sum_sample") > 0, round(col("sum_fault") * 100.0 / col("sum_sample"), 2)).otherwise(lit(None).cast("double"))
out_g  = when(perc_g <= col("kpi_threshold"), lit("OK")).otherwise(lit("KO"))

# final df result for grouped PSPs
df_grouped = (
    agg_grouped.select(
        col("kpi_id").cast("string").alias("kpi_id"),
        col("target_psp_id").cast("string").alias("psp_id"),   # comma-separated ids
        col("kpi_threshold").cast("double").alias("kpi_threshold"),
        perc_g.cast("double").alias("perc_kpi"),
        out_g.cast("string").alias("kpi_outcome"),
        col("start").cast("string").alias("start"),
        col("end").cast("string").alias("end"),
    )
)

# B) singles PSP - left_anti on mapping (PSPs not belonging to any group)
singles = src.join(mapping, src.psp_id == mapping.psp_member, "left_anti")
agg_single = (
    singles.groupBy("kpi_id", "start", "end", "psp_id")
           .agg(
               fsum(col("total_kpi_fault").cast("long")).alias("sum_fault"),
               fsum(col("total_kpi_sample").cast("long")).alias("sum_sample"),
               fmax(col("kpi_threshold").cast("double")).alias("kpi_threshold")
           )
)

# compute perc_kpi and kpi_outcome
perc_s = when(col("sum_sample") > 0, round(col("sum_fault") * 100.0 / col("sum_sample"), 2)).otherwise(lit(None).cast("double"))
out_s  = when(perc_s <= col("kpi_threshold"), lit("OK")).otherwise(lit("KO"))

# final df result for single PSPs
df_single = (
    agg_single.select(
        col("kpi_id").cast("string").alias("kpi_id"),
        col("psp_id").cast("string").alias("psp_id"),
        col("kpi_threshold").cast("double").alias("kpi_threshold"),
        perc_s.cast("double").alias("perc_kpi"),
        out_s.cast("string").alias("kpi_outcome"),
        col("start").cast("string").alias("start"),
        col("end").cast("string").alias("end"),
    )
)

# Final union
result = df_grouped.unionByName(df_single)
log.info(f"Final rows to write: {result.count()}")

result.createOrReplaceTempView("result_tmp")

if not table_exists(target_db, target_tbl):
    log.info("Target does not exist: creating EXTERNAL Iceberg v2 with required properties.")
    loc = f" LOCATION '{target_loc}'" if target_loc else ""
    spark.sql(f"""
        CREATE EXTERNAL TABLE {tgt_fqn}
        USING iceberg
        TBLPROPERTIES ('format-version'='2','engine.hive.enabled'='true')
        {loc}
        AS
        SELECT kpi_id, psp_id, kpi_threshold, perc_kpi, kpi_outcome, `start`, `end`
        FROM result_tmp
    """)
    log.info("Create Iceberg table completed.")
else:
    if not is_iceberg_table(target_db, target_tbl):
        raise RuntimeError(
            f"Target {tgt_fqn} exists but is NOT an Iceberg table. "
            f"Drop/convert it to Iceberg before appending."
        )
    log.info("Appending to existing Iceberg table.")
    tgt_cols = [f.name for f in spark.table(tgt_fqn).schema.fields]
    result.select(*tgt_cols).writeTo(tgt_fqn).append()
    log.info("Append completed.")

log.info("Job finished successfully.")
spark.stop()
