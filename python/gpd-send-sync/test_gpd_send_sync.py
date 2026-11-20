import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import gpd_send_sync as app


class GpdSendSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "input.csv"

    def write_csv(self, count=201, header=("noticecode", "creditortaxid"),
                  delimiter=","):
        with self.path.open("w", encoding="utf-8-sig", newline="") as source:
            writer = csv.writer(source, delimiter=delimiter)
            writer.writerow(header)
            for index in range(count):
                writer.writerow([f"{index:018d}", "00347720781"])

    def test_batch_boundaries_mapping_and_leading_zeros(self):
        self.write_csv()
        batches = list(app.read_batches(self.path, "creditortaxid", "noticecode", ","))
        self.assertEqual([len(batch) for batch in batches], [100, 100, 1])
        self.assertEqual(batches[0][0], {
            "organizationFiscalCode": "00347720781", "nav": "000000000000000000"
        })
        self.assertEqual(batches[-1][-1]["nav"], "000000000000000200")

    def test_custom_columns_and_delimiter(self):
        self.write_csv(1, ("notice", "fiscal_code"), ";")
        batches = list(app.read_batches(self.path, "fiscal_code", "notice", ";"))
        self.assertEqual(batches[0][0]["organizationFiscalCode"], "00347720781")

    def test_invalid_csv_is_rejected(self):
        for content in (
            "",
            "noticecode,other\n1,2\n",
            "noticecode,creditortaxid,creditortaxid\n1,2,3\n",
            "noticecode,creditortaxid\n1,\n",
            "noticecode,creditortaxid\n1\n",
            "noticecode,creditortaxid\n1,2,3\n",
            'noticecode,creditortaxid\n"unterminated,2\n',
        ):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises((ValueError, csv.Error)):
                    list(app.read_batches(self.path, "creditortaxid", "noticecode", ","))

    @patch.object(app.http.client, "HTTPSConnection")
    def test_http_request_shape_and_all_2xx_success(self, connection_class):
        batch = [{"organizationFiscalCode": "00347720781", "nav": "0001"}]
        connection = connection_class.return_value
        response = connection.getresponse.return_value
        response.read.return_value = b""
        for status in (200, 202, 204):
            response.status = status
            self.assertEqual(app.send_batch(1, batch, "test-key", 12, False), 1)
        connection_class.assert_called_with("api.platform.pagopa.it", timeout=12)
        args, kwargs = connection.request.call_args
        self.assertEqual(args, ("POST", "/gpd/api/v1/internal/config/send"))
        self.assertEqual(json.loads(kwargs["body"]), batch)
        self.assertEqual(kwargs["headers"], {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": "test-key",
        })
        self.assertEqual(connection.close.call_count, 3)

    @patch.object(app.http.client, "HTTPSConnection")
    def test_response_body_is_logged_at_info(self, connection_class):
        response = connection_class.return_value.getresponse.return_value
        response.status = 200
        response.reason = "OK"
        response.read.return_value = b'{"accepted":1}'
        with self.assertLogs(app.LOGGER, "INFO") as logs:
            app.send_batch(1, [{"nav": "1"}], "", 1, False)
        self.assertIn('response body: {"accepted":1}', "\n".join(logs.output))

    @patch.object(app.http.client, "HTTPSConnection")
    def test_http_errors_and_redirects_are_not_retried(self, connection_class):
        response = connection_class.return_value.getresponse.return_value
        response.read.return_value = b"error details"
        for status in (302, 400, 429, 500):
            with self.subTest(status=status), self.assertLogs(app.LOGGER, "ERROR"):
                response.status = status
                with self.assertRaisesRegex(RuntimeError, str(status)):
                    app.send_batch(1, [{"nav": "1"}], "test-key", 1, False)
        self.assertEqual(connection_class.return_value.request.call_count, 4)
        self.assertEqual(connection_class.return_value.close.call_count, 4)

    @patch.object(app.http.client, "HTTPSConnection")
    def test_transport_failure_closes_connection(self, connection_class):
        connection_class.return_value.request.side_effect = TimeoutError("timed out")
        with self.assertLogs(app.LOGGER, "ERROR"), self.assertRaises(TimeoutError):
            app.send_batch(1, [{"nav": "1"}], "test-key", 1, False)
        connection_class.return_value.close.assert_called_once()

    @patch.object(app, "send_batch", side_effect=RuntimeError("HTTP 500"))
    def test_single_worker_stops_after_first_failure(self, sender):
        self.write_csv(301)
        batches = app.read_batches(self.path, "creditortaxid", "noticecode", ",")
        try:
            with self.assertLogs(app.LOGGER, "WARNING"), self.assertRaises(RuntimeError):
                app.process_batches(batches, 1, "test-key", 1, False)
        finally:
            batches.close()
        sender.assert_called_once()

    @patch.object(app, "send_batch", side_effect=lambda number, batch, *args: len(batch))
    def test_multiple_workers_send_every_record_once(self, sender):
        self.write_csv(1001)
        batches = app.read_batches(self.path, "creditortaxid", "noticecode", ",")
        self.assertEqual(app.process_batches(batches, 3, "test-key", 1, False), (11, 1001))
        calls = sender.call_args_list
        self.assertEqual(sorted(call.args[0] for call in calls), list(range(1, 12)))
        notices = [item["nav"] for call in calls for item in call.args[1]]
        self.assertEqual(len(notices), len(set(notices)))

    @patch.object(app.http.client, "HTTPSConnection")
    def test_dry_run_needs_no_key_and_makes_no_requests(self, connection_class):
        self.write_csv()
        with patch.dict(app.os.environ, {}, clear=True), patch(
            "sys.argv", ["gpd_send_sync.py", str(self.path), "--dry-run"]
        ):
            self.assertEqual(app.main(), 0)
        connection_class.assert_not_called()

    @patch.object(app.http.client, "HTTPSConnection")
    def test_header_only_input_fails_without_sending(self, connection_class):
        self.write_csv(0)
        with patch.dict(app.os.environ, {}, clear=True), patch(
            "sys.argv", ["gpd_send_sync.py", str(self.path)]
        ), self.assertLogs(app.LOGGER, "ERROR"):
            self.assertEqual(app.main(), 1)
        connection_class.assert_not_called()

    @patch.object(app.http.client, "HTTPSConnection")
    def test_subscription_key_is_optional_and_used_when_set(self, connection_class):
        self.write_csv(1)
        response = connection_class.return_value.getresponse.return_value
        response.status = 204
        response.read.return_value = b""

        for environment, expected_headers in (
            ({}, {"Content-Type": "application/json"}),
            (
                {"SUBSCRIPTION_KEY": "test-key"},
                {
                    "Content-Type": "application/json",
                    "Ocp-Apim-Subscription-Key": "test-key",
                },
            ),
        ):
            with self.subTest(environment=environment), patch.dict(
                app.os.environ, environment, clear=True
            ), patch("sys.argv", ["gpd_send_sync.py", str(self.path)]):
                self.assertEqual(app.main(), 0)
                self.assertEqual(
                    connection_class.return_value.request.call_args.kwargs["headers"],
                    expected_headers,
                )

    @patch.object(app.http.client, "HTTPSConnection")
    def test_invalid_key_is_rejected_without_logging_it(self, connection_class):
        key = "test-secret\ninvalid-header"
        with patch.dict(app.os.environ, {"SUBSCRIPTION_KEY": key}), patch(
            "sys.argv", ["gpd_send_sync.py", str(self.path)]
        ), self.assertLogs(app.LOGGER, "ERROR") as logs:
            self.assertEqual(app.main(), 1)
        self.assertNotIn("test-secret", "\n".join(logs.output))
        connection_class.assert_not_called()

    def test_invalid_cli_limits(self):
        for option, value in (
            ("--workers", "0"), ("--workers", "-1"),
            ("--timeout", "0"), ("--timeout", "nan"), ("--timeout", "inf"),
        ):
            with self.subTest(option=option, value=value), patch(
                "sys.argv", ["gpd_send_sync.py", "input.csv", option, value]
            ), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                app.parse_args()
            self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
