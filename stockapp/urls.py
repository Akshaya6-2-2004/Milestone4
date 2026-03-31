from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/supplier/', views.supplier_dashboard, name='supplier_dashboard'),
    path('admin-login/', views.login_view, {'user_type': 'admin'}, name='admin_login'),
    path('supplier-login/', views.login_view, {'user_type': 'supplier'}, name='supplier_login'),
    path('supplier/profile/', views.supplier_profile, name='supplier_profile'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, {'user_type': 'admin'}, name='register'),
    path('supplier-register/', views.register_view, {'user_type': 'supplier'}, name='supplier_register'),
    path('add/', views.add_product, name='add_product'),
    path('stock-movement/add/', views.add_stock_movement, name='add_stock_movement'),
    path('products/', views.product_list, name='product_list'),
    path('products/update/<int:pk>/', views.update_product, name='update_product'),
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/sales/', views.download_sales_report, name='download_sales_report'),
    path('reports/purchase/', views.download_purchase_report, name='download_purchase_report'),
    path('reports/stock-summary/', views.download_stock_summary_report, name='download_stock_summary_report'),
    path('reports/invoice/<int:movement_id>/', views.generate_invoice_pdf, name='generate_invoice_pdf'),
    path('api/dashboard-summary/', views.api_dashboard_summary, name='api_dashboard_summary'),
    path('api/low-stock-alerts/', views.api_low_stock_alerts, name='api_low_stock_alerts'),
]