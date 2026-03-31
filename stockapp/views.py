from django.shortcuts import render, redirect, get_object_or_404
from .models import Product, Supplier, StockMovement, AuditLog
from .forms import ProductForm, SupplierProfileForm, StockMovementForm
from django.db import models
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET
from django.utils import timezone
from datetime import timedelta
from io import BytesIO
import csv
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    A4 = None
    canvas = None
    REPORTLAB_AVAILABLE = False


def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    primary = request.GET.get('primary', 'supplier').strip().lower()
    if primary not in ('supplier', 'admin'):
        primary = 'supplier'
    alternate = 'admin' if primary == 'supplier' else 'supplier'
    return render(request, 'home.html', {'primary_portal': primary, 'alternate_portal': alternate})


def get_dashboard_name(user):
    if hasattr(user, 'supplier'):
        return 'supplier_dashboard'
    return 'admin_dashboard'


def log_audit(event_type, target, actor=None, details=''):
    try:
        AuditLog.objects.create(
            event_type=event_type,
            target=target,
            actor=actor if actor and actor.is_authenticated else None,
            details=details,
        )
    except Exception:
        pass


def login_view(request, user_type='admin'):
    if request.user.is_authenticated:
        return redirect(get_dashboard_name(request.user))
    error = ''
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        user = None

        if user_type == 'supplier':
            email = request.POST.get('email', '').strip()
            supplier = Supplier.objects.select_related('user').filter(email__iexact=email).first()
            if supplier:
                user = authenticate(request, username=supplier.user.username, password=password)
        else:
            username = request.POST.get('username', '').strip()
            user = authenticate(request, username=username, password=password)

        if user:
            if user_type == 'admin' and not user.is_staff:
                error = 'Admin login requires staff privileges.'
            elif user_type == 'supplier' and not hasattr(user, 'supplier'):
                error = 'The account is not configured as a supplier.'
            else:
                login(request, user)
                log_audit('login', f'{user_type} login', actor=user, details=f'User: {user.username}')
                return redirect(get_dashboard_name(user))
        else:
            error = 'Invalid username or password.'

    return render(request, 'login.html', {'user_type': user_type, 'error': error})


@login_required(login_url='supplier_login')
def supplier_profile(request):
    if not hasattr(request.user, 'supplier'):
        messages.error(request, 'Please login as a supplier to view this page.')
        return redirect('supplier_login')

    supplier = request.user.supplier
    products = Product.objects.filter(supplier=supplier).order_by('-id')

    if request.method == 'POST':
        form = SupplierProfileForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('supplier_profile')
    else:
        form = SupplierProfileForm(instance=supplier)

    return render(request, 'supplier_profile.html', {'supplier': supplier, 'products': products, 'form': form})


def send_low_stock_notifications(user):
    if not hasattr(user, 'supplier'):
        return

    supplier = user.supplier
    alert_products = Product.objects.filter(supplier=supplier)
    now = timezone.now()
    for product in alert_products:
        # Use supplier-level threshold from profile when configured.
        threshold = supplier.low_stock_threshold if supplier.low_stock_threshold > 0 else product.reorder_level
        status = 'optimal'
        if threshold > 0:
            if product.quantity <= threshold * 0.5:
                status = 'critical'
            elif product.quantity <= threshold:
                status = 'low'

        if status in ('low', 'critical'):
            should_notify = True
            if product.last_low_stock_notification:
                diff = now - product.last_low_stock_notification
                if diff < timedelta(hours=24):
                    should_notify = False

            if should_notify and supplier.email:
                try:
                    send_mail(
                        subject=f'Low Stock Alert: {product.name}',
                        message=(
                            f'Hello {supplier.name},\n\n'
                            f'The product "{product.name}" is in {status} stock status.\n'
                            f'Current quantity: {product.quantity}\n'
                            f'Alert threshold: {threshold}\n\n'
                            'Please restock as soon as possible.\n\n'
                            'Regards,\nSmartStock'
                        ),
                        from_email=None,
                        recipient_list=[supplier.email],
                    )
                    product.last_low_stock_notification = now
                    product.save(update_fields=['last_low_stock_notification'])
                    log_audit('alert', product.name, actor=user, details=f'{status} stock email sent to {supplier.email}')
                except Exception:
                    # In dev, we may not have email configured; ignore so page still works
                    pass


