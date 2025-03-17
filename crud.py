from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, desc
from datetime import datetime, timedelta
import typing as t
from fastapi import HTTPException, status

from app.db.models import (
    User, Book, Category, Order, OrderItem, Promotion, Review, 
    TempUser, UserRole, OrderStatus
)
from app.db.security import get_password_hash, verify_password

# ---------- User CRUD ----------

def get_user(db: Session, user_id: int) -> t.Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> t.Optional[User]:
    return db.query(User).filter(User.email == email).first()

def get_user_by_username(db: Session, username: str) -> t.Optional[User]:
    return db.query(User).filter(User.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 100) -> t.List[User]:
    return db.query(User).offset(skip).limit(limit).all()

def create_user(db: Session, email: str, username: str, password: str, phone: str = None, full_name: str = None) -> User:
    hashed_password = get_password_hash(password)
    db_user = User(
        email=email,
        username=username,
        hashed_password=hashed_password,
        phone=phone,
        full_name=full_name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, update_data: dict) -> User:
    db_user = get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    for key, value in update_data.items():
        if key == "password":
            setattr(db_user, "hashed_password", get_password_hash(value))
        else:
            setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int) -> bool:
    db_user = get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return True

def update_user_role(db: Session, user_id: int, new_role: UserRole) -> User:
    db_user = get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.role = new_role
    db.commit()
    db.refresh(db_user)
    return db_user

def check_vip_eligibility(db: Session, user_id: int) -> bool:
    db_user = get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if db_user.total_spent >= 600.0 and db_user.role == UserRole.USER:
        db_user.role = UserRole.VIP
        db.commit()
        db.refresh(db_user)
        return True
    
    return False


# ---------- Temp User CRUD ----------

def create_temp_user(db: Session, email: str, phone: str, full_name: str = None) -> TempUser:
    db_temp_user = TempUser(
        email=email,
        phone=phone,
        full_name=full_name
    )
    db.add(db_temp_user)
    db.commit()
    db.refresh(db_temp_user)
    return db_temp_user

def get_temp_user(db: Session, temp_user_id: int) -> t.Optional[TempUser]:
    return db.query(TempUser).filter(TempUser.id == temp_user_id).first()

def get_temp_user_by_phone(db: Session, phone: str) -> t.Optional[TempUser]:
    return db.query(TempUser).filter(TempUser.phone == phone).first()

def cleanup_temp_users(db: Session, days: int = 3) -> int:
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    temp_users = db.query(TempUser).filter(TempUser.created_at < cutoff_date).all()
    
    count = len(temp_users)
    for temp_user in temp_users:
        db.delete(temp_user)
    
    db.commit()
    return count


# ---------- Book CRUD ----------

def get_book(db: Session, book_id: int) -> t.Optional[Book]:
    return db.query(Book).filter(Book.id == book_id).first()

def get_book_by_isbn(db: Session, isbn: str) -> t.Optional[Book]:
    return db.query(Book).filter(Book.isbn == isbn).first()

def get_books(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    search: str = None,
    category_id: int = None,
    min_price=None, max_price=None,
    in_stock: bool = None,
    sort_by="title", sort_desc=False
) -> t.List[Book]:
    query = db.query(Book)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Book.title.ilike(search_term),
                Book.original_title.ilike(search_term),
                Book.publisher.ilike(search_term),
                Book.isbn.ilike(search_term)
            )
        )
    
    if category_id:
        query = query.join(Book.categories).filter(Category.id == category_id)
    
    if min_price is not None:
        query = query.filter(Book.price >= min_price)
    
    if max_price is not None:
        query = query.filter(Book.price <= max_price)
    
    if in_stock is not None:
        if in_stock:
            query = query.filter(Book.stock_count > 0)
        else:
            query = query.filter(Book.stock_count == 0)
    
    # Apply sorting
    if sort_by == "price":
        order_column = Book.price
    elif sort_by == "created_at":
        order_column = Book.created_at
    elif sort_by == "goodreads_rating":
        order_column = Book.goodreads_rating
    else:  # Default to title
        order_column = Book.title
    
    if sort_desc:
        query = query.order_by(desc(order_column))
    else:
        query = query.order_by(order_column)
    
    # Apply pagination
    if limit:
        query = query.offset(skip).limit(limit)
    
    return query.all()

