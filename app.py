from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime
import pandas as pd
import os
import json
import logging

# Flask uygulaması oluşturma
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///muhasebe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'  # Güvenlik için kullanılacak secret key
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

# Loglama ayarı
logging.basicConfig(level=logging.DEBUG)

# Kullanıcı Modeli
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)  # Şifrelenmiş

# Kategori Modeli
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Ürün Modeli
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(100), nullable=False, unique=True)  # Barkod/SKU
    purchase_price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    shipping_cost = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)  # Stok bilgisi
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('products', lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def profit(self):
        return self.sale_price - self.purchase_price - self.shipping_cost

# Teklif Modeli
class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    offer_name = db.Column(db.String(100), nullable=False)  # Teklif ismi
    status = db.Column(db.String(20), nullable=False, default='Cevap Bekleyen')  # Teklif durumu
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)  # Vade tarihi
    currency = db.Column(db.String(10), nullable=False)  # Döviz tipi
    service_product_name = db.Column(db.String(100), nullable=False)  # Hizmet/Ürün Adı
    quantity = db.Column(db.Float, nullable=False)  # Miktar
    unit_price = db.Column(db.Float, nullable=False)  # Birim fiyatı
    tax_rate = db.Column(db.Float, nullable=False)  # Vergi oranı
    discount = db.Column(db.Float, default=0)  # İndirim oranı
    total_price = db.Column(db.Float, nullable=False)  # Toplam fiyat

    # Ürüne ilişkin bağlantı
    product = db.relationship('Product', backref='offers')  # Ürün ile ilişki

# Sipariş Modeli
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # Nakit veya POS
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Sipariş tarihi
    items = db.relationship('OrderItem', backref='order', lazy=True)  # İlişkili ürünler

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)  # Bu ürünün toplam fiyatı

# Veritabanı tablolarını oluşturmak için uygulama bağlamı kullanın
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    flash('Bu sayfayı görüntülemek için giriş yapmalısınız!')
    return redirect(url_for('login'))

@app.route('/')
def index():
    search_query = request.args.get('search')
    products = Product.query.all()

    # Bugünkü ve bir aylık toplam satış ve net kazanç hesaplamaları
    today = datetime.utcnow().date()
    
    # Bugünkü toplam satış
    today_orders = Order.query.filter(Order.created_at >= datetime.combine(today, datetime.min.time())).all()
    today_total_sales = sum(order.total_price for order in today_orders)
    today_total_profit = sum(order.total_price - sum(item.total_price for item in order.items) for order in today_orders)

    # Son 30 günün toplam satış ve net kazancı
    start_date = datetime.utcnow() - pd.DateOffset(months=1)  # 1 ay geri
    monthly_orders = Order.query.filter(Order.created_at >= start_date).all()
    monthly_total_sales = sum(order.total_price for order in monthly_orders)
    monthly_total_profit = sum(order.total_price - sum(item.total_price for item in order.items) for order in monthly_orders)

    if search_query:
        products = Product.query.filter(Product.name.like(f"%{search_query}%")).all()

    return render_template('index.html', products=products,
                           today_total_sales=today_total_sales,
                           today_total_profit=today_total_profit,
                           monthly_total_sales=monthly_total_sales,
                           monthly_total_profit=monthly_total_profit)


@app.route('/get_product_by_barcode')
@login_required
def get_product_by_barcode():
    barcode = request.args.get('barcode')
    product = Product.query.filter_by(sku=barcode).first()
    if product:
        return jsonify({'id': product.id, 'name': product.name, 'sale_price': product.sale_price})
    return jsonify(None)

@app.route('/create_order', methods=['POST'])
@login_required
def create_order():
    try:
        data = request.get_json()  # JSON formatında veri alın
        if not data or 'items' not in data:
            return jsonify({'error': 'Geçersiz veri!'}), 400

        items = data['items']
        total_price = sum(item['price'] * item['quantity'] for item in items)

        if total_price <= 0:
            return jsonify({'error': 'Toplam fiyat sıfırdan büyük olmalıdır!'}), 400

        new_order = Order(
            user_id=current_user.id,
            total_price=total_price,
            payment_method=data.get('payment_method', 'Nakit')
        )
        
        db.session.add(new_order)
        db.session.commit()  # Siparişi kaydet

        # Sipariş kalemlerini ekle
        for item in items:
            order_item = OrderItem(
                order_id=new_order.id,
                product_name=item['name'],
                quantity=item['quantity'],
                unit_price=item['price'],
                total_price=item['price'] * item['quantity']
            )
            db.session.add(order_item)

        db.session.commit()  # Sipariş kalemlerini kaydedin

        # Stok güncelle
        for item in items:
            product = Product.query.get(item['id'])
            if product:
                product.stock -= item['quantity']  # Stok azalt
        db.session.commit()  # Stok güncellemesini kaydet

        return jsonify({'total': total_price})

    except Exception as e:
        app.logger.error(f"Error while creating order: {str(e)}")
        return jsonify({'error': 'Bir hata oluştu!'}), 500


