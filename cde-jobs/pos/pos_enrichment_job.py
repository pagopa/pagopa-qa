from pyspark.sql import SparkSession
from pyspark.sql.functions import col, broadcast

# 1. Initialize Spark Session for CDE
spark = SparkSession.builder \
    .appName("POS_Enrichment_CDE_Job") \
    .config("spark.sql.catalogImplementation", "hive") \
    .getOrCreate()
    
spark = SparkSession.builder.appName("kpi-gold-iceberg").getOrCreate()

# Define paths for Data Lake (HDFS, s3a://, or abfs:// depending on your Cloud)
# You need to update these paths to where you uploaded the CSV on the Data Lake
input_csv_path = "/user/a117075/csv_temporaneo/Transazioni-POS-Q2-cumulativo.csv" 
output_csv_dir = "/user/a117075/csv_temporaneo/output_pos_enriched"
source_silver_table = "pagopa.silver_positive"

print("Step 1: Reading the input CSV from Data Lake...")
df_csv = spark.read.option("header", "true") \
                   .option("sep", ";") \
                   .csv(input_csv_path)

print("Step 2: Reading and filtering the silver_positive table...")
# Applying Predicate Pushdown and Column Pruning
df_silver = spark.table(source_silver_table) \
    .filter("CAST(paymentinfo.paymentdatetime AS TIMESTAMP) > CAST('2025-12-31 00:00:00' AS TIMESTAMP)") \
    .select(
        col("creditor.idpa").alias("silver_idpa"),
        col("debtorposition.iuv").alias("silver_iuv"),
        col("id").alias("PAYMENT_ID")
    )

print("Step 3: Performing Broadcast Join...")
# Forcing Broadcast Join since the CSV is small (13MB)
df_joined = broadcast(df_csv).join(
    df_silver,
    (col("ID_DOMINIO") == col("silver_idpa")) &
    (col("IUV") == col("silver_iuv")),
    how="left"
)

print("Step 4: Formatting final schema...")
df_final = df_joined.select(
    df_csv["*"], 
    col("PAYMENT_ID")
)

print(f"Step 5: Writing the enriched output to {output_csv_dir}...")
# coalesce(1) forces Spark to output a single CSV file instead of multiple small partitions
df_final.coalesce(1).write \
    .mode("overwrite") \
    .option("header", "true") \
    .option("sep", ";") \
    .csv(output_csv_dir)

print("CDE JOB COMPLETED SUCCESSFULLY!")