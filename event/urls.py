from django.urls import path
from . import views

app_name = 'event'

urlpatterns = [
    path('', views.events_list_view, name='events'),
    path('<int:pk>', views.event_detail_views, name='event-detail'),
    path('results/<int:pk>', views.results_view, name='results'),
    path('events-by-year/<int:pk>', views.events_list_by_year_view, name='events-by-year'),
    path('emtry-riders/<int:pk>', views.entry_riders_view, name='entry-riders'),
    path('entry/<int:pk>', views.add_entries_view, name='entry'),
    path('entry-foreign/<int:pk>', views.entry_foreign_view, name='entry-foreign'),
    path('confirm', views.confirm_view, name='confirm'),
    path('order', views.confirm_user_order, name='order'),
    path('success', views.check_order_payments, name="check-payments"),
    path('success/<int:pk>', views.success_view, name='success'),
    path('cancel', views.cancel_view, name='cancel'),
    path('event-admin/<int:pk>', views.event_admin_view, name='event-admin'),
    path('find-payment', views.find_payment_view, name='find-payment'),
    path('ranking-table', views.ranking_table_view, name='ranking-table'),
    path('entry-foreign/<int:pk>', views.entry_foreign_view, name='entry-foreign'),
    path('ec_by_club_xls/<int:pk>', views.ec_by_club_xls, name='ec_by_club_xls'),
    path('summary_riders_in_event/<int:pk>', views.summary_riders_in_event, name='summary_riders_in_event'),
    path('checkout', views.checkout_view, name='checkout'),
    path('fees-on-event/<int:pk>', views.fees_on_event, name='fees-on-event'),
    path('credit', views.credit_view, name='credit'),
    path("stripe-credit-webhook/", views.stripe_credit_webhook, name="stripe-credit-webhook"),
    path('success-credit', views.success_credit_view, name='success-credit'),
    path('success-credit-update', views.success_credit_update_view, name='success-credit-update'),
    path('not-reg', views.not_reg_view, name='not-reg'),
    path('check-rider/', views.check_rider, name='check-rider'),
    path('generate_pdf/<int:pk>', views.generate_pdf, name='generate_pdf'),
    path('generate_invoice_preparation_pdf/<int:pk>', views.generate_invoice_preparation_pdf, name='generate_invoice_preparation_pdf'),
    path('generate_invoices_pdf/<int:pk>', views.invoice_view, name='generate_invoices_pdf'),
    path('recalculate_balances_view', views.recalculate_balances_view, name='recalculate_balances_view'),
    path("export-results/<int:event_id>/", views.export_event_results, name="export_event_results"),
]