def register_view(request, user_type='admin'):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = ''
    success = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        confirm = request.POST.get('confirm_password', '').strip()
        if not username or not password:
            error = 'Username and password are required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif User.objects.filter(username=username).exists():
            error = 'Username already exists.'
        else:
            user = User.objects.create_user(username=username, password=password)
            if user_type == 'supplier':
                email = request.POST.get('email', '').strip()
                name = request.POST.get('name', '').strip() or username
                company = request.POST.get('company', '').strip()
                phone = request.POST.get('phone', '').strip()
                if not email:
                    user.delete()
                    error = 'Email is required for supplier registration.'
                elif Supplier.objects.filter(email__iexact=email).exists():
                    user.delete()
                    error = 'This supplier email is already registered.'
                else:
                    user.email = email
                    user.save(update_fields=['email'])
                    Supplier.objects.create(
                        user=user,
                        name=name,
                        company=company,
                        phone=phone,
                        email=email,
                    )
                    success = 'Supplier registration successful. Please login.'
                    log_audit('create', f'Supplier:{name}', actor=user, details='Supplier self-registration')
            else:
                success = 'Registration successful. Please login.'
                log_audit('create', f'User:{username}', actor=user, details='Admin registration')
    return render(request, 'register.html', {'error': error, 'success': success, 'user_type': user_type})


def logout_view(request):
    logout(request)
    return redirect('home')


def get_status(quantity, reorder_level):
    if reorder_level <= 0:
        return 'optimal'
    if quantity <= reorder_level * 0.5:
        return 'critical'
    if quantity <= reorder_level:
        return 'low'
    if quantity > reorder_level * 3:
        return 'overstock'
    return 'optimal'


def build_products(products):
    out = []
    for p in products:
        status = get_status(p.quantity, p.reorder_level)
        out.append({
            'id': p.id,
            'name': p.name,
            'sku': f'SKU-{p.id:04d}',
            'category': p.category,
            'price': p.price,
            'quantity': p.quantity,
            'reorder': p.reorder_level,
            'status': status,
            'value': round(p.quantity * p.price, 2),
        })
    return out


def build_dashboard_context(products, search=''):
    rows = build_products(products)

    total_products = products.count()
    total_stock = products.aggregate(total=models.Sum('quantity'))['total'] or 0
    low_stock_count = sum(1 for r in rows if r['status'] in ('low', 'critical'))
    critical_count = sum(1 for r in rows if r['status'] == 'critical')

    category_stats = []
    category_sum = {}
    status_counters = {'optimal': 0, 'low': 0, 'critical': 0, 'overstock': 0}
    for r in rows:
        category_sum[r['category']] = category_sum.get(r['category'], 0) + r['quantity']
        status_counters[r['status']] += 1

    category_stats = [{'name': k, 'stock': v} for k, v in category_sum.items()]
    if not category_stats:
        category_stats = [{'name': 'Beverages', 'stock': 1}, {'name': 'Grains', 'stock': 1}]

    alerts = []
    for r in rows:
        if r['status'] in ('low', 'critical'):
            alerts.append({
                'name': r['name'],
                'message': f'Below reorder point ({r["reorder"]})',
                'action': f'Order {max(1, r["reorder"] * 2 - r["quantity"])} units',
                'type': r['status'],
            })
    if not alerts:
        alerts = [{'name': 'Inventory healthy', 'message': 'No critical alerts', 'action': 'Continue monitoring', 'type': 'optimal'}]

    return {
        'products': rows,
        'total_products': total_products,
        'total_stock': total_stock,
        'low_stock_count': low_stock_count,
        'critical_count': critical_count,
        'category_stats': category_stats,
        'alerts': alerts,
        'status_count': status_counters,
        'search': search,
    }


def build_supplier_notifications(supplier):
    notifications = []
    products = Product.objects.filter(supplier=supplier).order_by('-id')
    for p in products:
        threshold = supplier.low_stock_threshold if supplier.low_stock_threshold > 0 else p.reorder_level
        if threshold <= 0:
            continue
        status = get_status(p.quantity, threshold)
        if status in ('low', 'critical'):
            notifications.append({
                'name': p.name,
                'message': f'Understock: {p.quantity} units (threshold {threshold})',
                'action': 'Reorder soon',
                'type': status,
            })
    return notifications


def parse_date_range(request):
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    movements = StockMovement.objects.select_related('product', 'supplier').order_by('-created_at')
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)
    return movements, date_from, date_to


