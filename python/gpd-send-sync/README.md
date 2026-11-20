# GPD send sync

Read a CSV file and send notices to the **production** endpoint:

```text
POST https://api.platform.pagopa.it/gpd/api/v1/internal/config/send
Content-Type: application/json
```

The `Ocp-Apim-Subscription-Key` header is sent only when `SUBSCRIPTION_KEY` is
set in the environment. If the variable is missing or empty, the request is
sent without that header.

Requires **Python 3.9+**. Uses only the standard library; no packages to install.
Run the following commands from this directory.

## Input and mapping

The default input is a comma-separated UTF-8 CSV with a header (BOM supported):

```csv
noticecode,creditortaxid
304202600010050400,00347720781
```

Additional columns are ignored. Each request body is a JSON array with at most
**100 items**; the final batch contains the remaining records:

```json
[{"organizationFiscalCode": "00347720781", "nav": "304202600010050400"}]
```

- `creditortaxid` -> `organizationFiscalCode`
- `noticecode` -> `nav`

Values remain strings, preserving leading zeros. Surrounding whitespace is removed.
Missing/duplicate selected headers, invalid CSV, inconsistent column counts,
empty selected values and files without data cause an error; no records are
silently skipped or deduplicated.

## Usage

First validate the entire input **without making any HTTP requests**:

```bash
python3 gpd_send_sync.py MigrazioneSynch-Asynch_202611161018.csv --dry-run
```

The subscription key is optional. If the service requires one, set it in the
environment (never place a real key in source control):

```bash
export SUBSCRIPTION_KEY='<your-subscription-key>'
python3 gpd_send_sync.py MigrazioneSynch-Asynch_202611161018.csv \
  --log-file gpd-send.log
unset SUBSCRIPTION_KEY
```

The variable is named `SUBSCRIPTION_KEY` (with the second `S`), not
`SUBCRIPTION_KEY`. It is never intentionally logged.

Custom CSV headers, separator and parallelism:

```bash
python3 gpd_send_sync.py input.csv \
  --organization-field fiscal_code \
  --notice-field notice \
  --delimiter ';' \
  --workers 4 \
  --timeout 90
```

| Option | Default | Description |
| --- | --- | --- |
| `csv_file` | Required | Path to the CSV file |
| `--organization-field` | `creditortaxid` | Organization fiscal code column |
| `--notice-field` | `noticecode` | Notice code column |
| `--delimiter` | `,` | Single-character CSV separator |
| `--workers` | `1` | Positive number of thread pool workers |
| `--timeout` | `60` | Positive, finite socket timeout in seconds (not an overall run deadline) |
| `--dry-run` | Disabled | Read, validate and build batches without sending |
| `--log-level` | `INFO` | `INFO` or `DEBUG` |
| `--log-file` | None | Append logs to a file, in addition to stderr |

Use `--help` to display CLI help.

## Summing configured items from a log

`sum_gpd_items.py` sums the counts from lines matching
`response body: Configuration completed for <n> items` and reports both the
total and the number of matching responses:

```bash
python3 sum_gpd_items.py
```

By default, the script reads `gpd-send.log` next to itself. You can pass another
log file as an argument:

```bash
python3 sum_gpd_items.py path/to/another.log
```

Example output:

```text
Totale item configurati: 125144 (risposte conteggiate: 3420)
```

## Logging and failure handling

Logs and exception traces are in English. INFO logs include timestamps, thread
names, batch numbers, CSV record ranges (excluding the header), item counts,
HTTP status, response body, elapsed time and a final summary. DEBUG also includes
the complete request body:

```bash
python3 gpd_send_sync.py MigrazioneSynch-Asynch_202611161018.csv \
  --dry-run --log-level DEBUG --log-file preview.log
```

**Logs contain the CSV identifiers and may contain sensitive response data:
restrict access and retention.** The subscription header is not included in
request logs.

The CSV is read in streaming mode, with at most one in-flight batch per worker.
With one worker requests follow CSV order. With multiple workers completion
order is not guaranteed.

Any non-2xx response (including redirects), transport error or invalid record
stops submission of new batches once detected. Already running requests are
allowed to finish and queued work is cancelled where possible. Validation is
streaming: an invalid record late in the file can be discovered after earlier
batches have been sent. Run `--dry-run` first against the same, unchanged input.

There are **no automatic retries, rollback, checkpoints or automatic resume**.
A timeout/disconnection can happen after the server accepted a batch. On failure,
inspect batch logs and reconcile with the service before rerunning: rerunning
the whole CSV may resend accepted notices. Do not assume the API is idempotent.
HTTP success only confirms the service returned a 2xx status, not downstream
processing completion.

Exit codes: `0` success, `1` processing/configuration error, `2` invalid CLI
arguments, `130` user interruption.

## Local tests

Tests use mocked HTTP connections and never call production:

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```
