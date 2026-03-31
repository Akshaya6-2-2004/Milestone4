from django import forms
from .models import Product, Supplier, StockMovement

class ProductForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        quantity = cleaned.get('quantity', 0)
        reorder = cleaned.get('reorder_level', 0)
        if reorder and quantity is not None and reorder > quantity * 5:
            self.add_error('reorder_level', 'Reorder level looks too high compared to quantity.')
        return cleaned

    class Meta:
        model = Product
        fields = '__all__'


class SupplierProfileForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'company', 'phone', 'email', 'low_stock_threshold']


class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ['product', 'movement_type', 'quantity', 'note']