def build_report_payload(movements):
    sales = movements.filter(movement_type='out')
    purchases = movements.filter(movement_type='in')
    stock = Product.objects.all().order_by('name')
    sales_total_qty = sum(m.quantity for m in sales)
    sales_total_value = round(sum(m.quantity * m.product.price for m in sales), 2)
    purchase_total_qty = sum(m.quantity for m in purchases)
    purchase_total_value = round(sum(m.quantity * m.product.price for m in purchases), 2)
    stock_total_value = round(sum(p.quantity * p.price for p in stock), 2)
    return {
        'sales': sales,
        'purchases': purchases,
        'stock': stock,
        'sales_total_qty': sales_total_qty,
        'sales_total_value': sales_total_value,
        'purchase_total_qty': purchase_total_qty,
        'purchase_total_value': purchase_total_value,
        'stock_total_value': stock_total_value,
    }


def build_pdf_response(filename):
    if not REPORTLAB_AVAILABLE:
        return None, None, None
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    return buffer, pdf, filename


def finalize_pdf_response(buffer, pdf, filename):
    pdf.save()
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def pdf_dependency_response():
    return HttpResponse(
        'PDF generation dependency missing. Install it in your active venv: pip install reportlab',
        status=503,
        content_type='text/plain',
    )


@login_required(login_url='admin_login')
def dashboard(request):
    return redirect(get_dashboard_name(request.user))


@login_required(login_url='admin_login')
def admin_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, 'Admin access required.')
        return redirect('admin_login')
    search = request.GET.get('search', '').strip()
    products = Product.objects.all().order_by('-id')
    if search:
        products = products.filter(models.Q(name__icontains=search) | models.Q(category__icontains=search) | models.Q(price__icontains=search))
    context = build_dashboard_context(products, search)
    context.update({'portal_name': 'Admin Dashboard', 'has_supplier': False})
    return render(request, 'admin_dashboard.html', context)


@login_required(login_url='supplier_login')
def supplier_dashboard(request):
    if not hasattr(request.user, 'supplier'):
        messages.error(request, 'Supplier account required.')
        return redirect('supplier_login')
    send_low_stock_notifications(request.user)
    supplier = request.user.supplier
    search = request.GET.get('search', '').strip()
    products = Product.objects.filter(supplier=supplier).order_by('-id')
    if search:
        products = products.filter(models.Q(name__icontains=search) | models.Q(category__icontains=search) | models.Q(price__icontains=search))
    context = build_dashboard_context(products, search)
    notifications = build_supplier_notifications(supplier)
    low_notifications = [item for item in notifications if item.get('type') == 'low']
    critical_notifications = [item for item in notifications if item.get('type') == 'critical']
    if notifications:
        context['alerts'] = notifications
    context.update({
        'portal_name': 'Supplier Dashboard',
        'has_supplier': True,
        'low_alert_count': len(low_notifications),
        'critical_alert_count': len(critical_notifications),
        'total_supplier_alerts': len(notifications),
    })
    return render(request, 'supplier_dashboard.html', context)


@login_required(login_url='admin_login')
def add_product(request):
    if not request.user.is_staff:
        messages.error(request, 'Only admin can add products.')
        return redirect('supplier_dashboard' if hasattr(request.user, 'supplier') else 'admin_login')
    form = ProductForm(request.POST or None)
    if form.is_valid():
        product = form.save()
        StockMovement.objects.create(
            product=product,
            supplier=product.supplier,
            movement_type='in',
            quantity=max(1, product.quantity),
            note='Initial stock added',
            created_by=request.user,
        )
        log_audit('create', f'Product:{product.name}', actor=request.user, details=f'Qty={product.quantity}')
        messages.success(request, 'Product added successfully.')
        return redirect('admin_dashboard')
    return render(request, 'add_product.html', {'form': form})


@login_required(login_url='admin_login')
def update_product(request, pk):
    if not request.user.is_staff:
        messages.error(request, 'Only admin can update products.')
        return redirect('supplier_dashboard' if hasattr(request.user, 'supplier') else 'admin_login')
    product = get_object_or_404(Product, pk=pk)
    old_qty = product.quantity
    form = ProductForm(request.POST or None, instance=product)
    if form.is_valid():
        updated = form.save()
        if updated.quantity != old_qty:
            diff = updated.quantity - old_qty
            StockMovement.objects.create(
                product=updated,
                supplier=updated.supplier,
                movement_type='in' if diff > 0 else 'out',
                quantity=abs(diff),
                note='Quantity changed from product update',
                created_by=request.user,
            )
        log_audit('update', f'Product:{updated.name}', actor=request.user, details=f'Qty {old_qty}->{updated.quantity}')
        messages.success(request, 'Product details updated.')
        return redirect('product_list')
    return render(request, 'update_product.html', {'form': form, 'product': product})


