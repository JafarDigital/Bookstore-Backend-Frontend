from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum

# Дефиниция на енумерация, която съвпада с UserRole от models.py
class UserRoleEnum(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    VIP = "vip"
    USER = "user"

# Дефиниция на енумерация, която съвпада с OrderStatus от models.py 
class OrderStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

# User schemas
class UserBase(BaseModel):
    email: str
    username: str
    
class UserCreate(UserBase):
    password: str
    phone: Optional[str] = None
    full_name: Optional[str] = None

class UserResponse(UserBase):
    id: int
    role: UserRoleEnum
    is_active: bool
    full_name: Optional[str] = None
    phone: Optional[str] = None
    two_factor_enabled: Optional[bool] = None
    
    class Config:
        orm_mode = True

class UserListResponse(UserBase):
    id: int
    role: UserRoleEnum
    is_active: bool
    full_name: Optional[str] = None
    phone: Optional[str] = None
    total_spent: Optional[float] = None

    class Config:
        orm_mode = True

# Book schemas
class CategoryBase(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

class PromotionInfo(BaseModel):
    discount_percentage: float
    end_date: str
    id: Optional[int] = None
    start_date: Optional[str] = None
    description: Optional[str] = None

    class Config:
        orm_mode = True

class BookBase(BaseModel):
    id: int
    title: str
    
    class Config:
        orm_mode = True

class BookListItem(BookBase):
    publisher: str
    price: float
    in_stock: bool
    stock_count: int
    categories: List[CategoryBase]
    goodreads_rating: Optional[float] = None
    promotion: Optional[PromotionInfo] = None
    discounted_price: Optional[float] = None
    
    class Config:
        orm_mode = True

class ReviewInfo(BaseModel):
    id: int
    rating: int
    comment: Optional[str] = None
    user: str
    created_at: str
    
    class Config:
        orm_mode = True

class BookDetail(BookBase):
    original_title: str
    publisher: str
    translator: Optional[str] = None
    pages: Optional[int] = None
    price: float
    cover_type: str
    language: str
    weight: Optional[float] = None
    dimensions: Optional[str] = None
    isbn: str
    description: Optional[str] = None
    in_stock: bool
    stock_count: int
    categories: List[CategoryBase]
    goodreads_id: Optional[str] = None
    goodreads_rating: Optional[float] = None
    reviews: List[ReviewInfo]
    promotion: Optional[PromotionInfo] = None
    discounted_price: Optional[float] = None
    
    class Config:
        orm_mode = True

class BookCreate(BaseModel):
    id: int
    title: str
    isbn: str
    price: float
    message: str
    
    class Config:
        orm_mode = True

# Review schemas
class ReviewBase(BaseModel):
    id: int
    book_id: int
    rating: int
    
    class Config:
        orm_mode = True

class ReviewCreate(ReviewBase):
    message: str
    
    class Config:
        orm_mode = True

class ReviewDetail(ReviewBase):
    user_id: int
    username: str
    comment: Optional[str] = None
    created_at: str
    
    class Config:
        orm_mode = True

# Category schemas
class CategoryDetail(CategoryBase):
    description: Optional[str] = None
    subcategory_ids: List[int]
    book_count: int
    
    class Config:
        orm_mode = True

class CategoryResponse(CategoryBase):
    message: str
    
    class Config:
        orm_mode = True

# Order schemas
class OrderItemDetail(BaseModel):
    book_id: int
    book_title: str
    quantity: int
    price_per_item: float
    discount: float
    total: float
    
    class Config:
        orm_mode = True

class OrderListItem(BaseModel):
    id: int
    total_price: float
    status: OrderStatusEnum
    created_at: str
    items_count: int
    shipping_address: Dict[str, Any]
    
    class Config:
        orm_mode = True

class OrderDetail(BaseModel):
    id: int
    user_id: int
    total_price: float
    status: OrderStatusEnum
    shipping_address: Dict[str, Any]
    phone: str
    created_at: str
    updated_at: str
    items: List[OrderItemDetail]
    
    class Config:
        orm_mode = True

class OrderCreate(BaseModel):
    id: int
    total_price: float
    status: OrderStatusEnum
    message: str
    order_reference: Optional[str] = None
    
    class Config:
        orm_mode = True

class OrderStatusUpdate(BaseModel):
    id: int
    status: OrderStatusEnum
    message: str
    
    class Config:
        orm_mode = True

# Promotion schemas
class PromotionBase(BaseModel):
    id: int
    book_id: int
    discount_percentage: float
    
    class Config:
        orm_mode = True

class PromotionCreate(PromotionBase):
    start_date: str
    end_date: str
    message: str
    
    class Config:
        orm_mode = True

class PromotionDetail(PromotionBase):
    book_title: str
    start_date: str
    end_date: str
    description: Optional[str] = None
    original_price: float
    discounted_price: float
    
    class Config:
        orm_mode = True

class PromotionBookDetail(PromotionBase):
    start_date: str
    end_date: str
    description: Optional[str] = None
    active: bool
    
    class Config:
        orm_mode = True

# Auth schemas
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str

class TokenWithTwoFactor(BaseModel):
    detail: str
    temporary_token: str
    two_fa_setup: Optional[Dict[str, Any]] = None

# Admin schemas
class BestsellerItem(BaseModel):
    id: int
    title: str
    price: float
    stock_count: int
    
    class Config:
        orm_mode = True

class TopRatedItem(BaseModel):
    id: int
    title: str
    goodreads_rating: float
    
    class Config:
        orm_mode = True

class RevenueResponse(BaseModel):
    start_date: str
    end_date: str
    revenue: float
    
    class Config:
        orm_mode = True

class CategoryRevenue(BaseModel):
    category_id: int
    category_name: str
    revenue: float
    
    class Config:
        orm_mode = True

# Общи отговори за съобщения
class MessageResponse(BaseModel):
    message: str

class SubcategoryResponse(BaseModel):
    parent_id: int
    child_id: int
    message: str
