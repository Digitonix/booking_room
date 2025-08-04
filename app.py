from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
import pytz
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, time, timedelta, date
from flask import send_file
import pandas as pd
import io
import os
from math import ceil
import uuid



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///booking.db'
app.config['SECRET_KEY'] = 'supersecretkey'
db = SQLAlchemy(app)

app.permanent_session_lifetime = timedelta(minutes=5)
def session_timeout_check():
    session.modified = True  # refresh timeout on activity
    if 'user_id' not in session and request.endpoint not in ['login', 'static']:
        return redirect(url_for('login'))

wib = pytz.timezone('Asia/Jakarta')
current_time = datetime.now(wib)
current_hour = current_time.hour


app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Maksimum 5MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Buat folder jika belum ada
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(100))
    pic_name = db.Column(db.String(100))
    role = db.Column(db.String(20))

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    lantai = db.Column(db.String(10), nullable=True) 

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100))
    username = db.Column(db.String(100))
    role = db.Column(db.String(50))
    department = db.Column(db.String(100))
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    description = db.Column(db.Text)  

    room = db.relationship('Room', backref='bookings')


def get_schedule_with_empty_slots(bookings, start_day, end_day):
    schedule = []
    current_time = start_day

    for booking in bookings:
        if booking.start_time > current_time:
            schedule.append({
                'user': '',
                'department': '',
                'description': '',
                'start_time': current_time,
                'end_time': booking.start_time
            })

        schedule.append({
            'user': booking.user if booking.user else '',
            'department': booking.department if booking.department else '',
            'description': booking.description if booking.description else '',
            'start_time': booking.start_time,
            'end_time': booking.end_time
        })

        current_time = max(current_time, booking.end_time)

    if current_time < end_day:
        schedule.append({
            'user': '',
            'department': '',
            'description': '',
            'start_time': current_time,
            'end_time': end_day
        })

    return schedule


