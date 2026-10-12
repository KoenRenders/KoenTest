"""The code lists the sales domain owns (CR-21): none yet.

An order's payment status comes from `payment`, its delivery status from its
lines (`sales_order_lines.delivered_at`, F5), and its `unit_code` is a UN/ECE
unit of measure somebody else owns (B3a). So `sales` owns no code list of its
own; this file stands so the domain keeps the package shape (CR-13 §B4.5).
"""
