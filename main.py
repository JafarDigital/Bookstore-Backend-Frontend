from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.requests import Request
from sqlalchemy.orm import Session
from app.db.security import decode_token
from fastapi import Query
from typing import Union
from datetime import datetime

from app.schemas import (
	UserResponse, UserListResponse, BookListItem, BookDetail, BookCreate, 
	ReviewCreate, ReviewDetail, CategoryDetail, CategoryResponse, 
	OrderListItem, OrderDetail, OrderCreate, OrderStatusUpdate,
	PromotionCreate, PromotionDetail, PromotionBookDetail,
	Token, TokenWithTwoFactor, BestsellerItem, TopRatedItem,
	RevenueResponse, CategoryRevenue, MessageResponse, SubcategoryResponse
)
from typing import Optional, List, Dict, Any
import asyncio
import os
import logging
from datetime import datetime, timedelta

# Импортираме нашите модули
from app.db.models import (
	Base, User, Book, Category, Order, 
	Promotion, Review, UserRole, OrderStatus
)
from app.db.security import (
	rate_limit_middleware, get_current_user, 
	check_admin, check_moderator, check_authenticated,
	authenticate_endpoint, verify_2fa_endpoint, setup_2fa_endpoint
)
from app.db.cache import get_cache, RedisCache
from app.db.scraping import init_goodreads_updater, manual_update_book, fetch_book_details

# Импортираме CRUD операции
import app.crud as crud

# Настройваме базата данни
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Настройки за базата данни от environment променливи
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_SERVER = os.getenv("POSTGRES_SERVER", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "bookshop")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Създаваме енджин за базата данни
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Зависимост за инжектиране на DB сесия
def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

# Настройваме логовете
logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(message)s",
	handlers=[
		logging.StreamHandler()
	]
)

logger = logging.getLogger(__name__)

# Създаваме FastAPI приложение
app = FastAPI(
	title="Bookshop API",
	description="API за верига книжарници",
	version="1.0.0"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token")

# Добавяме middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Добавяме rate limiting middleware
@app.middleware("http")
async def rate_limit(request: Request, call_next):
	return await rate_limit_middleware(request, call_next)

# Свързваме с папките за статични файлове и шаблони
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Функция за инициализация
@app.on_event("startup")
async def startup_event():
	# Създаваме таблиците в базата данни, ако не съществуват
	Base.metadata.create_all(bind=engine)
	
	# Инициализираме Redis кеша
	cache = get_cache()
	
	# Стартираме Goodreads updater
	goodreads_updater = init_goodreads_updater(lambda: SessionLocal())
	goodreads_updater.start()
	
	# Създаваме admin потребител, ако не съществува
	db = SessionLocal()
	
	# Проверяваме дали има admin потребител
	admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
	if not admin:
		# Създаваме admin потребител
		from app.db.security import get_password_hash
		admin_user = User(
			email="admin@bookshop.com",
			username="admin",
			hashed_password=get_password_hash("Admin123!"),
			role=UserRole.ADMIN,
			is_active=True,
			full_name="Admin User"
		)
		db.add(admin_user)
		db.commit()
		
		logger.info("Created default admin user")
	
	# Затваряме сесията
	db.close()
	
	logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
	logger.info("Application shutdown")

# Обработка на грешки
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
	# Log the error
	logger.error(f"Unexpected error: {str(exc)}")
	
	# Return appropriate response
	if isinstance(exc, HTTPException):
		return templates.TemplateResponse(
			"error.html",
			{"request": request, "status_code": exc.status_code, "detail": exc.detail}
		)
	else:
		return templates.TemplateResponse(
			"error.html",
			{"request": request, "status_code": 500, "detail": "Internal Server Error"}
		)

# Основни API точки

# --- Автентикация ---

@app.post("/api/token", response_model=Union[Token, TokenWithTwoFactor])
async def login_for_access_token(
	form_data: OAuth2PasswordRequestForm = Depends(),
	db: Session = Depends(get_db)
):
	"""Точка за достъп за автентикация и получаване на токени"""
	return await authenticate_endpoint(
		form_data.username, 
		form_data.password, 
		db
	)

@app.post("/api/token/verify-2fa", response_model=Token)
async def verify_2fa(
	token: str = Form(...),
	totp_code: str = Form(...),
	db: Session = Depends(get_db)
):
	"""Верифицира 2FA код след първоначалната автентикация"""
	return await verify_2fa_endpoint(token, totp_code, db)

@app.post("/api/token/setup-2fa", response_model=Token)
async def setup_2fa(
	token: str = Form(...),
	totp_code: str = Form(...),
	db: Session = Depends(get_db)
):
	"""Завършва настройката на 2FA"""
	return await setup_2fa_endpoint(token, totp_code, db)

@app.post("/api/token/refresh", response_model=Token)
async def refresh_token(refresh_token: str = Form(...)):
	"""Обновява access token с refresh token"""
	from app.db.security import SecurityUtils
	return SecurityUtils.refresh_access_token(refresh_token)

# --- Потребители ---

@app.post("/api/users/register", response_model=UserResponse)
async def register_user(
	email: str = Form(...),
	username: str = Form(...),
	password: str = Form(...),
	phone: str = Form(None),
	full_name: str = Form(None),
	db: Session = Depends(get_db)
):
	"""Регистрация на нов потребител"""
	# Проверяваме дали потребителското име е заето
	db_user = crud.get_user_by_username(db, username)
	if db_user:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Username already registered"
		)
	
	# Проверяваме дали email адресът е зает
	db_user = crud.get_user_by_email(db, email)
	if db_user:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Email already registered"
		)
	
	# Проверяваме силата на паролата
	from app.db.security import SecurityUtils
	if not SecurityUtils.validate_password_strength(password):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Password is too weak. It must be at least 8 characters long and contain uppercase, lowercase, digits and special characters."
		)
	
	# Създаваме потребителя
	user = crud.create_user(db, email, username, password, phone, full_name)
	
	# Връщаме данните без паролата
	return {
		"id": user.id,
		"email": user.email,
		"username": user.username,
		"role": user.role.value,
		"is_active": user.is_active
	}

