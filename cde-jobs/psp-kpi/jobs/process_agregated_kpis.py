# process_kpi_to_gold.py
import logging
from pyspark.sql import SparkSession
from pyspark.sql.utils import AnalysisException
from pyspark.sql.functions import (
    col, trim, split, transform, array_sort, array_join, explode,
    coalesce, sum as fsum, max as fmax, when, lit, isnan, size, expr, round
)
from datetime import datetime, date, timedelta
from time import time
from typing import Optional, Tuple


# ----------------------
# Logging configuration
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("kpi-gold-job")

# -----------------------
# Parameters
# -----------------------
spark = SparkSession.builder.appName("kpi-gold-iceberg").getOrCreate()

source_db   = spark.conf.get("spark.job.source_db",         "pagopa")
source_tbl  = spark.conf.get("spark.job.source_table",      "silver_kpi_psp")
agg_db      = spark.conf.get("spark.job.agg_db",            "pagopa_any_registries_pda")
agg_tbl     = spark.conf.get("spark.job.agg_table",         "contracts_crm")
target_db   = spark.conf.get("spark.job.target_db",         "pagopa_dev")
target_tbl  = spark.conf.get("spark.job.target_table",      "gold_kpi_pagamenti_psp")
sample_lim  = int(spark.conf.get("spark.job.sample_limit",  "0")) # only for test (0 = all)
target_loc  = spark.conf.get("spark.job.target_location",   "") # location for wherehouse (optional S3/ABFS prefix)

# preiod range
period_start = spark.conf.get("spark.job.period_start",     "") # e.g. '2025-05-01T00:00:00Z'
period_end   = spark.conf.get("spark.job.period_end",       "") # e.g. '2025-05-31T00:00:00Z'

# If True, a CRM "group" with a single member still counts as a group (default False to avoid duplicates)
count_groups_of_one = spark.conf.get("spark.job.count_groups_of_one", "false").lower() == "true"

src_fqn = f"{source_db}.{source_tbl}"
agg_fqn = f"{agg_db}.{agg_tbl}"
tgt_fqn = f"{target_db}.{target_tbl}"

log.info("------------------------")
log.info("---- Parameters --------")
log.info("------------------------")
log.info(f"KPI source table: {src_fqn}")
log.info(f"PSP aggregations table: {agg_fqn}")
log.info(f"Aggregate kpis gold table: {tgt_fqn}")
log.info(f"Period start: {period_start or '(none)'}")
log.info(f"Period end: {period_end or '(none)'}")
log.info(f"count_groups_of_one={count_groups_of_one}")
if sample_lim > 0: log.info(f"Sampling source with LIMIT {sample_lim}")
if target_loc:     log.info(f"Target LOCATION: {target_loc}")
log.info("------------------------")

# ---------------------------------
# Utility functions
# ---------------------------------
def table_exists(db: str, tbl: str) -> bool:
    ident = f"{db}.{tbl}"
    try:
        return spark.catalog.tableExists(ident)
    except Exception as e:
        log.warning("catalog.tableExists(%s) failed: %s", ident, e)

    try:
        return spark.sql(f"SHOW TABLES IN {db} LIKE '{tbl}'").count() > 0
    except Exception as e2:
        log.warning("SHOW TABLES fallback failed for %s: %s", ident, e2)
        return True

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

def previous_month_range(today: Optional[date] = None) -> Tuple[str, str]:
    """Return ('YYYY-MM-01T00:00:00Z', 'YYYY-MM-lastT00:00:00Z') for the previous month."""
    if today is None:
        today = datetime.utcnow().date()

    first_this = date(today.year, today.month, 1) # first day of this month
    last_prev  = first_this - timedelta(days=1) # last day of previous month
    first_prev = date(last_prev.year, last_prev.month, 1) # first day of previous month
    start = f"{first_prev.strftime('%Y-%m-%d')}T00:00:00Z"
    end   = f"{first_this.strftime('%Y-%m-%d')}T00:00:00Z"
    return start, end

# -----------------------
# Read source KPIs
# -----------------------

# date/period filters
if not period_start or not period_end:
    # Missing one or both -> fall back to previous month
    period_start, period_end = previous_month_range()

# quality guards (same ones you had)
conds = [
    f"`start` = '{period_start}'",
    f"`end`   = '{period_end}'",
    "perc_kpi IS NOT NULL",
    "NOT isnan(perc_kpi)",
    "total_kpi_sample IS NOT NULL",
    "total_kpi_fault  IS NOT NULL",
]

