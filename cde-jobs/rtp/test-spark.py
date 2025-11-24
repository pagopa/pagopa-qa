from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("test_rtp_access").enableHiveSupport().getOrCreate()

df = spark.table("pagopa_dev.rtp_pt_report").limit(10)
df.show(truncate=False)

spark.stop()