def create_book(db: Session, book_data: dict) -> Book:
    db_book = Book(**book_data)
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book

def update_book(db: Session, book_id: int, update_data: dict) -> Book:
    db_book = get_book(db, book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Обновляем атрибуты книги
    for key, value in update_data.items():
        if key != "categories":  # Категории обрабатываются отдельно
            setattr(db_book, key, value)
    
    # Обновляем связи с категориями, если они указаны
    if "categories" in update_data and update_data["categories"]:
        category_ids = update_data["categories"]
        db_categories = db.query(Category).filter(Category.id.in_(category_ids)).all()
        db_book.categories = db_categories
    
    db.commit()
    db.refresh(db_book)
    return db_book

def delete_book(db: Session, book_id: int) -> bool:
    db_book = get_book(db, book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    db.delete(db_book)
    db.commit()
    return True

def update_book_stock(db: Session, book_id: int, quantity_change: int) -> Book:
    db_book = get_book(db, book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    new_stock = db_book.stock_count + quantity_change
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Not enough books in stock")
    
    db_book.stock_count = new_stock
    db.commit()
    db.refresh(db_book)
    return db_book


# ---------- Category CRUD ----------

def get_category(db: Session, category_id: int) -> t.Optional[Category]:
    return db.query(Category).filter(Category.id == category_id).first()

def get_category_by_name(db: Session, name: str) -> t.Optional[Category]:
    return db.query(Category).filter(Category.name == name).first()

def get_categories(db: Session, skip: int = 0, limit: int = 100) -> t.List[Category]:
    return db.query(Category).offset(skip).limit(limit).all()

def create_category(db: Session, name: str, description: str = None) -> Category:
    db_category = Category(name=name, description=description)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def update_category(db: Session, category_id: int, update_data: dict) -> Category:
    db_category = get_category(db, category_id)
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    for key, value in update_data.items():
        setattr(db_category, key, value)
    
    db.commit()
    db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: int) -> bool:
    db_category = get_category(db, category_id)
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    db.delete(db_category)
    db.commit()
    return True

def add_subcategory(db: Session, parent_id: int, child_id: int) -> Category:
    parent = get_category(db, parent_id)
    child = get_category(db, child_id)
    
    if not parent or not child:
        raise HTTPException(status_code=404, detail="Category not found")
    
    parent.subcategories.append(child)
    db.commit()
    db.refresh(parent)
    return parent


# ---------- Order CRUD ----------

def get_order(db: Session, order_id: int) -> t.Optional[Order]:
    return db.query(Order).filter(Order.id == order_id).first()

def get_user_orders(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> t.List[Order]:
    return db.query(Order).filter(Order.user_id == user_id).offset(skip).limit(limit).all()

def get_temp_user_orders(db: Session, temp_user_id: int, skip: int = 0, limit: int = 100) -> t.List[Order]:
    return db.query(Order).filter(Order.temp_user_id == temp_user_id).offset(skip).limit(limit).all()

def create_order(
    db: Session, 
    user_id: int = None, 
    temp_user_id: int = None, 
    items: t.List[dict] = None,
    shipping_address: dict = None,
    phone: str = None
) -> Order:
    if not items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")
    
    if not user_id and not temp_user_id:
        raise HTTPException(status_code=400, detail="Order must be associated with a user or temp user")
    
    # Создаём заказ
    total_price = 0.0
    db_order = Order(
        user_id=user_id,
        temp_user_id=temp_user_id,
        total_price=total_price,  # Пока 0, обновим после создания OrderItem
        shipping_address=shipping_address,
        phone=phone
    )
    db.add(db_order)
    db.flush()  # Чтобы получить ID заказа
    
    # Создаём элементы заказа
    for item in items:
        book_id = item["book_id"]
        quantity = item["quantity"]
        
        # Получаем информацию о книге
        db_book = get_book(db, book_id)
        if not db_book:
            db.rollback()
            raise HTTPException(status_code=404, detail=f"Book with id {book_id} not found")
        
        # Проверяем наличие на складе
        if db_book.stock_count < quantity:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Not enough copies of book '{db_book.title}' in stock")
        
        # Уменьшаем количество на складе
        db_book.stock_count -= quantity
        
        # Определяем цену и скидку
        price_per_item = db_book.price
        discount = 0.0
        
        # Проверяем активные акции
        active_promotion = (
            db.query(Promotion)
            .filter(
                Promotion.book_id == book_id,
                Promotion.start_date <= datetime.utcnow(),
                Promotion.end_date >= datetime.utcnow()
            )
            .order_by(Promotion.discount_percentage.desc())  # Берём наибольшую скидку
            .first()
        )
        
        if active_promotion:
            discount = active_promotion.discount_percentage
        
        # Если пользователь VIP, добавляем дополнительную скидку в 10%
        if user_id:
            user = get_user(db, user_id)
            if user and user.role == UserRole.VIP:
                # Если уже есть скидка, берём большую
                discount = max(discount, 10.0)
        
        # Создаём элемент заказа
        db_order_item = OrderItem(
            order_id=db_order.id,
            book_id=book_id,
            quantity=quantity,
            price_per_item=price_per_item,
            discount=discount
        )
        db.add(db_order_item)
        
        # Добавляем к общей стоимости заказа
        item_total = quantity * price_per_item * (1 - discount / 100)
        total_price += item_total
    
    # Обновляем общую стоимость заказа
    db_order.total_price = total_price
    
    # Обновляем total_spent для зарегистрированного пользователя
    if user_id:
        user = get_user(db, user_id)
        if user:
            user.total_spent += total_price
            # Проверяем, не стал ли пользователь VIP
            check_vip_eligibility(db, user_id)
    
    db.commit()
    db.refresh(db_order)
    return db_order

def update_order_status(db: Session, order_id: int, new_status: OrderStatus) -> Order:
    db_order = get_order(db, order_id)
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    db_order.status = new_status
    db.commit()
    db.refresh(db_order)
    return db_order

def cancel_order(db: Session, order_id: int) -> Order:
    db_order = get_order(db, order_id)
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if db_order.status == OrderStatus.SHIPPED or db_order.status == OrderStatus.DELIVERED:
        raise HTTPException(status_code=400, detail="Cannot cancel an order that has been shipped or delivered")
    
    # Возвращаем книги на склад
    for item in db_order.items:
        update_book_stock(db, item.book_id, item.quantity)
    
    # Уменьшаем total_spent для пользователя
    if db_order.user_id:
        user = get_user(db, db_order.user_id)
        if user:
            user.total_spent -= db_order.total_price
            # Возможно, пользователь потеряет статус VIP, но мы оставим это на усмотрение администратора
    
    db_order.status = OrderStatus.CANCELLED
    db.commit()
    db.refresh(db_order)
    return db_order


# ---------- Promotion CRUD ----------

def get_promotion(db: Session, promotion_id: int) -> t.Optional[Promotion]:
    return db.query(Promotion).filter(Promotion.id == promotion_id).first()

def get_active_promotions(db: Session, skip: int = 0, limit: int = 100) -> t.List[Promotion]:
    return (
        db.query(Promotion)
        .filter(
            Promotion.start_date <= datetime.utcnow(),
            Promotion.end_date >= datetime.utcnow()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_book_promotions(db: Session, book_id: int) -> t.List[Promotion]:
    return (
        db.query(Promotion)
        .filter(Promotion.book_id == book_id)
        .order_by(Promotion.start_date.desc())
        .all()
    )

def create_promotion(
    db: Session,
    book_id: int,
    discount_percentage: float,
    start_date: datetime,
    end_date: datetime,
    description: str = None,
    created_by: int = None
) -> Promotion:
    # Проверяем существование книги
    book = get_book(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Проверяем корректность дат
    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")
    
    # Проверяем корректность скидки
    if discount_percentage <= 0 or discount_percentage >= 100:
        raise HTTPException(status_code=400, detail="Discount percentage must be between 0 and 100")
    
    db_promotion = Promotion(
        book_id=book_id,
        discount_percentage=discount_percentage,
        start_date=start_date,
        end_date=end_date,
        description=description,
        created_by=created_by
    )
    db.add(db_promotion)
    db.commit()
    db.refresh(db_promotion)
    return db_promotion

def update_promotion(db: Session, promotion_id: int, update_data: dict) -> Promotion:
    db_promotion = get_promotion(db, promotion_id)
    if not db_promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    
    for key, value in update_data.items():
        setattr(db_promotion, key, value)
    
    db.commit()
    db.refresh(db_promotion)
    return db_promotion

def delete_promotion(db: Session, promotion_id: int) -> bool:
    db_promotion = get_promotion(db, promotion_id)
    if not db_promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")
    
    db.delete(db_promotion)
    db.commit()
    return True


# ---------- Review CRUD ----------

def get_review(db: Session, review_id: int) -> t.Optional[Review]:
    return db.query(Review).filter(Review.id == review_id).first()

def get_book_reviews(db: Session, book_id: int, skip: int = 0, limit: int = 100) -> t.List[Review]:
    return db.query(Review).filter(Review.book_id == book_id).offset(skip).limit(limit).all()

def get_user_reviews(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> t.List[Review]:
    return db.query(Review).filter(Review.user_id == user_id).offset(skip).limit(limit).all()

# Продължение на функцията create_review от предишния файл
def create_review(
    db: Session,
    user_id: int,
    book_id: int,
    rating: int,
    comment: str = None
) -> Review:
    # Проверяваме съществуването на книгата и потребителя
    book = get_book(db, book_id)
    user = get_user(db, user_id)
    
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Проверяваме, не е ли оставял потребителят наскоро отзив за тази книга
    latest_review = (
        db.query(Review)
        .filter(
            Review.user_id == user_id,
            Review.book_id == book_id
        )
        .order_by(Review.created_at.desc())
        .first()
    )
    
    if latest_review and (datetime.utcnow() - latest_review.created_at).days < 21:
        days_left = 21 - (datetime.utcnow() - latest_review.created_at).days
        raise HTTPException(
            status_code=400,
            detail=f"You can leave a new review for this book in {days_left} days"
        )
    
    # Проверяваме коректността на рейтинга
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    db_review = Review(
        user_id=user_id,
        book_id=book_id,
        rating=rating,
        comment=comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

def update_review(db: Session, review_id: int, update_data: dict) -> Review:
    db_review = get_review(db, review_id)
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    for key, value in update_data.items():
        setattr(db_review, key, value)
    
    db.commit()
    db.refresh(db_review)
    return db_review

def delete_review(db: Session, review_id: int) -> bool:
    db_review = get_review(db, review_id)
    if not db_review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    db.delete(db_review)
    db.commit()
    return True

# Функция за обновяване на рейтинга от Goodreads
def update_goodreads_rating(db: Session, book_id: int, rating: float) -> Book:
    db_book = get_book(db, book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    db_book.goodreads_rating = rating
    db_book.goodreads_rating_updated = datetime.utcnow()
    db.commit()
    db.refresh(db_book)
    return db_book

# Функция за проверка дали рейтингът от Goodreads трябва да бъде обновен
def should_update_goodreads_rating(db_book: Book) -> bool:
    if not db_book.goodreads_rating_updated:
        return True
    
    # Обновяваме рейтинга всеки 24 часа
    return (datetime.utcnow() - db_book.goodreads_rating_updated).days >= 1

# ---------- Статистически функции ----------

def get_bestsellers(db: Session, limit: int = 10) -> t.List[Book]:
    """Връща най-продаваните книги, базирани на брой продажби."""
    bestsellers = (
        db.query(Book, func.sum(OrderItem.quantity).label('total_sold'))
        .join(OrderItem)
        .join(Order)
        .filter(Order.status != OrderStatus.CANCELLED)
        .group_by(Book.id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )
    
    return [book for book, _ in bestsellers]

def get_top_rated_books(db: Session, limit: int = 10) -> t.List[Book]:
    """Връща най-високо оценените книги, базирани на рейтинги от потребители."""
    top_rated = (
        db.query(Book, func.avg(Review.rating).label('avg_rating'))
        .join(Review)
        .group_by(Book.id)
        .having(func.count(Review.id) >= 3)  # Книги с поне 3 отзива
        .order_by(func.avg(Review.rating).desc())
        .limit(limit)
        .all()
    )
    
    return [book for book, _ in top_rated]

def get_revenue_by_period(db: Session, start_date: datetime, end_date: datetime) -> float:
    """Изчислява общите приходи за определен период от време."""
    revenue = (
        db.query(func.sum(Order.total_price))
        .filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date,
            Order.status != OrderStatus.CANCELLED
        )
        .scalar() or 0.0  # В случай че няма поръчки, връщаме 0
    )
    
    return revenue

def get_revenue_by_category(db: Session, start_date: datetime, end_date: datetime) -> t.List[t.Tuple[Category, float]]:
    """Изчислява приходите по категории за определен период от време."""
    revenues = (
        db.query(
            Category,
            func.sum(
                OrderItem.quantity * OrderItem.price_per_item * (1 - OrderItem.discount / 100)
            ).label('revenue')
        )
        .join(Category.books)
        .join(Book.order_items)
        .join(OrderItem.order)
        .filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date,
            Order.status != OrderStatus.CANCELLED
        )
        .group_by(Category.id)
        .order_by(func.sum(OrderItem.quantity * OrderItem.price_per_item).desc())
        .all()
    )
    
    return revenues

def get_user_purchase_history(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> t.List[Order]:
    """Връща историята на покупките на потребител."""
    return (
        db.query(Order)
        .filter(
            Order.user_id == user_id,
            Order.status != OrderStatus.CANCELLED
        )
        .order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def search_books_complex(
    db: Session,
    search_query: str = None,
    category_ids: t.List[int] = None,
    min_price: float = None,
    max_price: float = None,
    in_stock: bool = None,
    sort_by: str = "title",
    sort_desc: bool = False,
    skip: int = 0,
    limit: int = 100
) -> t.List[Book]:
    """
    Комплексно търсене на книги с множество филтри и сортиране.
    
    Args:
        search_query: Ключови думи за търсене в заглавие, автор, ISBN и др.
        category_ids: Списък с ID-та на категории за филтриране
        min_price: Минимална цена
        max_price: Максимална цена
        in_stock: Филтър за наличност
        sort_by: Поле за сортиране (title, price, etc.)
        sort_desc: Възходящо или низходящо сортиране
        skip: Офсет за пагинация
        limit: Лимит за брой резултати
    """
    query = db.query(Book)
    
    # Прилагаме филтрите
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            or_(
                Book.title.ilike(search_term),
                Book.original_title.ilike(search_term),
                Book.publisher.ilike(search_term),
                Book.isbn.ilike(search_term)
            )
        )
    
    if category_ids:
        # Използваме distinct() за да избегнем дублиране на резултати при множество категории
        query = query.join(Book.categories).filter(Category.id.in_(category_ids)).distinct()
    
    if min_price is not None:
        query = query.filter(Book.price >= min_price)
    
    if max_price is not None:
        query = query.filter(Book.price <= max_price)
    
    if in_stock is not None:
        if in_stock:
            query = query.filter(Book.stock_count > 0)
        else:
            query = query.filter(Book.stock_count == 0)
    
    # Прилагаме сортирането
    if sort_by:
        sort_column = getattr(Book, sort_by, Book.title)
        if sort_desc:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column)
    
    return query.offset(skip).limit(limit).all()

def get_book_with_promotions(db: Session, book_id: int) -> t.Tuple[Book, t.Optional[Promotion]]:
    """
    Връща книга заедно с активната промоция, ако има такава.
    Полезно за страницата на книгата, където показваме информация за книгата и промоция.
    """
    book = get_book(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Намираме активна промоция, ако има такава
    active_promotion = (
        db.query(Promotion)
        .filter(
            Promotion.book_id == book_id,
            Promotion.start_date <= datetime.utcnow(),
            Promotion.end_date >= datetime.utcnow()
        )
        .order_by(Promotion.discount_percentage.desc())
        .first()
    )
    
    return book, active_promotion