where_sql = (" WHERE " + " AND ".join(conds))
limit_sql = f" LIMIT {sample_lim}" if sample_lim > 0 else ""
src_sql = f"SELECT * FROM {src_fqn}{where_sql}{limit_sql}"
log.info(f"Reading source KPIs with SQL:\n{src_sql}")
src = spark.sql(src_sql)
log.info(f"Source rows read: {src.count()}")

# ---------------------------------------
# Read crm table to get aggreations
# ---------------------------------------
crm = spark.table(agg_fqn).select("provider_names", "contract_id").where(
    col("provider_names").isNotNull() & (trim(col("provider_names")) != "")
)

crm_norm = (
    crm
    .withColumn("members_array", transform(split(col("provider_names"), ","), lambda x: trim(x)))
    .withColumn("members_array", expr("filter(members_array, x -> x <> '')"))
)
log.info(f"CRM groups read: {crm_norm.count()}")

# Create a lookup for all individual psp_members to their contract_id
# This is needed for "singles" that might be in groups of 1 (filtered later)
psp_to_contract_id_lookup = (
    crm_norm
    .select("contract_id", explode(col("members_array")).alias("psp_member"))
    .dropDuplicates(["psp_member", "contract_id"])
    # If a psp is in multiple contracts (which shouldn't happen?), pick the "min"
    .groupBy("psp_member")
    .agg(expr("min(contract_id)").alias("contract_id"))
    .withColumnRenamed("psp_member", "lookup_psp_id") # To avoid join ambiguity
)
psp_to_contract_id_lookup.cache() # Cache this as it's used later in a join

if not count_groups_of_one:
    log.info("Dropping CRM groups with a single member (to avoid duplicates)")
    crm_norm = crm_norm.where(size(col("members_array")) > 1)
    log.info(f"CRM groups after drop: {crm_norm.count()}")

crm_norm = crm_norm.withColumn("group_key", array_join(array_sort(col("members_array")), ","))
log.info(f"CRM afert grouping: {crm_norm.count()}")


# Map each member -> single canonical group_key (if member appears in multiple groups, pick the smallest)
# We also need to carry the contract_id associated with that smallest group_key
# This contains all possible (group_key, contract_id, psp_member) combinations
mapping_with_contract = (
    crm_norm
    .select("group_key", "contract_id", explode(col("members_array")).alias("psp_member"))
    .dropDuplicates(["psp_member", "group_key", "contract_id"])
)

# For each member, find their min(group_key)
min_group_mapping = (
    mapping_with_contract
    .groupBy("psp_member")
    .agg(expr("min(group_key)").alias("group_key"))
)

# Create a clean 1:1 lookup for group_key -> contract_id
# If a group_key has multiple contracts (bad data), pick the "min" one to be deterministic
group_to_contract_lookup = (
    crm_norm
    .select("group_key", "contract_id")
    .dropDuplicates(["group_key", "contract_id"])
    .groupBy("group_key")
    .agg(expr("min(contract_id)").alias("contract_id"))
)

# Join the min_group_mapping with the new group_to_contract_lookup
mapping = (
    min_group_mapping
    .join(
        group_to_contract_lookup,
        "group_key",
        "left"
    )
)

# log.info(f"Aggregation mapping size (distinct members): {mapping.count()}")

# -------------------------------------------------------------------------------
#   A) group members: PSPs present in mapping  -> aggregate by group_key
#   B) SINGLES       : PSPs NOT present in mapping -> keep single aggregation
#   If a PSP appears both alone and in a group, we keep only the group row.
# -------------------------------------------------------------------------------

# A) groupe members
grp_rows = (
    src.join(mapping, src.psp_id == mapping.psp_member, "inner")
    .drop("psp_member")
    .withColumn("target_psp_id", col("group_key"))
)

# sum total_kpi_fault and total_kpi_sample, take max kpi_threshold
agg_grouped = (
    grp_rows.groupBy("kpi_id", "start", "end", "target_psp_id", "contract_id")
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
        col("target_psp_id").cast("string").alias("psp_id"),
        col("contract_id").cast("string").alias("contract_id"),
        col("kpi_threshold").cast("double").alias("kpi_threshold"),
        perc_g.cast("double").alias("perc_kpi"),
        out_g.cast("string").alias("kpi_outcome"),
        col("start").cast("string").alias("start"),
        col("end").cast("string").alias("end"),
    )
)

# B) singles PSP - left_anti on mapping (PSPs not belonging to any group)
singles = src.join(mapping.select("psp_member").distinct(), src.psp_id == mapping.psp_member, "left_anti")
agg_single = (
    singles.groupBy("kpi_id", "start", "end", "psp_id")
    .agg(
        fsum(col("total_kpi_fault").cast("long")).alias("sum_fault"),
        fsum(col("total_kpi_sample").cast("long")).alias("sum_sample"),
        fmax(col("kpi_threshold").cast("double")).alias("kpi_threshold")
    )
)

