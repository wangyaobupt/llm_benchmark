from __future__ import annotations

import unittest

from collections import Counter

from eda.analysis.profile_raw_admission_archive import (
    cad_group,
    histogram_percentile,
    is_cad_code,
    percentile,
)


class RawArchiveEdaTest(unittest.TestCase):
    def test_cad_code_scope_is_coronary_only(self) -> None:
        self.assertTrue(is_cad_code("414.01", 9))
        self.assertTrue(is_cad_code("I21.4", 10))
        self.assertTrue(is_cad_code("I2510", "10"))
        self.assertFalse(is_cad_code("440.20", 9))
        self.assertFalse(is_cad_code("I70.20", 10))
        self.assertFalse(is_cad_code("I10", 10))

    def test_percentile_interpolates_stable_values(self) -> None:
        self.assertEqual(percentile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(percentile([], 0.5), 0.0)

    def test_histogram_percentile_does_not_expand_counts(self) -> None:
        histogram = Counter({0: 50, 2: 45, 100: 5})
        self.assertEqual(histogram_percentile(histogram, 0.50), 0)
        self.assertEqual(histogram_percentile(histogram, 0.95), 2)

    def test_cad_groups_do_not_call_all_angina_acs(self) -> None:
        self.assertEqual(cad_group("410.71", 9), "acute_myocardial_infarction")
        self.assertEqual(cad_group("I21.4", 10), "acute_myocardial_infarction")
        self.assertEqual(cad_group("I20.9", 10), "angina")
        self.assertEqual(
            cad_group("I25.10", 10),
            "chronic_ischemic_or_coronary_atherosclerosis",
        )


if __name__ == "__main__":
    unittest.main()
