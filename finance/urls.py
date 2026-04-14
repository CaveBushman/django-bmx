from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_admin, name='finance' ),
    path('audit/', views.finance_audit_dashboard, name='finance_audit'),
    path('checkout-refunds.csv', views.export_checkout_refunds_csv, name='export_checkout_refunds_csv'),
]
