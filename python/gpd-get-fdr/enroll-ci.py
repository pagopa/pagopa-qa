import requests
from collections import defaultdict
import os

# === Config ===
API_URL_TEMPLATE = "https://api.platform.pagopa.it/gps/gpd-reporting-orgs-enrollment/api/v1/organizations/{}"
SUBSCRIPTION_KEY = os.getenv("ENROLL_SUB_KEY")
INPUT_FILE = "taxcodes.txt"
FR_BASE_DIR: str = os.environ.get("GITHUB_WORKSPACE")
file_path = FR_BASE_DIR + "/python/gpd-get-fdr/config/" + INPUT_FILE

# === Init response counter ===
response_counts = defaultdict(int)

# === Load tax codes from file ===
with open(file_path, "r") as f:
    tax_codes = [line.strip() for line in f if line.strip()]

# === Process each tax code ===
for tax_code in tax_codes:
    url = API_URL_TEMPLATE.format(tax_code)
    try:
        response = requests.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY},
            timeout=10
        )
        response_counts[response.status_code] += 1
        print(f"[{response.status_code}] Tax code: {tax_code}")
    except requests.RequestException as e:
        print(f"[ERROR] Tax code: {tax_code} => {e}")
        response_counts["error"] += 1

# === Final summary ===
print("\n=== HTTP Response Code Summary ===")
for code, count in response_counts.items():
    print(f"{code}: {count}")