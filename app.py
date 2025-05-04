from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import geopy.distance
from geopy.geocoders import Nominatim
import os
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

geolocator = Nominatim(user_agent="food_sharing_app")

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # donor or recipient
    address = db.Column(db.String(200))
    contact_number = db.Column(db.String(20))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FoodListing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    food_item = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    available_until = db.Column(db.DateTime, nullable=False)
    is_claimed = db.Column(db.Boolean, default=False)
    contact_number = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FoodRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    food_listing_id = db.Column(db.Integer, db.ForeignKey('food_listing.id'), nullable=False)
    quantity_requested = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Utility Functions
def calculate_distance(lat1, lon1, lat2, lon2):
    coords_1 = (lat1, lon1)
    coords_2 = (lat2, lon2)
    return geopy.distance.distance(coords_1, coords_2).km

def get_coordinates(address):
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    return None, None

food_quotes = [
    "Food is symbolic of love when words are inadequate.",
    "Good food is the foundation of genuine happiness.",
    "Sharing food is sharing love.",
    "Food tastes better when you eat it with your family.",
    "One cannot think well, love well, sleep well, if one has not dined well.",
]

# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            flash('Login successful!', 'success')
            return redirect(url_for('welcome'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        address = request.form['address']
        contact_number = request.form['contact_number']

        # Validate contact number: must be exactly 10 digits numeric
        if not (contact_number.isdigit() and len(contact_number) == 10):
            flash('please enter correct number', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))

        lat, lon = get_coordinates(address)
        if not lat or not lon:
            flash('Could not find your location. Please enter a valid address.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            password=hashed_password,
            role=role,
            address=address,
            contact_number=contact_number,
            latitude=lat,
            longitude=lon
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/donor', methods=['GET', 'POST'])
def donor():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(user_id)

    if request.method == 'POST':
        food_item = request.form['food_item']
        quantity = int(request.form['quantity'])
        address = request.form['address']
        available_hours = int(request.form['available_hours'])

        lat, lon = get_coordinates(address)
        if not lat or not lon:
            flash('Could not find the pickup location.', 'danger')
            return redirect(url_for('donor'))

        available_until = datetime.utcnow() + timedelta(hours=available_hours)

        new_listing = FoodListing(
            donor_id=user.id,
            food_item=food_item,
            quantity=quantity,
            address=address,
            latitude=lat,
            longitude=lon,
            available_until=available_until,
            contact_number=user.contact_number
        )
        db.session.add(new_listing)
        db.session.commit()

        flash('Food listed successfully!', 'success')
        return redirect(url_for('donor'))

    requests = FoodRequest.query.join(FoodListing).filter(
        FoodListing.donor_id == user.id,
        FoodRequest.status == 'pending'
    ).all()

    return render_template('donor.html', requests=requests, quotes=random.choice(food_quotes))

@app.route('/recipient', methods=['GET', 'POST'])
def recipient():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(user_id)

    if request.method == 'POST':
        quantity_needed = int(request.form['quantity_needed'])
        address = request.form['address']

        lat, lon = get_coordinates(address)
        if not lat or not lon:
            flash('Could not find your location.', 'danger')
            return redirect(url_for('recipient'))

        user.address = address
        user.latitude = lat
        user.longitude = lon
        db.session.commit()

        all_listings = FoodListing.query.filter(
            FoodListing.is_claimed == False,
            FoodListing.available_until > datetime.utcnow()
        ).all()

        listings_with_distance = []
        for listing in all_listings:
            distance = calculate_distance(user.latitude, user.longitude, listing.latitude, listing.longitude)
            listings_with_distance.append((distance, listing))

        listings_with_distance.sort(key=lambda x: (x[0], x[1].created_at))  # sort shortest distance, then FCFS

        listings = [listing for distance, listing in listings_with_distance if distance <= 30]

        return render_template('recipient.html', listings=listings, user=user, quotes=random.choice(food_quotes), requests=None)

    # Fetch FoodRequests and join FoodListing
    user_requests = FoodRequest.query.filter_by(recipient_id=user.id).all()
    enriched_requests = []
    for req in user_requests:
        listing = FoodListing.query.get(req.food_listing_id)
        enriched_requests.append({
            'request': req,
            'listing': listing
        })

    return render_template('recipient.html', requests=enriched_requests, user=user, listings=None, quotes=random.choice(food_quotes))


@app.route('/request_food/<int:listing_id>', methods=['POST'])
def request_food(listing_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))

    quantity_requested = int(request.form['quantity_requested'])
    listing = FoodListing.query.get(listing_id)

    if not listing:
        flash('Food listing not found.', 'danger')
        return redirect(url_for('recipient'))

    new_request = FoodRequest(
        recipient_id=user_id,
        food_listing_id=listing.id,
        quantity_requested=quantity_requested
    )
    db.session.add(new_request)
    db.session.commit()

    flash('Request sent successfully!', 'success')
    return redirect(url_for('recipient'))

@app.route('/respond_request/<int:request_id>/<string:response>', methods=['POST'])
def respond_request(request_id, response):
    request_record = FoodRequest.query.get(request_id)
    if not request_record:
        flash('Request not found.', 'danger')
        return redirect(url_for('donor'))

    if response == 'approve':
        request_record.status = 'approved'
        food_listing = FoodListing.query.get(request_record.food_listing_id)
        food_listing.is_claimed = True
        flash('Request approved successfully!', 'success')
    else:
        request_record.status = 'rejected'
        flash('Request rejected.', 'info')

    db.session.commit()
    return redirect(url_for('donor'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