# Join with the lookup to get contract_id for singles
agg_single_with_contract = (
    agg_single
    .join(
        psp_to_contract_id_lookup,
        agg_single.psp_id == psp_to_contract_id_lookup.lookup_psp_id,
        "left" # Use left join so we don't drop singles that aren't in CRM
    )
)

# ------------------------------------------------------
# compute perc_kpi and and write them to gold table
# ------------------------------------------------------
perc_s = when(col("sum_sample") > 0, round(col("sum_fault") * 100.0 / col("sum_sample"), 2)).otherwise(lit(None).cast("double"))
out_s  = when(perc_s <= col("kpi_threshold"), lit("OK")).otherwise(lit("KO"))

# final df result for single PSPs
df_single = (
    agg_single_with_contract.select(
        col("kpi_id").cast("string").alias("kpi_id"),
        col("psp_id").cast("string").alias("psp_id"),
        col("contract_id").cast("string").alias("contract_id"),
        col("kpi_threshold").cast("double").alias("kpi_threshold"),
        perc_s.cast("double").alias("perc_kpi"),
        out_s.cast("string").alias("kpi_outcome"),
        col("start").cast("string").alias("start"),
        col("end").cast("string").alias("end"),
    )
)

# Final union
result = df_grouped.unionByName(df_single)

try:
    log.info(f"Final rows to write: {result.count()}")
except Exception as e:
    log.warning("Skipping count() due to cloud auth/listing issue: %s", e)

# Add _ts column with current timestamp
batch_ts_ms = int(time() * 1000)   # single value for the whole load
log.info(f"Batch insert timestamp (ms): {batch_ts_ms}")
result = result.withColumn("_ts", lit(batch_ts_ms).cast("bigint"))

# Create temp view for SQL CTAS
result.createOrReplaceTempView("result_tmp")

created_now = False
if not table_exists(target_db, target_tbl):
    log.info("Target does not exist: creating EXTERNAL Iceberg v2 with required properties.")
    loc = f" LOCATION '{target_loc}'" if target_loc else ""
    try:
        spark.sql(f"""
            CREATE EXTERNAL TABLE {tgt_fqn}
            USING iceberg
            TBLPROPERTIES ('format-version'='2','engine.hive.enabled'='true')
            {loc}
            AS
            SELECT kpi_id, psp_id, contract_id, kpi_threshold, perc_kpi, kpi_outcome, `start`, `end`, _ts
            FROM result_tmp
        """)
        created_now = True
        log.info("Create Iceberg table completed.")
    except AnalysisException as e:
        msg = str(e)
        if "TABLE_OR_VIEW_ALREADY_EXISTS" in msg:
            log.warning("Race detected: %s was created by another run; switching to append.", tgt_fqn)
        else:
            raise

# Append if the table already exists
if not created_now:
    if not is_iceberg_table(target_db, target_tbl):
        raise RuntimeError(f"Target {tgt_fqn} exists but is NOT an Iceberg table.")
    log.info("Merging new data to existing Iceberg table.")

    spark.sql("""
        CREATE OR REPLACE TEMP VIEW staged_result AS
        SELECT kpi_id, psp_id, contract_id, kpi_threshold, perc_kpi, kpi_outcome, `start`, `end`, _ts
        FROM (
        SELECT *,
                 ROW_NUMBER() OVER (PARTITION BY kpi_id, psp_id, `start`, `end`
                                      ORDER BY _ts DESC) AS rn
        FROM result_tmp
        ) t
        WHERE rn = 1
    """)

    spark.sql(f"""
        MERGE INTO {tgt_fqn} AS t
        USING staged_result AS s
        ON  t.kpi_id = s.kpi_id
        AND t.psp_id = s.psp_id
        AND t.`start` = s.`start`
        AND t.`end`   = s.`end`
        WHEN MATCHED THEN UPDATE SET
        t.contract_id   = s.contract_id, 
        t.kpi_threshold = s.kpi_threshold,
        t.perc_kpi      = s.perc_kpi,
        t.kpi_outcome   = s.kpi_outcome,
        t.`start`       = s.`start`,
        t.`end`         = s.`end`,
        t._ts           = s._ts
        WHEN NOT MATCHED THEN INSERT *
    """)

    log.info("Merge (upsert) completed.")

log.info("Job finished successfully.")
spark.stop()