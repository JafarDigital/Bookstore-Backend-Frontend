# 📚 Bookstore Backend & Frontend

This is a full-stack bookstore application with a FastAPI backend and a frontend interface. The project supports user authentication, book management, reviews, and caching using Redis.

## Features

🔐 User Authentication: JWT-based login & registration with 2FA

📚 Book Management: CRUD operations for books with categories

⭐ Reviews & Ratings: Periodic scraping & rating updates

🛒 Cart & Orders: Temporary order storage & VIP user roles

⚡ Performance: Redis caching

🛠 Admin & Moderator Panel: Role-based access control (RBAC)

## To be finished

Fix for 2FA

Proper auth for admin panel

The admin endpoints:

api/admin/dashboard
api/admin/orders 
api/admin/books
api/admin/categories
api/admin/promotions
api/admin/users

## 🏗️ Tech Stack

Backend: FastAPI, PostgreSQL, Redis, SQLAlchemy, Pydantic

Frontend: HTML, CSS, Jinja2 Templates, JavaScript

Security: JWT, 2FA, Role-Based Access Control (RBAC)

Deployment: Docker (optional)


## Installation & Setup

### 1️⃣ Clone the repository

### 2️⃣ Set up a virtual environment

### 3️⃣ Install requirements

### 4️⃣ Configure the database in main.py

### 5️⃣ Configure Redis and admin endpoints if necessary 

### 6️⃣ Use dummy-books.py to add books into the database 

### 7️⃣ Run the application (uvicorn app.main:app --reload) 

Access the API at: http://127.0.0.1:8000