@app.get("/api/users/me")  # Без response_model
async def read_users_me(
	token: str = Depends(oauth2_scheme), 
	db: Session = Depends(get_db)
):
	"""Връща информация за текущия потребител"""
	# Имплементирайте логиката директно тук, без да разчитате на get_current_user
	token_data = decode_token(token)
	
	from app.crud import get_user
	
	user = get_user(db, int(token_data.user_id))
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="User not found"
		)
	
	if not user.is_active:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Inactive user"
		)
	
	# Връщаме ръчно създаден речник вместо User обект
	return {
		"id": user.id,
		"email": user.email,
		"username": user.username,
		"role": user.role.value,
		"is_active": user.is_active,
		"full_name": user.full_name,
		"phone": user.phone,
		"two_factor_enabled": user.two_factor_enabled
	}

@app.route("/api/users/{user_id}/role", methods=["PUT"])
async def update_user_role(
	user_id: int,
	role: UserRole,
	current_user: User = Depends(check_admin)):
	"""Обновява ролята на потребител (само за admin)"""
	# Създаваме DB сесия локално във функцията
	db = SessionLocal()
	try:
		user = crud.update_user_role(db, user_id, role)
		return {
			"id": user.id,
			"username": user.username,
			"role": user.role.value,
			"email": user.email,
			"is_active": user.is_active
		}
	finally:
		# Не забравяме да затворим сесията накрая
		db.close()

@app.route("/api/users/{user_id}/activate", methods=["PUT"])
async def activate_user(
	user_id: int,
	is_active: bool,
	current_user: User = Depends(check_admin),
	db: Session = Depends(get_db)
):
	"""Активира или деактивира потребител (само за admin)"""
	user = crud.update_user(db, user_id, {"is_active": is_active})
	return {
		"id": user.id,
		"username": user.username,
		"email": user.email,
		"role": user.role.value,
		"is_active": user.is_active
	}

# --- Книги ---

@app.get("/api/books")
async def list_books(
	skip: int = 0,
	limit: int = 100,
	search: str = None,
	category_id: int = None,
	in_stock: bool = None,
	db: Session = Depends(get_db),
	cache: RedisCache = Depends(get_cache)
):
	"""Връща списък с книги"""
	# Проверяваме дали резултатът е в кеша
	from app.db.cache import get_book_search_cache_key
	
	cache_key = get_book_search_cache_key(
		query=search or "",
		category_id=category_id,
		in_stock=in_stock
	)
	
	# Проверяваме кеша
	cached_result = cache.get(cache_key)
	if cached_result:
		return cached_result
	
	# Извличаме книги от базата данни
	books = crud.get_books(
		db,
		skip=skip,
		limit=limit,
		search=search,
		category_id=category_id,
		in_stock=in_stock
	)
	
	# Форматираме резултатите
	result = []
	for book in books:
		# Проверяваме за активни промоции
		promo = None
		for promotion in book.promotions:
			now = datetime.utcnow()
			if promotion.start_date <= now <= promotion.end_date:
				if promo is None or promotion.discount_percentage > promo.discount_percentage:
					promo = promotion
		
		book_data = {
			"id": book.id,
			"title": book.title,
			"publisher": book.publisher,
			"price": book.price,
			"in_stock": book.stock_count > 0,
			"stock_count": book.stock_count,
			"categories": [{"id": cat.id, "name": cat.name} for cat in book.categories],
			"goodreads_rating": book.goodreads_rating
		}
		
		if promo:
			book_data["promotion"] = {
				"discount_percentage": promo.discount_percentage,
				"end_date": promo.end_date.isoformat()
			}
			book_data["discounted_price"] = book.price * (1 - promo.discount_percentage / 100)
		
		result.append(book_data)
	
	# Кешираме резултата за 10 минути
	cache.set(cache_key, result, expires=600)
	
	return result

def date_filter(date_str):
    if isinstance(date_str, str):
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date_obj.strftime('%d.%m.%Y %H:%M')
        except ValueError:
            return date_str
    elif isinstance(date_str, datetime):
        return date_str.strftime('%d.%m.%Y %H:%M')
    return date_str