@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    categories = Category.query.all()
    if request.method == 'POST':
        name = request.form['name']
        sku = request.form['sku']
        purchase_price = float(request.form['purchase_price'])
        sale_price = float(request.form['sale_price'])
        shipping_cost = float(request.form['shipping_cost'])
        stock = int(request.form['stock'])
        category_id = int(request.form['category'])

        new_product = Product(
            name=name,
            sku=sku,
            purchase_price=purchase_price,
            sale_price=sale_price,
            shipping_cost=shipping_cost,
            stock=stock,
            category_id=category_id
        )
        
        db.session.add(new_product)
        db.session.commit()
        flash('Ürün başarıyla eklendi!')
        return redirect(url_for('index'))
    return render_template('add_product.html', categories=categories)

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
def add_category():
    if request.method == 'POST':
        name = request.form['name']
        new_category = Category(name=name)

        db.session.add(new_category)
        db.session.commit()
        flash('Kategori başarıyla eklendi!')
        return redirect(url_for('add_product'))
    return render_template('add_category.html')

@app.route('/add_offer', methods=['GET', 'POST'])
@login_required
def add_offer():
    if request.method == 'POST':
        product_id = request.form['product_id']
        customer_name = request.form['customer_name']
        offer_name = request.form['offer_name']
        due_date = request.form['due_date']
        currency = request.form['currency']
        service_product_name = request.form['service_product_name']
        quantity = float(request.form['quantity'])
        unit_price = float(request.form['unit_price'])
        tax_rate = float(request.form['tax_rate'])
        discount = float(request.form['discount'])

        total_price = (unit_price * quantity) * (1 + tax_rate / 100) * (1 - (discount / 100))

        new_offer = Offer(
            product_id=product_id,
            customer_name=customer_name,
            offer_name=offer_name,
            due_date=datetime.strptime(due_date, '%Y-%m-%d'),
            currency=currency,
            service_product_name=service_product_name,
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=tax_rate,
            discount=discount,
            total_price=total_price
        )

        db.session.add(new_offer)
        db.session.commit()
        flash('Teklif başarıyla eklendi!')
        return redirect(url_for('offers'))

    products = Product.query.all()  # Ürünleri al
    return render_template('add_offer.html', products=products)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            df = pd.read_excel(file)
            for index, row in df.iterrows():
                category_name = row['category']
                category = Category.query.filter_by(name=category_name).first()
                if not category:
                    category = Category(name=category_name)
                    db.session.add(category)
                    db.session.commit()
                new_product = Product(
                    name=row['name'],
                    sku=row['sku'],
                    purchase_price=row['purchase_price'],
                    sale_price=row['sale_price'],
                    shipping_cost=row['shipping_cost'],
                    stock=row['stock'],
                    category_id=category.id
                )
                db.session.add(new_product)
            db.session.commit()
            flash('Excel ile ürünler yüklendi!')
        return redirect(url_for('products'))
    return render_template('upload.html')

@app.route('/export')
@login_required
def export():
    products = Product.query.all()
    product_list = [{
        'name': product.name,
        'sku': product.sku,
        'purchase_price': product.purchase_price,
        'sale_price': product.sale_price,
        'shipping_cost': product.shipping_cost,
        'stock': product.stock,
        'category': product.category.name
    } for product in products]

    df = pd.DataFrame(product_list)
    excel_file = 'products.xlsx'
    df.to_excel(excel_file, index=False)

    return send_file(excel_file, as_attachment=True)


@app.route('/report', methods=['GET'])
@login_required
def report():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = Product.query
    if start_date and end_date:
        query = query.filter(Product.created_at >= start_date, Product.created_at <= end_date)

    products = query.all()
    total_profit = sum(product.profit for product in products)
    return render_template('report.html', products=products, total_profit=total_profit)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        new_user = User(username=username, password=password)  # Burada da hashleme yapmayı unutmayın!
        
        db.session.add(new_user)
        db.session.commit()
        flash('Kullanıcı başarıyla oluşturuldu!')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:  # Burada şifre kontrolünü yaptıktan sonra giriş yapabilirsiniz.
            login_user(user)
            flash('Giriş başarılı!')
            return redirect(url_for('index'))
        flash('Kullanıcı adı veya şifre hatalı!')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Başarıyla çıkış yaptınız!')
    return redirect(url_for('login'))

@app.route('/backup')
@login_required
def backup():
    db_file = 'muhasebe.db'
    backup_file = 'backup_muhasebe.db'
    os.system(f'cp {db_file} {backup_file}')
    flash('Veritabanı başarıyla yedeklendi!')
    return redirect(url_for('index'))

