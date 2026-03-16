"""
event/views/__init__.py — re-exportuje všechny views

Rozdělení do souborů:
  views_public.py   — veřejné pohledy (seznam závodů, detail, výsledky)
  views_entry.py    — přihlašování jezdců na závody
  views_payment.py  — Stripe platby, kredit, košík
  views_admin.py    — admin panel, exporty, výsledky, API ČSC
  views_pdf.py      — generování PDF dokumentů

urls.py stále importuje `from . import views` a `views.function_name` — beze změny.
"""

from event.views.views_public import (
    events_list_view,
    events_list_by_year_view,
    event_detail_views,
    results_view,
    ranking_table_view,
    not_reg_view,
)

from event.views.views_entry import (
    add_entries_view,
    entry_riders_view,
    confirm_view,
    entry_foreign_view,
    entry_foreign_summary_view,
    entry_foreign_pay_view,
    entry_foreign_success_view,
    check_rider,
    fees_on_event,
    invoice_edit_view,
    invoice_delete_view,
    cash_receipts_on_event,
    cash_receipts_export_view,
    cash_receipt_pdf_view,
    cash_receipt_edit_view,
    cash_receipt_delete_view,
)

from event.views.views_payment import (
    success_view,
    cancel_view,
    stripe_credit_webhook,
    confirm_user_order,
    check_order_payments,
    checkout_view,
    credit_view,
    success_credit_view,
    success_credit_update_view,
    recalculate_balances_view,
)

from event.views.views_admin import (
    event_admin_view,
    commissar_assignments_view,
    commissar_statistics_view,
    find_payment_view,
    ec_by_club_xls,
    summary_riders_in_event,
    export_event_results,
    send_invoices,
    price_money_pdf,
)

from event.views.views_pdf import (
    generate_pdf,
    generate_invoice_preparation_pdf,
    invoice_view,
)
