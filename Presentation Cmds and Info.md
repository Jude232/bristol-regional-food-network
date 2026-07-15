# confirm PostgreSQL
docker compose exec web python manage.py shell -c "from django.db import connection; print(connection.vendor)"


# Enter PostgreSQL
docker compose exec db psql -U brfn_user -d brfn_marketplace

# List the database tables
\dt

# Show Users
SELECT email, first_name, last_name, role
FROM accounts_user
ORDER BY email;

# Show Produces
SELECT id, name, price, stock_quantity, availability_status
FROM marketplace_product
ORDER BY name;

# Show Orders
SELECT order_number, status, payment_status, total_amount
FROM orders_order
ORDER BY created_at DESC;

# Exit PostgreSQL
\q


# Key Project Files

## `accounts/models.py`

Stores the database models used for user accounts.

It includes:

- Custom user model
- Email-based login
- User roles
- Producer profiles
- Customer profiles
- Authentication event records
- Login, logout and failed-login audit information

## `marketplace/models.py`

Stores the database models used for the product catalogue.

It includes:

- Product categories
- Product names and descriptions
- Producer relationships
- Prices and selling units
- Stock quantities
- Low-stock thresholds
- Seasonal availability
- Harvest and best-before dates
- Allergen information
- Organic certification details


## `orders/models.py`

Stores the database models used for shopping, checkout and order management.

It includes:

- Customer shopping carts
- Cart items and quantities
- Customer orders
- Producer-specific orders
- Purchased order items
- Commission and producer payment totals
- Mock payment transactions
- Order status history
- Customer and producer notifications


## `orders/reporting.py`

Contains the logic used to create financial reports.

It includes:

- Five percent commission calculations
- Producer payment calculations
- Weekly settlement date ranges
- UK tax-year totals
- Producer settlement data
- Administrator commission report data
- Report filtering and totals

This file does not store records directly. It reads order information from the database and prepares it for reports.


## `accounts/security.py`

Contains the authentication security logic.

It includes:

- Email normalisation
- Client IP address detection
- Browser user-agent recording
- Authentication event logging
- Failed-login counting
- Login throttling
- Temporary blocking after repeated failed attempts

Authentication events created by this file are stored using the `AuthenticationEvent` model in `accounts/models.py`.


## `api/permissions.py`

Contains the access-control rules used by the REST API.

It controls:

- Which API endpoints require authentication
- Which endpoints producers can access
- Which endpoints customers can access
- Whether a user owns the requested record
- Whether producers can only manage their own products
- Whether customers can only view their own orders

This file does not store data. It checks the logged-in user's role and ownership before allowing access.


## `docker-compose.yml`

Stores the Docker service configuration for the project.

It defines:

- The Django web container
- The PostgreSQL database container
- Environment variables
- Database connection details
- Container dependencies
- Port mapping
- PostgreSQL health checks
- Persistent database volumes
- Application startup settings

This allows the Django application and PostgreSQL database to run together as a multi-container system.