@login_required(login_url='admin_login')
def product_list(request):
    if not request.user.is_staff:
        messages.error(request, 'Only admin can view full product list.')
        return redirect('supplier_dashboard' if hasattr(request.user, 'supplier') else 'admin_login')
    search = request.GET.get('search', '').strip()
    products = Product.objects.all().order_by('-id')
    if search:
        products = products.filter(models.Q(name__icontains=search) | models.Q(category__icontains=search) | models.Q(price__icontains=search))
    rows = build_products(products)
    return render(request, 'product_list.html', {'products': rows, 'search': search})


@login_required(login_url='admin_login')
def add_stock_movement(request):
    if not request.user.is_staff:
        return redirect('admin_login')
    form = StockMovementForm(request.POST or None)
    if form.is_valid():
        movement = form.save(commit=False)
        movement.created_by = request.user
        movement.supplier = movement.product.supplier
        movement.save()
        if movement.movement_type == 'in':
            movement.product.quantity += movement.quantity
        elif movement.movement_type == 'out':
            movement.product.quantity = max(0, movement.product.quantity - movement.quantity)
        movement.product.save(update_fields=['quantity'])
        log_audit('update', f'StockMovement:{movement.product.name}', actor=request.user, details=f'{movement.movement_type}:{movement.quantity}')
        messages.success(request, 'Stock movement saved.')
        return redirect('admin_dashboard')
    return render(request, 'add_product.html', {'form': form})


@login_required(login_url='admin_login')
@require_GET
def api_dashboard_summary(request):
    if hasattr(request.user, 'supplier'):
        products = Product.objects.filter(supplier=request.user.supplier)
    else:
        products = Product.objects.all()
    rows = build_products(products)
    data = {
        'total_products': len(rows),
        'total_stock': sum(r['quantity'] for r in rows),
        'low_stock_count': sum(1 for r in rows if r['status'] in ('low', 'critical')),
        'critical_count': sum(1 for r in rows if r['status'] == 'critical'),
    }
    return JsonResponse(data)


@login_required(login_url='admin_login')
@require_GET
def api_low_stock_alerts(request):
    if hasattr(request.user, 'supplier'):
        supplier = request.user.supplier
        alerts = build_supplier_notifications(supplier)
    else:
        rows = build_products(Product.objects.all())
        alerts = [
            {'name': r['name'], 'status': r['status'], 'quantity': r['quantity'], 'reorder_level': r['reorder']}
            for r in rows if r['status'] in ('low', 'critical')
        ]
    return JsonResponse({'alerts': alerts})


@login_required(login_url='admin_login')
def reports_dashboard(request):
    if not request.user.is_staff:
        messages.error(request, 'Only admin can access reports.')
        return redirect('admin_login')
    movements, date_from, date_to = parse_date_range(request)
    payload = build_report_payload(movements)
    payload.update({'date_from': date_from, 'date_to': date_to})
    return render(request, 'reports.html', payload)


@login_required(login_url='admin_login')
def download_sales_report(request):
    if not request.user.is_staff:
        return redirect('admin_login')
    fmt = request.GET.get('format', 'csv').lower()
    movements, _, _ = parse_date_range(request)
    sales = movements.filter(movement_type='out')
    if fmt == 'pdf':
        buffer, pdf, filename = build_pdf_response('sales_report.pdf')
        if not buffer:
            return pdf_dependency_response()
        y = 800
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "Sales Report")
        y -= 30
        pdf.setFont("Helvetica", 10)
        for row in sales:
            line = f'{row.created_at:%Y-%m-%d} | {row.product.name} | Qty: {row.quantity} | Value: {row.quantity * row.product.price:.2f}'
            pdf.drawString(40, y, line[:110])
            y -= 18
            if y < 60:
                pdf.showPage()
                y = 800
                pdf.setFont("Helvetica", 10)
        return finalize_pdf_response(buffer, pdf, filename)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Product', 'SKU', 'Quantity', 'Unit Price', 'Value', 'Supplier'])
    for row in sales:
        writer.writerow([row.created_at.date(), row.product.name, row.product.sku, row.quantity, row.product.price, row.quantity * row.product.price, row.supplier.name if row.supplier else ''])
    return response