@app.route('/offers', methods=['GET', 'POST'])
@login_required
def offers():
    if request.method == 'POST':
        # Teklif ekleme işlemleri
        product_id = request.form['product_id']
        customer_name = request.form['customer_name']
        offer_name = request.form['offer_name']
        due_date = request.form['due_date']
        currency = request.form['currency']
        service_product_name = request.form['service_product_name']
        quantity = float(request.form['quantity'])
        unit_price = float(request.form['unit_price'])
        tax_rate = float(request.form['tax_rate'])
        discount = float(request.form['discount'])

        total_price = (unit_price * quantity) * (1 + tax_rate / 100) * (1 - (discount / 100))

        new_offer = Offer(
            product_id=product_id,
            customer_name=customer_name,
            offer_name=offer_name,
            due_date=datetime.strptime(due_date, '%Y-%m-%d'),
            currency=currency,
            service_product_name=service_product_name,
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=tax_rate,
            discount=discount,
            total_price=total_price
        )

        db.session.add(new_offer)
        db.session.commit()
        flash('Teklif başarıyla eklendi!')
        return redirect(url_for('offers'))

    offers = Offer.query.all()  # Tüm teklifleri al
    return render_template('offers.html', offers=offers)

@app.route('/offer/update/<int:offer_id>', methods=['POST'])
@login_required
def update_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    status = request.form.get('status')
    offer.status = status
    db.session.commit()
    flash('Teklif durumu güncellendi!')
    return redirect(url_for('offers'))

@app.route('/offer/delete/<int:offer_id>', methods=['POST'])
@login_required
def delete_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    db.session.delete(offer)
    db.session.commit()
    flash('Teklif başarıyla silindi!')
    return redirect(url_for('offers'))

@app.route('/products', methods=['GET'])
@login_required
def products():
    all_products = Product.query.all()  # Tüm ürünleri al
    return render_template('products.html', products=all_products)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.all()

    if request.method == 'POST':
        product.name = request.form['name']
        product.sku = request.form['sku']
        product.purchase_price = float(request.form['purchase_price'])
        product.sale_price = float(request.form['sale_price'])
        product.shipping_cost = float(request.form['shipping_cost'])
        product.stock = int(request.form['stock'])
        product.category_id = int(request.form['category'])

        db.session.commit()
        flash('Ürün başarıyla güncellendi!')
        return redirect(url_for('products'))

    return render_template('edit_product.html', product=product, categories=categories)

@app.route('/sales_screen', methods=['GET', 'POST'])
@login_required
def sales_screen():
    products = Product.query.all()

    if 'sales' not in session:
        session['sales'] = []

    sales = session['sales']

    if request.method == 'POST':
        action = request.form.get('action')
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity', type=int, default=1)

        if action == 'add' and product_id:
            product = Product.query.get(product_id)
            if product and product.stock >= quantity:
                existing_item = next((item for item in sales if item['id'] == int(product_id)), None)
                if existing_item:
                    existing_item['quantity'] += quantity
                else:
                    sales.append({"id": product.id, "name": product.name, "price": product.sale_price, "quantity": quantity})
                product.stock -= quantity
                db.session.commit()
                flash(f"{product.name} başarıyla sepete eklendi.")
            else:
                flash('Yeterli stok yok!')

        elif action == 'remove' and product_id:
            for item in sales:
                if item['id'] == int(product_id):
                    product = Product.query.get(item['id'])
                    if product:
                        product.stock += item['quantity']
                        sales.remove(item)
                        db.session.commit()
                        flash(f"{item['name']} sepetten çıkarıldı.")
                    break

        session['sales'] = sales

    return render_template('sales_screen.html', products=products, sales=sales)

@app.route('/get_product_by_id')
@login_required
def get_product_by_id():
    product_id = request.args.get('product_id')
    product = Product.query.get(product_id)
    if product:
        return jsonify({'success': True, 'product': {'id': product.id, 'name': product.name, 'sale_price': product.sale_price}})
    return jsonify({'success': False})



@app.route('/update_stock_handler', methods=['POST'])
@login_required
def update_stock_handler():
    product_id = request.args.get('product_id')
    quantity = request.args.get('quantity', type=int)

    if product_id and quantity is not None:
        product = Product.query.get(product_id)
        if product:
            product.stock += quantity
            db.session.commit()
            print(f"Stok güncellendi: Ürün ID: {product_id}, Miktar: {quantity}")
            return jsonify({'success': True})
    print(f"Stok güncellenemedi: Ürün ID: {product_id}, Miktar: {quantity}")
    return jsonify({'success': False})


@app.route('/sales/clear', methods=['POST'])
@login_required
def clear_sales():
    session.pop('sales', None)
    flash('Sepet temizlendi!')
    return redirect(url_for('sales_screen'))

@app.route('/my_orders', methods=['GET'])
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('my_orders.html', orders=orders)

if __name__ == '__main__':
    with app.app_context():  
        db.create_all()  # Veritabanındaki tüm tabloları oluştur

    app.run(debug=True, port=5002)  # Uygulamayı debug modunda başlat
