from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


class Supplier(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    company = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    low_stock_threshold = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name or self.user.username


class Product(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    sku = models.CharField(max_length=40, unique=True, blank=True, null=True)
    price = models.FloatField(default=0, validators=[MinValueValidator(0)])
    quantity = models.IntegerField(validators=[MinValueValidator(0)])
    reorder_level = models.IntegerField(validators=[MinValueValidator(0)])
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL)
    last_low_stock_notification = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.sku:
            base = "".join(ch for ch in self.name.upper() if ch.isalnum())[:8] or "PRODUCT"
            self.sku = f"{base}-{self.category[:3].upper()}"
        super().save(*args, **kwargs)


class StockMovement(models.Model):
    MOVEMENT_TYPES = (
        ("in", "Stock In"),
        ("out", "Stock Out"),
        ("adjust", "Adjustment"),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL)
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.movement_type} ({self.quantity})"


class AuditLog(models.Model):
    EVENT_TYPES = (
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("login", "Login"),
        ("alert", "Alert"),
    )

    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    target = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} - {self.target}"