# След това добавете филтъра към Jinja2 средата
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["date"] = date_filter

@app.get("/api/books/{book_id}")
async def get_book_detail(
	book_id: int,
	db: Session = Depends(get_db),
	cache: RedisCache = Depends(get_cache)
):
	"""Връща детайли за книга"""
	# Проверяваме кеша
	from app.db.cache import get_book_cache_key
	cache_key = get_book_cache_key(book_id)
	cached_result = cache.get(cache_key)
	
	if cached_result:
		return cached_result
	
	# Взимаме книгата и активната промоция, ако има такава
	book, active_promotion = crud.get_book_with_promotions(db, book_id)
	
	# Форматираме резултата
	result = {
		"id": book.id,
		"title": book.title,
		"original_title": book.original_title or book.title,
		"publisher": book.publisher,
		"translator": book.translator,
		"pages": book.pages,
		"price": book.price,
		"cover_type": book.cover_type,
		"language": book.language,
		"weight": book.weight,
		"dimensions": book.dimensions,
		"isbn": book.isbn,
		"description": book.description,
		"in_stock": book.stock_count > 0,
		"stock_count": book.stock_count,
		"categories": [{"id": cat.id, "name": cat.name} for cat in book.categories],
		"goodreads_id": book.goodreads_id,
		"goodreads_rating": book.goodreads_rating,
		"reviews": [
			{
				"id": review.id,
				"rating": review.rating,
				"comment": review.comment,
				"user": review.user.username,
				"created_at": review.created_at.isoformat()
			} for review in book.reviews
		]
	}
	
	if active_promotion:
		result["promotion"] = {
			"id": active_promotion.id,
			"discount_percentage": active_promotion.discount_percentage,
			"start_date": active_promotion.start_date.isoformat(),
			"end_date": active_promotion.end_date.isoformat(),
			"description": active_promotion.description
		}
		result["discounted_price"] = book.price * (1 - active_promotion.discount_percentage / 100)
	
	# Кешираме резултата за 1 час
	cache.set(cache_key, result, expires=3600)
	
	return result

def get_db_session(): # аа избягване на fastapi.exceptions.FastAPIError: Invalid args for response field! по-долу
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

# Дефинирайте функцията за обработка на заявката
async def create_book_endpoint(request: Request):
    # Получаване на form данни
    form_data = await request.form()
    
    # Извличане на данните от формата
    title = form_data.get("title")
    original_title = form_data.get("original_title")
    publisher = form_data.get("publisher")
    translator = form_data.get("translator")
    pages = int(form_data.get("pages")) if form_data.get("pages") else None
    price = float(form_data.get("price"))
    cover_type = form_data.get("cover_type")
    language = form_data.get("language")
    weight = float(form_data.get("weight")) if form_data.get("weight") else None
    dimensions = form_data.get("dimensions")
    isbn = form_data.get("isbn")
    description = form_data.get("description")
    stock_count = int(form_data.get("stock_count", 0))
    category_ids = [int(id) for id in form_data.getlist("category_ids")] if "category_ids" in form_data else []
    
    # Проверка на аутентикацията/роля (имитираме Depends(check_moderator))
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"detail": "Not authenticated"}, 
            status_code=401
        )
    
    token = auth_header.split(" ")[1]
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            # Проверяваме дали е модератор/админ
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized"}, 
                    status_code=403
                )
            
            # Проверяваме за съществуваща книга с този ISBN
            existing_book = crud.get_book_by_isbn(db, isbn)
            if existing_book:
                return JSONResponse(
                    {"detail": "Book with this ISBN already exists"},
                    status_code=400
                )
            
            # Подготвяме данните за книгата
            book_data = {
                "title": title,
                "original_title": original_title or title,
                "publisher": publisher,
                "translator": translator,
                "pages": pages,
                "price": price,
                "cover_type": cover_type,
                "language": language,
                "weight": weight,
                "dimensions": dimensions,
                "isbn": isbn,
                "description": description,
                "stock_count": stock_count
            }
            
            # Създаваме книгата
            book = crud.create_book(db, book_data)
            
            # Добавяме категориите
            if category_ids:
                categories = db.query(Category).filter(Category.id.in_(category_ids)).all()
                book.categories = categories
                db.commit()
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_book_cache
            invalidate_book_cache(cache, book.id)
            
            # Добавяме background task за Goodreads
            if "background_tasks" in request.scope:
                background_tasks = request.scope["background_tasks"]
                async def update_goodreads():
                    await manual_update_book(db, book.id)
                background_tasks.add_task(update_goodreads)
            
            # Връщаме успешен отговор
            return JSONResponse({
                "id": book.id,
                "title": book.title,
                "isbn": book.isbn,
                "price": book.price,
                "message": "Book created successfully"
            }, status_code=201)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse(
            {"detail": f"Error: {str(e)}"}, 
            status_code=500
        )

# Добавяме маршрута директно към FastAPI приложението
app.routes.append(
    Route("/api/books", create_book_endpoint, methods=["POST"])
)