# ROUTES
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'user_id' not in session:
        flash('Sesi Anda telah berakhir, silakan login kembali.', 'warning')
        return redirect(url_for('login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 6 
    
    rooms_pagination = Room.query.order_by(Room.name).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('dashboard.html', rooms_pagination=rooms_pagination)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # print(f"[DEBUG] Username input: {username}")
        # print(f"[DEBUG] Password input: {password}")

        user = User.query.filter_by(username=username).first()
        # print(f"[DEBUG] User ditemukan: {user}")

        if user and check_password_hash(user.password, password):
            # print(f"[DEBUG] Role: {user.role}")

            session.permanent = True

            if user.role == 'admin':
                app.permanent_session_lifetime = timedelta(minutes=5)
            elif user.role == 'user':
                app.permanent_session_lifetime = timedelta(minutes=5)
            else:
                app.permanent_session_lifetime = timedelta(minutes=15)

            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role

            # print(f"[DEBUG] Session: {session}")

            flash('Login berhasil!', 'success')
            return redirect(url_for('home'))
        else:
            # print("[DEBUG] Login gagal: user tidak ditemukan atau password salah")
            flash('Username atau password salah', 'danger')

    return render_template('login.html')


# @app.route('/logout')
# def logout():
#     session.clear()
#     flash('Anda telah logout.', 'info')
#     return redirect(url_for('login'))

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    if request.method == 'POST' or request.method == 'GET':
        session.clear()
        return redirect(url_for('login'))

@app.route('/book', methods=['GET', 'POST'])
def book():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    rooms = Room.query.all()

    if request.method == 'POST':
        user = request.form['user']
        username = session.get('username')
        role = session.get('role')
        department = request.form['department']
        room_id = int(request.form['room_id'])
        date_str = request.form['date']
        start_str = request.form['start_time']
        end_str = request.form['end_time']
        description = request.form.get('description')

        start_time = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{date_str} {end_str}", "%Y-%m-%d %H:%M")

        if end_time <= start_time:
            flash('Jam akhir harus lebih besar dari jam mulai', 'danger')
            return redirect(url_for('book'))

        conflict = Booking.query.filter(
            Booking.room_id == room_id,
            Booking.end_time > start_time,
            Booking.start_time < end_time
        ).first()

        if conflict:
            flash('Ruangan sudah dibooking di jam tersebut!', 'danger')
        else:
            booking = Booking(
                user=user,
                username=username,
                role=role,
                department=department,
                room_id=room_id,
                start_time=start_time,
                end_time=end_time,
                description=description  
            )
            db.session.add(booking)
            db.session.commit()
            flash('Booking berhasil!', 'success')
            return redirect(url_for('home'))
        

    return render_template('booking_form.html', rooms=rooms)


@app.route('/rooms')
def manage_rooms():
    if 'role' not in session or session['role'] == 'user':
        flash("Anda tidak punya akses!", "danger")
        return redirect(url_for('home'))
    
    rooms = Room.query.all()
    return render_template('rooms/manage_rooms.html', rooms=rooms)

@app.route('/rooms/add', methods=['GET', 'POST'])
def add_room():
    if request.method == 'POST':
        name = request.form['name']
        lantai = request.form['lantai']
        new_room = Room(name=name, lantai=lantai)
        db.session.add(new_room)
        db.session.commit()
        flash('Ruangan berhasil ditambahkan!', 'success')
        return redirect(url_for('manage_rooms'))
    return render_template('rooms/add_room.html')

@app.route('/rooms/update/<int:room_id>', methods=['GET', 'POST'])
def update_room(room_id):
    room = Room.query.get_or_404(room_id)
    if request.method == 'POST':
        room.name = request.form['name']
        room.lantai = request.form['lantai']
        db.session.commit()
        flash('Ruangan berhasil diperbarui!', 'success')
        return redirect(url_for('manage_rooms'))
    return render_template('rooms/update_room.html', room=room)

@app.route('/rooms/delete/<int:room_id>', methods=['POST'])
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    db.session.delete(room)
    db.session.commit()
    flash('Ruangan berhasil dihapus!', 'danger')
    return redirect(url_for('manage_rooms'))


# This is the correct route for the tv_display.html template
@app.route('/tv/<int:room_id>')
def tv_display(room_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    room = Room.query.get_or_404(room_id)
    selected_date_str = request.args.get('date')
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else datetime.today().date()

    start_hour = 7
    end_hour = 17
    start_day = datetime.combine(selected_date, time(start_hour))
    end_day = datetime.combine(selected_date, time(end_hour))

    bookings = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.end_time > start_day,
        Booking.start_time < end_day
    ).order_by(Booking.start_time).all()

    schedule = get_schedule_with_empty_slots(bookings, start_day, end_day)
    now_time = datetime.utcnow() + timedelta(hours=7)  # WIB

    return render_template('tv_display.html', room=room, bookings=schedule, selected_date=selected_date, now_time=now_time)



# This is the API endpoint that the JavaScript in tv_display.html calls for daily updates
@app.route('/api/tv_schedule/<int:room_id>/<string:date_str>', methods=['GET'])
def get_tv_schedule_api(room_id, date_str):
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    start_hour = 7
    end_hour = 17
    start_day = datetime.combine(selected_date, time(start_hour))
    end_day = datetime.combine(selected_date, time(end_hour))

    bookings = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.end_time > start_day,
        Booking.start_time < end_day
    ).order_by(Booking.start_time).all()

    schedule_data = get_schedule_with_empty_slots(bookings, start_day, end_day)

    # Format datetime objects to strings for JSON serialization
    formatted_schedule = []
    for item in schedule_data:
        formatted_schedule.append({
            'user': item['user'] if item['user'] else '', # Ensure '--- Available ---' for empty slots
            'department': item['department'],
            'description': item['description'] if 'description' in item else '',
            'start_time': item['start_time'].strftime('%H:%M'),
            'end_time': item['end_time'].strftime('%H:%M')
        })

    # Get room name for the header
    room = db.session.get(Room, room_id)
    room_name = room.name if room else "Unknown Room"

    return jsonify({
        "room_name": room_name,
        "selected_date": selected_date.strftime('%Y-%m-%d'),
        "bookings": formatted_schedule,
        "now_time": datetime.now().strftime('%H:%M:%S') # For client-side comparison if needed
    })


@app.route('/available-times', methods=['POST'])
def available_times():
    room_id = int(request.form['room_id'])
    date = datetime.strptime(request.form['date'], "%Y-%m-%d").date()

    start_hour = 00
    end_hour = 23
    interval_minutes = 60

    bookings = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.start_time >= datetime.combine(date, time.min),
        Booking.end_time <= datetime.combine(date, time.max)
    ).all()

    booked_slots = set()
    for booking in bookings:
        s = booking.start_time
        e = booking.end_time
        while s < e:
            booked_slots.add(s.strftime("%H:%M"))
            s += timedelta(minutes=interval_minutes)

    all_slots = []
    now = datetime.now()
    current = datetime.combine(date, time(hour=start_hour))
    end = datetime.combine(date, time(hour=end_hour))

    while current < end:
        if date > now.date() or (date == now.date() and current.time() >= now.time()):
            slot_str = current.strftime("%H:%M")
            if slot_str not in booked_slots:
                all_slots.append(slot_str)
        current += timedelta(minutes=interval_minutes)

    booked_times = [{'start': b.start_time.strftime("%H:%M"), 'end': b.end_time.strftime("%H:%M")} for b in bookings]

    return jsonify({'available_hours': all_slots, 'booked_times': booked_times})




