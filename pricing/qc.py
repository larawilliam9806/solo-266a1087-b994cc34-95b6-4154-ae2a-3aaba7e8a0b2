"""Quality verification of the three-column price-list result.

Pure logic, no Flask/SQLite: given the detailed rows produced by
``layout.build_rows_detailed`` (name / spec / price plus the source box refs
of each column), flag

  * 品名为空            missing_name
  * 规格为空            missing_spec
  * 批发价不是正十进制  bad_price
  * 同键不同价          price_conflict  (same 品名+规格 key, different prices)

The web layer saves the returned report once and serves both the page and
the CSV download from that single saved state.
"""

from __future__ import annotations

import re

from .layout import COLUMN_LABELS, COLUMNS

# A plain positive decimal: digits with an optional fractional part (".5"
# allowed).  No sign, no exponent, no thousands separators, no units.
PRICE_RE = re.compile(r"(?:\d+(?:\.\d+)?|\.\d+)")

ISSUE_ORDER = ("missing_name", "missing_spec", "bad_price", "price_conflict")
ISSUE_LABELS = {
    "missing_name": "品名为空",
    "missing_spec": "规格为空",
    "bad_price": "批发价非正十进制",
    "price_conflict": "同键不同价",
}

ROW_STATUS_LABELS = {True: "正常", False: "异常"}
TASK_STATUS_LABELS = {"pass": "核验通过", "fail": "核验未通过"}


def is_positive_decimal(text):
    """True when the text is exactly a positive decimal number."""
    stripped = (text or "").strip()
    if not PRICE_RE.fullmatch(stripped):
        return False
    return float(stripped) > 0


def _price_group_key(text):
    """Grouping key for price comparison.

    Valid decimals compare by value ("5" == "5.0" == "5.00"); anything else
    compares by its raw stripped text.
    """
    stripped = (text or "").strip()
    if is_positive_decimal(stripped):
        return ("num", float(stripped))
    return ("raw", stripped)


def check_rows(rows):
    """Verify detailed rows, returning (report_rows, summary).

    Each report row keeps the row data and gains ``issues`` (type keys) and
    ``reasons`` (human-readable Chinese explanations).
    """
    reports = []
    for row in rows:
        name = row["name"]
        spec = row["spec"]
        price = row["price"]
        issues = []
        reasons = []
        if not name.strip():
            issues.append("missing_name")
            reasons.append(ISSUE_LABELS["missing_name"])
        if not spec.strip():
            issues.append("missing_spec")
            reasons.append(ISSUE_LABELS["missing_spec"])
        if not is_positive_decimal(price):
            issues.append("bad_price")
            if price.strip():
                reasons.append(f"批发价“{price.strip()}”不是正十进制")
            else:
                reasons.append("批发价为空，不是正十进制")
        reports.append({
            "row": row["row"],
            "name": name,
            "spec": spec,
            "price": price,
            "refs": row.get("refs", {}),
            "issues": issues,
            "reasons": reasons,
        })

    # Same key (品名 + 规格) but different prices.  Rows without a 品名 cannot
    # form a meaningful key and are already flagged, so they stay out.
    groups = {}
    for report in reports:
        if not report["name"].strip():
            continue
        key = (report["name"].strip(), report["spec"].strip())
        groups.setdefault(key, []).append(report)

    for (name, spec), members in groups.items():
        by_price = {}
        for member in members:
            by_price.setdefault(_price_group_key(member["price"]), []).append(member)
        if len(by_price) < 2:
            continue
        variants = []
        for group_members in by_price.values():
            rows_text = "、".join(str(item["row"]) for item in group_members)
            shown = group_members[0]["price"].strip() or "（空）"
            variants.append(f"{shown}（第 {rows_text} 行）")
        spec_text = spec if spec else "（规格空）"
        reason = f"同键不同价：「{name} / {spec_text}」价格不一致：" + "；".join(variants)
        for member in members:
            member["issues"].append("price_conflict")
            member["reasons"].append(reason)

    by_type = {key: 0 for key in ISSUE_ORDER}
    anomaly = 0
    for report in reports:
        if report["issues"]:
            anomaly += 1
        for issue in report["issues"]:
            by_type[issue] += 1
    status = "fail" if anomaly else "pass"
    summary = {
        "rows": len(reports),
        "ok": len(reports) - anomaly,
        "anomaly": anomaly,
        "by_type": by_type,
        "status": status,
        "status_label": TASK_STATUS_LABELS[status],
    }
    return reports, summary


def refs_text(refs):
    """Compact per-column source-box list, e.g. 品名:1、6；规格:2；批发价:3."""
    parts = []
    for column in COLUMNS:
        box_refs = (refs or {}).get(column) or []
        shown = "、".join(str(ref) for ref in box_refs) if box_refs else "（无）"
        parts.append(f"{COLUMN_LABELS[column]}:{shown}")
    return "；".join(parts)


def row_status_label(report_row):
    return ROW_STATUS_LABELS[not report_row["issues"]]


def view_rows(report_rows):
    """Display-ready copies of the saved report rows (page and CSV share them)."""
    output = []
    for report in report_rows:
        row = dict(report)
        row["ok"] = not report["issues"]
        row["status_label"] = row_status_label(report)
        row["reasons_text"] = "；".join(report["reasons"])
        row["issue_labels"] = [ISSUE_LABELS[issue] for issue in report["issues"]]
        row["refs_text"] = refs_text(report.get("refs"))
        output.append(row)
    return output
