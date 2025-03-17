from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Table, Text, DateTime, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

# Междинна таблица за връзка между книги и категории
book_category = Table(
    'book_category',
    Base.metadata,
    Column('book_id', Integer, ForeignKey('books.id')),
    Column('category_id', Integer, ForeignKey('categories.id'))
)

# Междинна таблица за връзка между категории и подкатегории
category_subcategory = Table(
    'category_subcategory',
    Base.metadata,
    Column('parent_id', Integer, ForeignKey('categories.id')),
    Column('child_id', Integer, ForeignKey('categories.id'))
)

class UserRole(enum.Enum):
    USER = "user"
    VIP = "vip"
    MODERATOR = "moderator"
    ADMIN = "admin"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    phone = Column(String)
    full_name = Column(String)
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)
    total_spent = Column(Float, default=0.0)  # Для определения VIP-статуса
    
    # Отношения
    orders = relationship("Order", back_populates="user")
    reviews = relationship("Review", back_populates="user")


class TempUser(Base):
    __tablename__ = 'temp_users'
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    phone = Column(String, nullable=False)
    full_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    orders = relationship("Order", back_populates="temp_user")


class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    
    # Отношения
    books = relationship("Book", secondary=book_category, back_populates="categories")
    parent_categories = relationship(
        "Category",
        secondary=category_subcategory,
        primaryjoin=id==category_subcategory.c.child_id,
        secondaryjoin=id==category_subcategory.c.parent_id,
        backref="subcategories"
    )


class Book(Base):
    __tablename__ = 'books'
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    original_title = Column(String, index=True)
    publisher = Column(String)
    translator = Column(String, nullable=True)
    pages = Column(Integer)
    price = Column(Float, nullable=False)
    cover_type = Column(String)  # тип обложки (твердая, мягкая и т.д.)
    language = Column(String)
    weight = Column(Float)  # в граммах
    dimensions = Column(String)  # например "210x148x15 мм"
    isbn = Column(String, unique=True, index=True)
    description = Column(Text)
    stock_count = Column(Integer, default=0)
    goodreads_id = Column(String, nullable=True)
    goodreads_rating = Column(Float, nullable=True)
    goodreads_rating_updated = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    categories = relationship("Category", secondary=book_category, back_populates="books")
    promotions = relationship("Promotion", back_populates="book")
    reviews = relationship("Review", back_populates="book")
    order_items = relationship("OrderItem", back_populates="book")


class Review(Base):
    __tablename__ = 'reviews'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    book_id = Column(Integer, ForeignKey('books.id'))
    rating = Column(Integer, nullable=False)  # от 1 до 5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    user = relationship("User", back_populates="reviews")
    book = relationship("Book", back_populates="reviews")


class Promotion(Base):
    __tablename__ = 'promotions'
    
    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey('books.id'))
    discount_percentage = Column(Float, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    book = relationship("Book", back_populates="promotions")


class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    temp_user_id = Column(Integer, ForeignKey('temp_users.id'), nullable=True)
    total_price = Column(Float, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    shipping_address = Column(JSON)  # JSON с адресом доставки
    phone = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    user = relationship("User", back_populates="orders", foreign_keys=[user_id])
    temp_user = relationship("TempUser", back_populates="orders", foreign_keys=[temp_user_id])
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = 'order_items'
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    book_id = Column(Integer, ForeignKey('books.id'))
    quantity = Column(Integer, nullable=False)
    price_per_item = Column(Float, nullable=False)  # Цена на момент покупки
    discount = Column(Float, default=0.0)  # Скидка в процентах
    
    # Отношения
    order = relationship("Order", back_populates="items")
    book = relationship("Book", back_populates="order_items")
