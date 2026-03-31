from django.apps import AppConfig


class StockappConfig(AppConfig):
    name = 'stockapp'

    def ready(self):
        # Pre-create a supplier account with fixed credentials (as requested)
        from django.contrib.auth.models import User
        from django.db.utils import OperationalError, ProgrammingError
        from .models import Supplier

        DEFAULT_SUPPLIERS = [
            {
                'username': 'supplier1',
                'password': 'supplier123',
                'name': 'Default Supplier',
                'company': 'SmartStock Supplies',
                'email': 'supplier1@example.com',
                'phone': '+911234567890',
            }
        ]

        try:
            for s in DEFAULT_SUPPLIERS:
                user, created = User.objects.get_or_create(username=s['username'])
                if created or not user.check_password(s['password']):
                    user.set_password(s['password'])
                user.email = s['email']
                user.save()
                supplier, _ = Supplier.objects.get_or_create(user=user)
                supplier.name = s['name']
                supplier.company = s['company']
                supplier.email = s['email']
                supplier.phone = s['phone']
                supplier.save()
        except (OperationalError, ProgrammingError):
            # DB may not be ready when migrations run
            pass