@login_required(login_url='admin_login')
def download_purchase_report(request):
    if not request.user.is_staff:
        return redirect('admin_login')
    fmt = request.GET.get('format', 'csv').lower()
    movements, _, _ = parse_date_range(request)
    purchases = movements.filter(movement_type='in')
    if fmt == 'pdf':
        buffer, pdf, filename = build_pdf_response('purchase_report.pdf')
        if not buffer:
            return pdf_dependency_response()
        y = 800
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "Purchase Report")
        y -= 30
        pdf.setFont("Helvetica", 10)
        for row in purchases:
            line = f'{row.created_at:%Y-%m-%d} | {row.product.name} | Qty: {row.quantity} | Cost: {row.quantity * row.product.price:.2f}'
            pdf.drawString(40, y, line[:110])
            y -= 18
            if y < 60:
                pdf.showPage()
                y = 800
                pdf.setFont("Helvetica", 10)
        return finalize_pdf_response(buffer, pdf, filename)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="purchase_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Product', 'SKU', 'Quantity', 'Unit Price', 'Value', 'Supplier'])
    for row in purchases:
        writer.writerow([row.created_at.date(), row.product.name, row.product.sku, row.quantity, row.product.price, row.quantity * row.product.price, row.supplier.name if row.supplier else ''])
    return response


@login_required(login_url='admin_login')
def download_stock_summary_report(request):
    if not request.user.is_staff:
        return redirect('admin_login')
    fmt = request.GET.get('format', 'csv').lower()
    stock = Product.objects.select_related('supplier').all().order_by('name')
    if fmt == 'pdf':
        buffer, pdf, filename = build_pdf_response('stock_summary_report.pdf')
        if not buffer:
            return pdf_dependency_response()
        y = 800
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, "Stock Summary Report")
        y -= 30
        pdf.setFont("Helvetica", 10)
        for p in stock:
            line = f'{p.name} ({p.sku or "-"}) | Qty: {p.quantity} | Reorder: {p.reorder_level} | Value: {p.quantity * p.price:.2f}'
            pdf.drawString(40, y, line[:110])
            y -= 18
            if y < 60:
                pdf.showPage()
                y = 800
                pdf.setFont("Helvetica", 10)
        return finalize_pdf_response(buffer, pdf, filename)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="stock_summary_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Product', 'SKU', 'Category', 'Quantity', 'Reorder Level', 'Unit Price', 'Stock Value', 'Supplier'])
    for p in stock:
        writer.writerow([p.name, p.sku, p.category, p.quantity, p.reorder_level, p.price, p.quantity * p.price, p.supplier.name if p.supplier else ''])
    return response


@login_required(login_url='admin_login')
def generate_invoice_pdf(request, movement_id):
    if not request.user.is_staff:
        return redirect('admin_login')
    movement = get_object_or_404(StockMovement.objects.select_related('product', 'supplier'), pk=movement_id, movement_type='out')
    buffer, pdf, filename = build_pdf_response(f'invoice_{movement.id}.pdf')
    if not buffer:
        return pdf_dependency_response()
    y = 800
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(40, y, "INVOICE")
    y -= 30
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f'Invoice No: INV-{movement.id:05d}')
    y -= 18
    pdf.drawString(40, y, f'Date: {movement.created_at:%Y-%m-%d %H:%M}')
    y -= 18
    pdf.drawString(40, y, f'Supplier: {movement.supplier.name if movement.supplier else "N/A"}')
    y -= 30
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Item")
    pdf.drawString(220, y, "Qty")
    pdf.drawString(280, y, "Rate")
    pdf.drawString(360, y, "Amount")
    y -= 15
    pdf.line(40, y, 520, y)
    y -= 18
    pdf.setFont("Helvetica", 10)
    amount = movement.quantity * movement.product.price
    pdf.drawString(40, y, movement.product.name)
    pdf.drawString(220, y, str(movement.quantity))
    pdf.drawString(280, y, f'{movement.product.price:.2f}')
    pdf.drawString(360, y, f'{amount:.2f}')
    y -= 30
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(280, y, "Total:")
    pdf.drawString(360, y, f'{amount:.2f}')
    y -= 40
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, y, "Generated by SmartStock Reporting Module")
    return finalize_pdf_response(buffer, pdf, filename)