@app.put("/api/books/{book_id}")
async def update_book(
	# Параметрите са дефинирани в предишния файл
):
	# ... (предишния код)
	
	# Обновяваме книгата
	updated_book = crud.update_book(db, book_id, update_data)
	
	# Инвалидираме кеша
	from app.db.cache import invalidate_book_cache
	invalidate_book_cache(cache, book_id)
	
	# Връщаме обновената книга
	return {
		"id": updated_book.id,
		"title": updated_book.title,
		"isbn": updated_book.isbn,
		"price": updated_book.price,
		"message": "Book updated successfully"
	}

async def delete_book(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    # Автентикация (имитираме Depends(check_admin))
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"detail": "Not authenticated"}, 
            status_code=401
        )
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя и проверяваме дали е админ
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role != UserRole.ADMIN:
                return JSONResponse(
                    {"detail": "Not authorized - admin role required"}, 
                    status_code=403
                )
            
            # Изтриваме книгата
            crud.delete_book(db, book_id)
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_book_cache
            invalidate_book_cache(cache, book_id)
            
            # Връщаме успешен отговор
            return JSONResponse({"message": "Book deleted successfully"})
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse(
            {"detail": f"Error: {str(e)}"}, 
            status_code=500
        )

# Добавяме маршрута директно към FastAPI приложението
app.routes.append(
    Route("/api/books/{book_id}", delete_book, methods=["DELETE"])
)

async def update_book_from_goodreads(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    # Проверка на аутентикацията (имитираме Depends(check_moderator))
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"detail": "Not authenticated"}, 
            status_code=401
        )
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя и проверяваме дали е модератор/админ
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Обновяваме информацията от Goodreads
            result = await manual_update_book(db, book_id)
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_book_cache
            invalidate_book_cache(cache, book_id)
            
            # Връщаме резултата
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse(
            {"detail": f"Error: {str(e)}"}, 
            status_code=500
        )

# Добавяме маршрута директно към FastAPI приложението
app.routes.append(
    Route("/api/books/{book_id}/update-goodreads", update_book_from_goodreads, methods=["POST"])
)


# --- Категории ---

@app.get("/api/categories")
async def list_categories(
	db: Session = Depends(get_db),
	cache: RedisCache = Depends(get_cache)
):
	"""Връща списък с всички категории"""
	# Проверяваме кеша
	from app.db.cache import get_category_cache_key
	cache_key = get_category_cache_key()
	cached_result = cache.get(cache_key)
	
	if cached_result:
		return cached_result
	
	# Взимаме категориите от базата данни
	categories = crud.get_categories(db)
	
	# Форматираме резултата
	result = []
	for category in categories:
		# Изграждаме списък с ID-та на подкатегориите
		subcategory_ids = [subcategory.id for subcategory in category.subcategories]
		
		result.append({
			"id": category.id,
			"name": category.name,
			"description": category.description,
			"subcategory_ids": subcategory_ids,
			"book_count": len(category.books)
		})
	
	# Кешираме резултата за 1 час
	cache.set(cache_key, result, expires=3600)
	
	return result