@app.route('/my-bookings')
def my_bookings():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    role = session['role']
    now = datetime.now()
    today = now.date()

    filter_date_str = request.args.get('filter_date')
    filter_date = None

    # Ambil semua booking berdasarkan role
    if role == 'admin':
        bookings = Booking.query.order_by(Booking.start_time.desc()).all()
    else:
        bookings = Booking.query.filter_by(username=username).order_by(Booking.start_time.desc()).all()

    # Filter berdasarkan tanggal & waktu saat ini
    filtered_bookings = []
    for b in bookings:
        start_date = b.start_time.date()
        if filter_date_str:
            try:
                filter_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
            except ValueError:
                filter_date = None

            if start_date == filter_date and b.end_time > now:
                filtered_bookings.append(b)
        else:
            if start_date == today and b.end_time > now:
                filtered_bookings.append(b)

    return render_template(
        'my_bookings.html',
        bookings=filtered_bookings,
        now=now,
        today=today
    )



@app.route('/cancel-booking/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session:
        flash('Anda harus login untuk membatalkan booking.', 'danger')
        return redirect(url_for('login'))

    booking = Booking.query.get_or_404(booking_id)
    current_username = session.get('username')
    current_role = session.get('role')

    if current_role == 'admin' or (current_role == 'user' and booking.username == current_username):
        db.session.delete(booking)
        db.session.commit()
        flash('Booking berhasil dibatalkan.', 'success')
    else:
        flash('Anda tidak memiliki izin untuk membatalkan booking ini.', 'danger')

    return redirect(url_for('my_bookings'))




@app.template_filter('to_datetime')
def to_datetime_filter(value, format="%Y-%m-%d %H:%M"):
    if isinstance(value, str):
        return datetime.strptime(value, format)
    return value



@app.template_filter('format_date_id')
def format_date_id(value):
    days = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    months = {
        'January': 'Januari', 'February': 'Februari', 'March': 'Maret',
        'April': 'April', 'May': 'Mei', 'June': 'Juni',
        'July': 'Juli', 'August': 'Agustus', 'September': 'September',
        'October': 'Oktober', 'November': 'November', 'December': 'Desember'
    }
    day_name = days[value.strftime('%A')]
    month_name = months[value.strftime('%B')]
    return f"{day_name}, {value.day:02d} {month_name} {value.year}"



@app.route('/jadwal-booking')
def jadwal_booking():
    rooms = Room.query.all()
    today = datetime.today().date()
    start_time = datetime.combine(today, time(7, 0))
    end_time = datetime.combine(today, time(17, 0))

    # Ambil semua booking hari ini
    bookings = Booking.query.filter(
        Booking.start_time >= start_time,
        Booking.end_time <= end_time
    ).all()

    return render_template('schedule.html', rooms=rooms, bookings=bookings, today=today)



@app.route('/schedule')
def schedule_view():
    if 'user_id' not in session:
        return redirect(url_for('login'))


    local_now = datetime.utcnow() + timedelta(hours=7)

 
    today_param = request.args.get('date')
    if today_param:
        try:
            selected_date = datetime.strptime(today_param, '%Y-%m-%d').date()
        except ValueError:
            selected_date = local_now.date()
    else:
        selected_date = local_now.date()

    start_hour = 7
    end_hour = 17
    now = local_now  # Gunakan waktu lokal untuk realtime clock
    current_hour = now.hour if now.date() == selected_date else None
    hours = list(range(start_hour, end_hour + 1))

    # Ambil semua ruangan dan booking pada tanggal terpilih
    rooms = Room.query.all()
    bookings = Booking.query.filter(
        db.func.date(Booking.start_time) == selected_date
    ).all()


    schedule = {}             
    booking_details = {}      
    room_floors = {}          

    for room in rooms:
        room_schedule = {h: None for h in hours}
        room_detail = {h: None for h in hours}
        room_floors[room.name] = room.lantai

        room_bookings = [b for b in bookings if b.room_id == room.id]
        for booking in room_bookings:
            start_hour_bk = booking.start_time.hour
            end_hour_bk = booking.end_time.hour

            # Tambahkan 1 jam jika ada menit atau detik
            if booking.end_time.minute > 0 or booking.end_time.second > 0:
                end_hour_bk += 1

            for h in range(start_hour_bk, end_hour_bk):
                if h in room_schedule:
                    room_schedule[h] = booking.department
                    room_detail[h] = booking

        schedule[room.name] = room_schedule
        booking_details[room.name] = room_detail

    return render_template(
        'schedule.html',
        schedule=schedule,
        hours=hours,
        selected_date=selected_date,
        room_floors=room_floors,
        booking_details=booking_details,
        current_hour=current_hour,
        current_time=now,
        rooms=rooms
    )



@app.route('/tv-schedule')
def tv_schedule():
    # Ambil parameter tanggal (optional)
    today_param = request.args.get('date')
    if today_param:
        try:
            selected_date = datetime.strptime(today_param, '%Y-%m-%d').date()
        except ValueError:
            selected_date = datetime.today().date()
    else:
        selected_date = datetime.today().date()

    # config
    start_hour = 7
    end_hour = 17

    now = datetime.utcnow() + timedelta(hours=7)
    current_hour = now.hour if now.date() == selected_date else None


    rooms = Room.query.all()


    bookings = Booking.query.filter(
        db.func.date(Booking.start_time) == selected_date
    ).all()


    hours = []
    for h in range(start_hour, end_hour + 1):
        hours.append({
            "start": h,
            "end": h + 1
        })


    schedule = {}
    room_floors = {}
    for room in rooms:
        room_schedule = {h: None for h in range(start_hour, end_hour + 1)}
        for booking in bookings:
            if booking.room_id == room.id:
                start = booking.start_time.hour
                end = booking.end_time.hour
                for h in range(start, end):
                    if h in room_schedule:
                        room_schedule[h] = booking.department 
        schedule[room.name] = room_schedule
        room_floors[room.name] = room.lantai


    images = TvImage.query.filter_by(is_active=True).order_by(TvImage.upload_date.desc()).all()

    return render_template(
        'tv_schedule.html',
        schedule=schedule,
        hours=hours,
        selected_date=selected_date,
        current_hour=current_hour,
        room_floors=room_floors,
        images=images
    )


@app.route('/export-schedule')
def export_schedule():
    today = request.args.get('date')
    if today:
        try:
            selected_date = datetime.strptime(today, '%Y-%m-%d').date()
        except ValueError:
            selected_date = datetime.today().date()
    else:
        selected_date = datetime.today().date()

    start_hour = 7
    end_hour = 17
    hours = list(range(start_hour, end_hour + 1))

    rooms = Room.query.all()
    bookings = Booking.query.filter(
        db.func.date(Booking.start_time) == selected_date
    ).all()

    data = []
    for room in rooms:
        row = {"Ruangan": room.name}
        hour_map = {h: "" for h in hours}

        room_bookings = [b for b in bookings if b.room_id == room.id]
        for booking in room_bookings:
            start_hour_bk = booking.start_time.hour
            end_hour_bk = booking.end_time.hour


            if booking.end_time.minute > 0 or booking.end_time.second > 0:
                end_hour_bk += 1


            end_hour_bk = min(end_hour_bk, end_hour + 1)


            for h in range(start_hour_bk, end_hour_bk):
                if h in hour_map:
                    hour_map[h] = booking.department  

        for h in hours:
            time_range = f"{h:02d}:00 - {h+1:02d}:00"
            row[time_range] = hour_map[h]

        data.append(row)

    df = pd.DataFrame(data)

    # Export ke Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Jadwal Booking')

    output.seek(0)
    filename = f"jadwal_booking_{selected_date.strftime('%Y%m%d')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )




@app.route('/admin/users')
def manage_users():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    all_users = User.query.order_by(User.username).all()
    total_pages = ceil(len(all_users) / per_page)
    users = all_users[(page - 1) * per_page: page * per_page]

    return render_template("manage_users.html", users=users, page=page, total_pages=total_pages)


@app.route('/add_user', methods=['POST'])
def add_user():
    if request.method == 'POST':
        user_id = request.form.get('id') 

        if user_id: # Ini adalah mode EDIT

            username = request.form['username'] 
            user = User.query.get(user_id)
            if user:

                department = request.form['department']
                pic_name = request.form['pic_name']
                role = request.form['role']
                new_password = request.form.get('password')

                user.department = department
                user.pic_name = pic_name
                user.role = role

                if new_password: 
                    user.set_password(new_password) 
                
                try:
                    db.session.commit()
                    flash('Pengguna berhasil diperbarui!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Terjadi kesalahan saat memperbarui pengguna: {e}', 'danger')
            else:
                flash('Pengguna tidak ditemukan!', 'danger')
            return redirect(url_for('manage_users'))

        else: 
            username = request.form['username']
            password = request.form['password']
            department = request.form['department']
            pic_name = request.form['pic_name']
            role = request.form['role']

            if not password:
                flash('Password wajib diisi untuk pengguna baru!', 'danger')
                return redirect(url_for('manage_users')) 
            
            if User.query.filter_by(username=username).first():
                flash('Username sudah ada, pilih username lain.', 'danger')
                return redirect(url_for('manage_users'))

            new_user = User(
                username=username,
                department=department,
                pic_name=pic_name,
                role=role
            )
            new_user.set_password(password) 
            
            try:
                db.session.add(new_user)
                db.session.commit()
                flash('Pengguna baru berhasil ditambahkan!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Terjadi kesalahan saat menambahkan pengguna: {e}', 'danger')

            return redirect(url_for('manage_users'))
    

    return render_template('manage_users.html', user=None, users=User.query.all())


@app.route('/edit_user/<int:user_id>')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    all_users = User.query.all() 
    return render_template('manage_users.html', user=user, users=all_users)


@app.route('/admin/users/delete/<int:user_id>')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('manage_users'))


class TvImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False)
    caption = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True) 
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)


# Fungsi cek ekstensi
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Route upload gambar
@app.route('/admin/upload_image', methods=['GET', 'POST'])
def upload_image():
    if session.get('role') != 'admin':
        return redirect('/')

    if request.method == 'POST':
        file = request.files.get('image')
        caption = request.form.get('caption', '').strip()
        is_active = bool(request.form.get('is_active'))

        if not file or file.filename == '':
            flash('Tidak ada file yang dipilih.', 'danger')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('Format file tidak diizinkan. Gunakan JPG, JPEG, PNG, atau GIF.', 'danger')
            return redirect(request.url)

        # Buat nama file unik
        ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"

        # Pastikan folder upload ada
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        new_image = TvImage(filename=filename, caption=caption, is_active=is_active)
        db.session.add(new_image)
        db.session.commit()

        flash('Gambar berhasil diunggah.', 'success')
        return redirect(url_for('manage_images'))

    return render_template('upload_image_form.html')

@app.errorhandler(413)
def file_too_large(e):
    flash('Ukuran file terlalu besar (maksimum 5MB).', 'danger')
    return redirect(request.url)


@app.route('/admin/manage_images')
def manage_images():
    if session.get('role') != 'admin':
        return redirect('/')

    images = TvImage.query.order_by(TvImage.upload_date.desc()).all()

    for img in images:
        img.upload_wib = img.upload_date + timedelta(hours=7)

    return render_template('manage_images.html', images=images)


