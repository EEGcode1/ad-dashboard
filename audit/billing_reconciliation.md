# Billing reconciliation

Output of `parsers/billing_cross_check.py`, run monthly.

Compares daily-scraped GGR × rev share (from `data/history/*.json`) against
the actual invoiced / paid totals in JP's billing emails and LNW's billing
statements. Any per-source delta > 1% is flagged for manual review.

_(First real run pending — this file is a placeholder.)_
