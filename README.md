# Bristol Regional Food Network

A multi-producer digital food marketplace developed with Django for the Bristol Regional Food Network.

The application allows local producers to manage products and incoming orders while customers, restaurants and community organisations can browse products, maintain persistent carts and complete multi-producer orders.

## Main Features

### Accounts and security

- Email-based authentication
- Customer, restaurant, community-group, producer and administrator roles
- Producer and customer profiles
- Strong Django password hashing
- Generic login failure messages
- Login throttling after repeated failed attempts
- Authentication audit events
- Optional persistent login sessions
- Role-based page and API permissions
- CSRF protection and secure browser headers

### Marketplace

- Producer product creation and editing
- Category browsing
- Product search
- Organic-product filtering
- Seasonal availability
- Allergen information
- Farm and producer origin information
- Stock and low-stock thresholds
- Automatic low-stock notifications

### Cart and checkout

- Persistent database-backed shopping cart
- Quantity updates and item removal
- Products grouped by producer
- Single-producer checkout
- Multi-producer checkout
- Minimum 48-hour delivery rule
- Simulated MockPay payment
- Transactional stock reduction
- Permanent product and price snapshots
- Five percent network commission calculation

### Order management

- Customer order history
- Separate producer portions within a multi-producer order
- Producer incoming-order dashboard
- Controlled status progression
- Order status audit history
- Customer and producer notifications

### Financial reporting

- Producer settlement reports
- Delivered-order payment totals
- Five percent commission and 95 percent producer allocation
- UK tax-year running totals
- Administrator commission reports
- Producer and status filters
- CSV export

### REST API

- Public category API
- Public available-product API
- Producer-owned product CRUD API
- Customer-owned order API
- Producer-owned incoming-order API
- Search, filtering and ordering
- Role and ownership isolation

## Technology Stack

- Python 3.12
- Django 5.2
- Django REST Framework
- django-filter
- PostgreSQL 16
- Docker and Docker Compose
- Gunicorn
- WhiteNoise
- HTML and CSS
- SQLite for direct non-Docker development

## Architecture

The Docker application uses two services:

```text
Browser
   |
   v
Django and Gunicorn web container
   |
   v
PostgreSQL database container