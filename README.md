# Bristol Regional Food Network

A Django-based multi-producer food marketplace developed as a third-year university project.

The system allows local producers to manage products and orders, while customers, restaurants and community groups can browse products, use a persistent cart and complete a multi-producer checkout.

## Main Features

- Email-based accounts with customer, producer, restaurant, community-group and administrator roles
- Producer and customer profiles
- Product catalogue with categories, search and filtering
- Seasonal, organic and allergen information
- Persistent shopping cart
- Single-producer and multi-producer checkout
- Mock payment processing
- Automatic stock reduction and low-stock alerts
- Producer order management and status updates
- Customer and producer notifications
- Five percent platform commission
- Producer settlement and administrator commission reports
- CSV report export
- Role-based REST API
- Login throttling and authentication audit logging
- Docker and PostgreSQL support
- Automated Django tests

## Technology Used

- Python 3.12
- Django 5.2
- Django REST Framework
- PostgreSQL 16
- Docker Compose
- Gunicorn
- WhiteNoise
- HTML and CSS

## Running the Project

The project uses Docker and PostgreSQL.

```powershell
git clone https://github.com/Jude232/bristol-regional-food-network.git
cd bristol-regional-food-network
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec web python manage.py loaddata categories
docker compose exec web python manage.py seed_demo_data

Open the website at:

http://localhost:8000/

To stop the project:

docker compose down


Demo Accounts

All demo accounts use the password DemoPassword2026!.

Role	         Email
Administrator	demo.admin@example.test
Producer	      demo.farm@example.test
Producer	      demo.dairy@example.test
Customer	      demo.customer@example.test
Restaurant	   demo.restaurant@example.test

Tests

Run the full test suite with:

docker compose exec web python manage.py test accounts marketplace orders api

A successful test run ends with:

OK

## Project Structure

```text
accounts/       User accounts, profiles and authentication
api/            REST API
config/         Django project settings and URLs
marketplace/    Products, categories and inventory
orders/         Cart, checkout, orders, notifications and reports
static/         CSS and static files
templates/      HTML templates
docs/           Screenshots and supporting files
```

## Repository

https://github.com/Jude232/bristol-regional-food-network