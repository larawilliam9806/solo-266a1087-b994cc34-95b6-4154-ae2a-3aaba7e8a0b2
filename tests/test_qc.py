import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricing import qc  # noqa: E402


def make_row(row, name, spec, price, refs=None):
    return {
        "row": row, "name": name, "spec": spec, "price": price,
        "refs": refs or {"name": ["1"], "spec": ["2"], "price": ["3"]},
    }


class PositiveDecimalTests(unittest.TestCase):
    def test_accepts_plain_positive_decimals(self):
        for text in ("5", "5.0", "5.00", "0.5", ".5", "120", "0.01", " 3.5 "):
            self.assertTrue(qc.is_positive_decimal(text), text)

    def test_rejects_zero_and_negative(self):
        for text in ("0", "0.0", "0.00", "-1", "-0.5", "+3"):
            self.assertFalse(qc.is_positive_decimal(text), text)

    def test_rejects_non_numeric_and_decorated(self):
        for text in ("", "abc", "5元", "1,000", "1e5", "5.", ".", "面议", "1.2.3"):
            self.assertFalse(qc.is_positive_decimal(text), text)


class CheckRowsTests(unittest.TestCase):
    def test_clean_rows_pass(self):
        rows = [make_row(1, "白砂糖", "一级", "5.00"),
                make_row(2, "红糖", "统货", "1.2")]
        reports, summary = qc.check_rows(rows)
        self.assertEqual([r["issues"] for r in reports], [[], []])
        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["ok"], 2)
        self.assertEqual(summary["anomaly"], 0)

    def test_empty_name_and_spec_flagged(self):
        rows = [make_row(1, "", "", "5.00")]
        reports, summary = qc.check_rows(rows)
        self.assertIn("missing_name", reports[0]["issues"])
        self.assertIn("missing_spec", reports[0]["issues"])
        self.assertEqual(summary["by_type"]["missing_name"], 1)
        self.assertEqual(summary["by_type"]["missing_spec"], 1)

    def test_bad_price_flagged_with_value_in_reason(self):
        rows = [make_row(1, "食盐", "散装", "面议")]
        reports, summary = qc.check_rows(rows)
        self.assertEqual(reports[0]["issues"], ["bad_price"])
        self.assertIn("面议", reports[0]["reasons"][0])
        self.assertEqual(summary["by_type"]["bad_price"], 1)

    def test_empty_price_is_bad_price(self):
        rows = [make_row(1, "食盐", "散装", "")]
        reports, _summary = qc.check_rows(rows)
        self.assertEqual(reports[0]["issues"], ["bad_price"])

    def test_same_key_different_price_flagged_on_both_rows(self):
        rows = [make_row(1, "白砂糖", "一级", "5.00"),
                make_row(2, "红糖", "统货", "1.20"),
                make_row(3, "白砂糖", "一级", "4.80")]
        reports, summary = qc.check_rows(rows)
        self.assertEqual(reports[0]["issues"], ["price_conflict"])
        self.assertEqual(reports[1]["issues"], [])
        self.assertEqual(reports[2]["issues"], ["price_conflict"])
        self.assertEqual(summary["by_type"]["price_conflict"], 2)
        reason = reports[0]["reasons"][0]
        self.assertIn("白砂糖", reason)
        self.assertIn("5.00", reason)
        self.assertIn("4.80", reason)
        self.assertIn("第 1 行", reason)
        self.assertIn("第 3 行", reason)
        # Both rows of the conflict share the same explanation.
        self.assertEqual(reports[0]["reasons"], reports[2]["reasons"])

    def test_same_key_same_price_value_is_not_a_conflict(self):
        rows = [make_row(1, "白砂糖", "一级", "5.00"),
                make_row(2, "白砂糖", "一级", "5.0"),
                make_row(3, "白砂糖", "一级", "5")]
        reports, summary = qc.check_rows(rows)
        self.assertTrue(all(not r["issues"] for r in reports))
        self.assertEqual(summary["status"], "pass")

    def test_key_includes_spec(self):
        rows = [make_row(1, "白砂糖", "一级", "5.00"),
                make_row(2, "白砂糖", "二级", "4.80")]
        reports, _summary = qc.check_rows(rows)
        self.assertTrue(all(not r["issues"] for r in reports))

    def test_empty_name_rows_do_not_form_conflict_keys(self):
        rows = [make_row(1, "", "一级", "5.00"),
                make_row(2, "", "一级", "4.80")]
        reports, summary = qc.check_rows(rows)
        self.assertEqual(summary["by_type"]["price_conflict"], 0)
        self.assertTrue(all("missing_name" in r["issues"] for r in reports))

    def test_empty_spec_still_participates_in_conflicts(self):
        rows = [make_row(1, "红糖", "", "1.20"),
                make_row(2, "红糖", "", "1.00")]
        reports, summary = qc.check_rows(rows)
        self.assertEqual(summary["by_type"]["price_conflict"], 2)
        self.assertTrue(all("price_conflict" in r["issues"] for r in reports))

    def test_refs_are_carried_into_report(self):
        refs = {"name": ["7", "8"], "spec": ["9"], "price": []}
        reports, _summary = qc.check_rows([make_row(1, "糖", "甲", "1", refs)])
        self.assertEqual(reports[0]["refs"], refs)


class ViewRowsTests(unittest.TestCase):
    def test_refs_text_lists_each_column(self):
        text = qc.refs_text({"name": ["1", "6"], "spec": ["2"], "price": ["3"]})
        self.assertEqual(text, "品名:1、6；规格:2；批发价:3")

    def test_refs_text_marks_missing_column(self):
        text = qc.refs_text({"name": [], "spec": ["2"], "price": ["3"]})
        self.assertIn("品名:（无）", text)

    def test_view_rows_adds_display_fields(self):
        reports, _summary = qc.check_rows([make_row(1, "", "一级", "abc")])
        view = qc.view_rows(reports)
        self.assertEqual(view[0]["status_label"], "异常")
        self.assertIn("品名为空", view[0]["reasons_text"])
        self.assertIn("品名为空", view[0]["issue_labels"])
        self.assertTrue(view[0]["refs_text"])


if __name__ == "__main__":
    unittest.main()
