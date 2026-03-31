from django.contrib import admin
from .models import Product, Supplier, StockMovement, AuditLog

admin.site.register(Product)
admin.site.register(Supplier)
admin.site.register(StockMovement)
admin.site.register(AuditLog)