# @app.route('/admin/edit_image/<int:image_id>', methods=['GET', 'POST'])
# def edit_image(image_id):
#     if session.get('role') != 'admin':
#         return redirect('/')

#     image = TvImage.query.get_or_404(image_id)

#     if request.method == 'POST':
 
#         image.caption = request.form.get('caption', '')
#         image.is_active = bool(request.form.get('is_active'))

#         file = request.files.get('file')
#         if file and file.filename:
#             filename = secure_filename(file.filename)
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             file.save(filepath)
#             image.filename = filename  


#         db.session.commit()
#         flash('Data gambar berhasil diperbarui', 'success')
#         return redirect(url_for('manage_images'))

#     return render_template('edit_image.html', image=image)


@app.route('/admin/edit_image/<int:image_id>', methods=['GET', 'POST'])
def edit_image(image_id):
    if session.get('role') != 'admin':
        return redirect('/')

    image = TvImage.query.get_or_404(image_id)
    old_filename = image.filename  

    if request.method == 'POST':
        image.caption = request.form.get('caption', '')
        image.is_active = bool(request.form.get('is_active'))

        file = request.files.get('file')
        if file and file.filename:
 
            old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except Exception as e:
                    print(f"Gagal menghapus file lama: {e}")

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            image.filename = filename

        db.session.commit()
        flash('Data gambar berhasil diperbarui', 'success')
        return redirect(url_for('manage_images'))

    return render_template('edit_image.html', image=image)