async def create_category_endpoint(request: Request):
    # Извличаме form data
    form_data = await request.form()
    name = form_data.get("name")
    description = form_data.get("description")
    parent_id = int(form_data.get("parent_id")) if form_data.get("parent_id") else None
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя и проверяваме дали е модератор/админ
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Проверяваме дали категорията съществува
            existing_category = crud.get_category_by_name(db, name)
            if existing_category:
                return JSONResponse(
                    {"detail": "Category with this name already exists"},
                    status_code=400
                )
            
            # Създаваме категорията
            category = crud.create_category(db, name, description)
            
            # Ако е зададена родителска категория, добавяме връзката
            if parent_id:
                crud.add_subcategory(db, parent_id, category.id)
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_category_cache
            invalidate_category_cache(cache, category.id)
            
            return JSONResponse({
                "id": category.id,
                "name": category.name,
                "message": "Category created successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 2. Обновяване на категория
async def update_category_endpoint(request: Request):
    # Извличаме category_id от path параметрите
    category_id = int(request.path_params["category_id"])
    
    # Извличаме form data
    form_data = await request.form()
    name = form_data.get("name")
    description = form_data.get("description")
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя и проверяваме дали е модератор/админ
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Подготвяме данните за обновяване
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            
            # Обновяваме категорията
            category = crud.update_category(db, category_id, update_data)
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_category_cache
            invalidate_category_cache(cache, category_id)
            
            return JSONResponse({
                "id": category.id,
                "name": category.name,
                "message": "Category updated successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 3. Добавяне на подкатегория
async def add_subcategory_endpoint(request: Request):
    # Извличаме parent_id и child_id от path параметрите
    parent_id = int(request.path_params["parent_id"])
    child_id = int(request.path_params["child_id"])
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя и проверяваме дали е модератор/админ
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Добавяме подкатегорията
            category = crud.add_subcategory(db, parent_id, child_id)
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_category_cache
            invalidate_category_cache(cache, parent_id)
            invalidate_category_cache(cache, child_id)
            
            return JSONResponse({
                "parent_id": parent_id,
                "child_id": child_id,
                "message": "Subcategory added successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# Добавяме маршрутите
app.routes.append(Route("/api/categories", create_category_endpoint, methods=["POST"]))
app.routes.append(Route("/api/categories/{category_id}", update_category_endpoint, methods=["PUT"]))
app.routes.append(Route("/api/categories/{parent_id}/subcategories/{child_id}", add_subcategory_endpoint, methods=["POST"]))

# --- Отзиви ---

async def create_review_endpoint(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    # Извличаме form data
    form_data = await request.form()
    rating = int(form_data.get("rating"))
    comment = form_data.get("comment")
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if not current_user:
                return JSONResponse({"detail": "User not found"}, status_code=404)
            
            # Създаваме отзива
            review = crud.create_review(db, current_user.id, book_id, rating, comment)
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_book_cache
            invalidate_book_cache(cache, book_id)
            
            return JSONResponse({
                "id": review.id,
                "book_id": review.book_id,
                "rating": review.rating,
                "message": "Review created successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 2. Получаване на отзиви за книга
async def get_book_reviews_endpoint(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    # Извличаме query параметри
    skip = int(request.query_params.get("skip", 0))
    limit = int(request.query_params.get("limit", 100))
    
    try:
        db = SessionLocal()
        
        try:
            # Взимаме отзивите
            reviews = crud.get_book_reviews(db, book_id, skip, limit)
            
            # Форматираме резултата
            result = [{
                "id": review.id,
                "book_id": review.book_id,
                "user_id": review.user_id,
                "username": review.user.username,
                "rating": review.rating,
                "comment": review.comment,
                "created_at": review.created_at.isoformat()
            } for review in reviews]
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# Добавяме маршрутите
app.routes.append(Route("/api/books/{book_id}/reviews", create_review_endpoint, methods=["POST"]))
app.routes.append(Route("/api/books/{book_id}/reviews", get_book_reviews_endpoint, methods=["GET"]))

# --- Поръчки ---

async def create_order_endpoint(request: Request):
    # Извличаме form data
    form_data = await request.form()
    items = json.loads(form_data.get("items"))
    shipping_address = json.loads(form_data.get("shipping_address"))
    phone = form_data.get("phone")
    email = form_data.get("email")
    full_name = form_data.get("full_name")
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if not current_user:
                return JSONResponse({"detail": "User not found"}, status_code=404)
            
            # Създаваме поръчката
            order = crud.create_order(
                db,
                user_id=current_user.id,
                items=items,
                shipping_address=shipping_address,
                phone=phone
            )
            
            return JSONResponse({
                "id": order.id,
                "total_price": order.total_price,
                "status": order.status.value,
                "message": "Order created successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 2. Създаване на поръчка за нерегистриран потребител
async def create_guest_order_endpoint(request: Request):
    # Извличаме form data
    form_data = await request.form()
    items = json.loads(form_data.get("items"))
    shipping_address = json.loads(form_data.get("shipping_address"))
    phone = form_data.get("phone")
    email = form_data.get("email")
    full_name = form_data.get("full_name")
    
    try:
        db = SessionLocal()
        
        try:
            # Създаваме временен потребител
            temp_user = crud.create_temp_user(db, email, phone, full_name)
            
            # Създаваме поръчката
            order = crud.create_order(
                db,
                temp_user_id=temp_user.id,
                items=items,
                shipping_address=shipping_address,
                phone=phone
            )
            
            return JSONResponse({
                "id": order.id,
                "total_price": order.total_price,
                "status": order.status.value,
                "message": "Order created successfully",
                "order_reference": f"GU-{order.id}"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 3. Получаване на поръчки на потребител
async def get_user_orders_endpoint(request: Request):
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if not current_user:
                return JSONResponse({"detail": "User not found"}, status_code=404)
            
            # Взимаме поръчките
            orders = crud.get_user_orders(db, current_user.id)
            
            # Форматираме резултата
            result = [{
                "id": order.id,
                "total_price": order.total_price,
                "status": order.status.value,
                "created_at": order.created_at.isoformat(),
                "items_count": len(order.items),
                "shipping_address": order.shipping_address
            } for order in orders]
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 4. Получаване на детайли за поръчка
async def get_order_details_endpoint(request: Request):
    # Извличаме order_id от path параметрите
    order_id = int(request.path_params["order_id"])
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if not current_user:
                return JSONResponse({"detail": "User not found"}, status_code=404)
            
            # Взимаме поръчката
            order = crud.get_order(db, order_id)
            
            # Проверяваме дали поръчката съществува
            if not order:
                return JSONResponse({"detail": "Order not found"}, status_code=404)
            
            # Проверяваме дали поръчката принадлежи на текущия потребител
            # или потребителят е admin/moderator
            if (order.user_id != current_user.id and 
                current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]):
                return JSONResponse(
                    {"detail": "Not authorized to access this order"},
                    status_code=403
                )
            
            # Форматираме резултата
            result = {
                "id": order.id,
                "user_id": order.user_id,
                "total_price": order.total_price,
                "status": order.status.value,
                "shipping_address": order.shipping_address,
                "phone": order.phone,
                "created_at": order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat(),
                "items": [{
                    "book_id": item.book_id,
                    "book_title": item.book.title,
                    "quantity": item.quantity,
                    "price_per_item": item.price_per_item,
                    "discount": item.discount,
                    "total": item.quantity * item.price_per_item * (1 - item.discount / 100)
                } for item in order.items]
            }
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 5. Обновяване на статус на поръчка
async def update_order_status_endpoint(request: Request):
    # Извличаме order_id от path параметрите
    order_id = int(request.path_params["order_id"])
    
    # Извличаме form data
    form_data = await request.form()
    status = form_data.get("status")
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Конвертираме статуса към enum
            order_status = OrderStatus(status)
            
            # Обновяваме статуса
            order = crud.update_order_status(db, order_id, order_status)
            
            return JSONResponse({
                "id": order.id,
                "status": order.status.value,
                "message": "Order status updated successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 6. Отказване на поръчка
async def cancel_order_endpoint(request: Request):
    # Извличаме order_id от path параметрите
    order_id = int(request.path_params["order_id"])
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if not current_user:
                return JSONResponse({"detail": "User not found"}, status_code=404)
            
            # Взимаме поръчката
            order = crud.get_order(db, order_id)
            
            # Проверяваме дали поръчката съществува
            if not order:
                return JSONResponse({"detail": "Order not found"}, status_code=404)
            
            # Проверяваме дали поръчката принадлежи на текущия потребител
            # или потребителят е admin/moderator
            if (order.user_id != current_user.id and 
                current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]):
                return JSONResponse(
                    {"detail": "Not authorized to cancel this order"},
                    status_code=403
                )
            
            # Отказваме поръчката
            cancelled_order = crud.cancel_order(db, order_id)
            
            return JSONResponse({
                "id": cancelled_order.id,
                "status": cancelled_order.status.value,
                "message": "Order cancelled successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# Добавяме маршрутите
app.routes.append(Route("/api/orders", create_order_endpoint, methods=["POST"]))
app.routes.append(Route("/api/guest-orders", create_guest_order_endpoint, methods=["POST"]))
app.routes.append(Route("/api/orders", get_user_orders_endpoint, methods=["GET"]))
app.routes.append(Route("/api/orders/{order_id}", get_order_details_endpoint, methods=["GET"]))
app.routes.append(Route("/api/orders/{order_id}/status", update_order_status_endpoint, methods=["PUT"]))
app.routes.append(Route("/api/orders/{order_id}/cancel", cancel_order_endpoint, methods=["POST"]))

# --- Промоции ---

async def create_promotion_endpoint(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    # Извличаме form data
    form_data = await request.form()
    discount_percentage = float(form_data.get("discount_percentage"))
    start_date = datetime.fromisoformat(form_data.get("start_date"))
    end_date = datetime.fromisoformat(form_data.get("end_date"))
    description = form_data.get("description")
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Създаваме промоцията
            promotion = crud.create_promotion(
                db,
                book_id=book_id,
                discount_percentage=discount_percentage,
                start_date=start_date,
                end_date=end_date,
                description=description,
                created_by=current_user.id
            )
            
            # Инвалидираме кеша
            cache = get_cache()
            from app.db.cache import invalidate_book_cache
            invalidate_book_cache(cache, book_id)
            
            return JSONResponse({
                "id": promotion.id,
                "book_id": promotion.book_id,
                "discount_percentage": promotion.discount_percentage,
                "start_date": promotion.start_date.isoformat(),
                "end_date": promotion.end_date.isoformat(),
                "message": "Promotion created successfully"
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 2. Получаване на активни промоции
async def get_active_promotions_endpoint(request: Request):
    try:
        db = SessionLocal()
        
        try:
            # Взимаме активните промоции
            promotions = crud.get_active_promotions(db)
            
            # Форматираме резултата
            result = [{
                "id": promo.id,
                "book_id": promo.book_id,
                "book_title": promo.book.title,
                "discount_percentage": promo.discount_percentage,
                "start_date": promo.start_date.isoformat(),
                "end_date": promo.end_date.isoformat(),
                "description": promo.description,
                "original_price": promo.book.price,
                "discounted_price": promo.book.price * (1 - promo.discount_percentage / 100)
            } for promo in promotions]
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 3. Получаване на промоции за книга
async def get_book_promotions_endpoint(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    try:
        db = SessionLocal()
        
        try:
            # Взимаме промоциите за книгата
            promotions = crud.get_book_promotions(db, book_id)
            
            # Форматираме резултата
            result = [{
                "id": promo.id,
                "book_id": promo.book_id,
                "discount_percentage": promo.discount_percentage,
                "start_date": promo.start_date.isoformat(),
                "end_date": promo.end_date.isoformat(),
                "description": promo.description,
                "active": (
                    promo.start_date <= datetime.utcnow() and
                    promo.end_date >= datetime.utcnow()
                )
            } for promo in promotions]
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# Добавяме маршрутите
app.routes.append(Route("/api/books/{book_id}/promotions", create_promotion_endpoint, methods=["POST"]))
app.routes.append(Route("/api/promotions", get_active_promotions_endpoint, methods=["GET"]))
app.routes.append(Route("/api/books/{book_id}/promotions", get_book_promotions_endpoint, methods=["GET"]))

# --- Админски функции ---

async def get_bestsellers_endpoint(request: Request):
    # Извличаме query параметри
    limit = int(request.query_params.get("limit", 10))
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Проверяваме кеша
            cache = get_cache()
            cache_key = "bestsellers"
            cached_result = cache.get(cache_key)
            
            if cached_result:
                return JSONResponse(cached_result)
            
            # Взимаме бестселърите
            bestsellers = crud.get_bestsellers(db, limit)
            
            # Форматираме резултата
            result = [{
                "id": book.id,
                "title": book.title,
                "price": book.price,
                "stock_count": book.stock_count
            } for book in bestsellers]
            
            # Кешираме резултата
            cache.set(cache_key, result, expires=3600)
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 2. Получаване на най-високо оценените книги
async def get_top_rated_endpoint(request: Request):
    # Извличаме query параметри
    limit = int(request.query_params.get("limit", 10))
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return JSONResponse(
                    {"detail": "Not authorized - moderator or admin role required"}, 
                    status_code=403
                )
            
            # Проверяваме кеша
            cache = get_cache()
            cache_key = "top_rated"
            cached_result = cache.get(cache_key)
            
            if cached_result:
                return JSONResponse(cached_result)
            
            # Взимаме най-високо оценените книги
            top_rated = crud.get_top_rated_books(db, limit)
            
            # Форматираме резултата
            result = [{
                "id": book.id,
                "title": book.title,
                "goodreads_rating": book.goodreads_rating
            } for book in top_rated]
            
            # Кешираме резултата
            cache.set(cache_key, result, expires=3600)
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 3. Получаване на приходи за период
async def get_revenue_endpoint(request: Request):
    # Извличаме query параметри
    start_date = datetime.fromisoformat(request.query_params.get("start_date"))
    end_date = datetime.fromisoformat(request.query_params.get("end_date"))
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role != UserRole.ADMIN:
                return JSONResponse(
                    {"detail": "Not authorized - admin role required"}, 
                    status_code=403
                )
            
            # Вземаме приходите
            revenue = crud.get_revenue_by_period(db, start_date, end_date)
            
            return JSONResponse({
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "revenue": revenue
            })
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# 4. Получаване на приходи по категории
async def get_revenue_by_category_endpoint(request: Request):
    # Извличаме query параметри
    start_date = datetime.fromisoformat(request.query_params.get("start_date"))
    end_date = datetime.fromisoformat(request.query_params.get("end_date"))
    
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role != UserRole.ADMIN:
                return JSONResponse(
                    {"detail": "Not authorized - admin role required"}, 
                    status_code=403
                )
            
            # Вземаме приходите по категории
            revenues = crud.get_revenue_by_category(db, start_date, end_date)
            
            # Форматираме резултата
            result = [{
                "category_id": category.id,
                "category_name": category.name,
                "revenue": revenue
            } for category, revenue in revenues]
            
            return JSONResponse(result)
            
        finally:
            db.close()
            
    except Exception as e:
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)

# Добавяме маршрутите
app.routes.append(Route("/api/admin/bestsellers", get_bestsellers_endpoint, methods=["GET"]))
app.routes.append(Route("/api/admin/top-rated", get_top_rated_endpoint, methods=["GET"]))
app.routes.append(Route("/api/admin/revenue", get_revenue_endpoint, methods=["GET"]))
app.routes.append(Route("/api/admin/revenue-by-category", get_revenue_by_category_endpoint, methods=["GET"]))

# --- Уеб интерфейс ---

# 1. Начална страница
async def home_endpoint(request: Request):
    try:
        db = SessionLocal()
        
        try:
            # Взимаме бестселърите и новите книги
            bestsellers = crud.get_bestsellers(db, 6)
            new_books = db.query(Book).order_by(Book.created_at.desc()).limit(6).all()
            
            # Използваме Jinja2Templates
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "bestsellers": bestsellers,
                    "new_books": new_books
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": 500, "detail": f"Error: {str(e)}"}
        )

# 2. Страница с детайли за книга
async def book_detail_page_endpoint(request: Request):
    # Извличаме book_id от path параметрите
    book_id = int(request.path_params["book_id"])
    
    try:
        db = SessionLocal()
        
        try:
            # Взимаме книгата
            book, promotion = crud.get_book_with_promotions(db, book_id)
            
            # Използваме Jinja2Templates
            return templates.TemplateResponse(
                "book.html",
                {
                    "request": request,
                    "book": book,
                    "promotion": promotion
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": 500, "detail": f"Error: {str(e)}"}
        )

# 3. Страница за търсене
async def search_page_endpoint(request: Request):
    # Извличаме query параметри
    query = request.query_params.get("query")
    category_id = int(request.query_params.get("category_id")) if request.query_params.get("category_id") else None
    
    min_price = None
    max_price = None
    in_stock = True
    sort_by = "title"  # по подразбиране
    sort_desc = False  # по подразбиране
    
    if request.query_params.get("min_price"):
        try:
            min_price = float(request.query_params.get("min_price"))
        except ValueError:
            pass
            
    if request.query_params.get("max_price"):
        try:
            max_price = float(request.query_params.get("max_price"))
        except ValueError:
            pass
            
    if request.query_params.get("in_stock"):
        in_stock = request.query_params.get("in_stock") == "true"
        
    if request.query_params.get("sort_by"):
        sort_by = request.query_params.get("sort_by")
        
    if request.query_params.get("sort_desc"):
        sort_desc = request.query_params.get("sort_desc") == "true"
    
    try:
        db = SessionLocal()
        
        try:
            # Взимаме резултатите от търсенето
            books = crud.get_books(
                db,
                search=query,
                category_id=category_id,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
            
            # Взимаме всички категории за филтриране
            categories = crud.get_categories(db)
            
            # Използваме Jinja2Templates
            return templates.TemplateResponse(
                "search.html",
                {
                    "request": request,
                    "books": books,
                    "categories": categories,
                    "query": query,
                    "category_id": category_id,
                    "now": datetime.utcnow()  # For promotion checks
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": 500, "detail": f"Error: {str(e)}"}
        )

# 4. Страница за вход
async def login_page_endpoint(request: Request, next: str = "/"):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

# 5. Страница за регистрация
async def register_page_endpoint(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request}
    )

# 6. Страница за забравена парола
async def forgotten_password_page_endpoint(request: Request):
    return templates.TemplateResponse(
        "forgotten-password.html",
        {"request": request}
    )

# 7. Страница за поръчка
async def order_page_endpoint(request: Request):
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    current_user = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        
        try:
            # Проверяваме токена
            token_data = decode_token(token)
            db = SessionLocal()
            
            try:
                # Взимаме потребителя
                from app.crud import get_user
                current_user = get_user(db, int(token_data.user_id))
            finally:
                db.close()
        except:
            pass
    
    return templates.TemplateResponse(
        "order.html",
        {
            "request": request,
            "user": current_user
        }
    )

@app.get("/profile")
async def profile_page(request: Request):
    return templates.TemplateResponse(
        "profile.html",
        {"request": request}
    )

@app.get("/orders")
async def orders_page(request: Request):
    return templates.TemplateResponse(
        "orders.html",
        {"request": request}
    )

@app.get("/cart")
async def cart_page(request: Request):
    return templates.TemplateResponse(
        "cart.html",
        {"request": request}
    )

# 8. Админ панел
"""async def admin_page_endpoint(request: Request):
    # Проверка на аутентикацията
    auth_header = request.headers.get("Authorization")
    #if not auth_header or not auth_header.startswith("Bearer "):
    #    return RedirectResponse(url="/login")
    if not auth_header or not auth_header.startswith("Bearer "):
        return RedirectResponse(url="/login?next=/admin")
    
    token = auth_header.split(" ")[1]
    
    try:
        # Проверяваме токена
        token_data = decode_token(token)
        db = SessionLocal()
        
        try:
            # Взимаме потребителя
            from app.crud import get_user
            current_user = get_user(db, int(token_data.user_id))
            
            if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
                return RedirectResponse(url="/")
            
            # Данни за панела
            is_admin = current_user.role == UserRole.ADMIN
            orders = db.query(Order).order_by(Order.created_at.desc()).limit(10).all()
            books = db.query(Book).order_by(Book.created_at.desc()).limit(10).all()
            
            # Използваме Jinja2Templates
            return templates.TemplateResponse(
                "admin.html",
                {
                    "request": request,
                    "user": current_user,
                    "is_admin": is_admin,
                    "orders": orders,
                    "books": books
                }
            )
            
        finally:
            db.close()
            
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": 500, "detail": f"Error: {str(e)}"}
        )"""

async def admin_page_endpoint(request: Request):
    # ВРЕМЕННО РЕШЕНИЕ - автоматично зареждане на админ потребител -- докато не се настрои двуфакторната верификация
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.role == UserRole.ADMIN).first()
        
        # Данни за панела
        is_admin = True
        orders = db.query(Order).order_by(Order.created_at.desc()).limit(10).all()
        books = db.query(Book).order_by(Book.created_at.desc()).limit(10).all()
        
        return templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "user": admin_user,
                "is_admin": is_admin,
                "orders": orders,
                "books": books
            }
        )
    finally:
        db.close()

# Добавяме маршрутите
app.routes.append(Route("/", home_endpoint, methods=["GET"]))
app.routes.append(Route("/books/{book_id}", book_detail_page_endpoint, methods=["GET"]))
app.routes.append(Route("/search", search_page_endpoint, methods=["GET"]))
app.routes.append(Route("/login", login_page_endpoint, methods=["GET"]))
app.routes.append(Route("/register", register_page_endpoint, methods=["GET"]))
app.routes.append(Route("/forgotten-password", forgotten_password_page_endpoint, methods=["GET"]))
app.routes.append(Route("/order", order_page_endpoint, methods=["GET"]))
app.routes.append(Route("/admin", admin_page_endpoint, methods=["GET"]))

# Стартиране на приложението, ако файлът се изпълнява директно
if __name__ == "__main__":
	import uvicorn
	uvicorn.run(app, host="0.0.0.0", port=8000)
