import tempfile
import unittest
from pathlib import Path

from sum_gpd_items import sum_configured_items


class SumGpdItemsTests(unittest.TestCase):
    def test_sums_only_matching_response_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "gpd-send.log"
            log_path.write_text(
                "INFO Batch 1 response body: Configuration completed for 32 items\n"
                "INFO Batch 2 response body: Configuration completed for 11 items\n"
                "ERROR response body: service unavailable\n"
                "INFO response body: Configuration completed for many items\n",
                encoding="utf-8",
            )

            self.assertEqual(sum_configured_items(log_path), (43, 2))


if __name__ == "__main__":
    unittest.main()