@app.route('/admin/delete_image/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    if session.get('role') != 'admin':
        return redirect('/')

    image = TvImage.query.get_or_404(image_id)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(image)
    db.session.commit()
    flash('Gambar berhasil dihapus', 'success')
    return redirect(url_for('manage_images'))

@app.route('/api/tv_images')
def api_tv_images():

    images = TvImage.query.filter_by(is_active=True).order_by(TvImage.upload_date.desc()).all()
    
    result = []
    for img in images:
        result.append({
            'filename': img.filename,
            'caption': img.caption or ''
        })

    return jsonify({'product_images': result})


@app.route('/admin/bookings')
def manage_bookings():
    page = request.args.get('page', 1, type=int)
    bookings = Booking.query.order_by(Booking.start_time.desc()).paginate(page=page, per_page=10)
    return render_template('admin_bookings.html', bookings=bookings)


@app.route('/admin/bookings/delete/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    flash('Booking berhasil dihapus.', 'success')
    return redirect(url_for('manage_bookings'))


@app.route('/admin/bookings/bulk-delete', methods=['POST'])
def bulk_delete_bookings():
    booking_ids = request.form.getlist('booking_ids')
    if booking_ids:
        Booking.query.filter(Booking.id.in_(booking_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(booking_ids)} booking berhasil dihapus.', 'success')
    else:
        flash('Tidak ada booking yang dipilih.', 'warning')
    return redirect(url_for('manage_bookings'))







if __name__ == '__main__':
    # with app.app_context():
    #     db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)


