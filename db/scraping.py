import logging
import aiohttp
import asyncio
from typing import Dict, Optional, Tuple, List
from bs4 import BeautifulSoup
import re
from urllib.parse import quote_plus
from datetime import datetime, timedelta

# Конфигуриране на логера
logger = logging.getLogger(__name__)

class GoodreadsClient:
    """
    Клиент за извличане на информация от Goodreads
    
    Използва асинхронни заявки за ефективно извличане на данни без
    блокиране на основния thread на приложението.
    """
    
    BASE_URL = "https://www.goodreads.com"
    SEARCH_URL = f"{BASE_URL}/search"
    BOOK_URL = f"{BASE_URL}/book/show"
    
    def __init__(self, max_retries: int = 3, timeout: int = 10):
        """
        Инициализира Goodreads клиент
        
        Args:
            max_retries: Максимален брой опити при неуспешна заявка
            timeout: Таймаут в секунди за HTTP заявки
        """
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        }
    
    async def _make_request(self, url: str) -> Optional[str]:
        """
        Изпълнява HTTP GET заявка с повторни опити при неуспех
        
        Args:
            url: URL адрес за заявката
            
        Returns:
            HTML съдържание при успех или None при неуспех
        """
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, 
                        headers=self.headers, 
                        timeout=self.timeout
                    ) as response:
                        if response.status == 200:
                            return await response.text()
                        
                        # При блокиране от Cloudflare или други форми на защита
                        if response.status == 403 or response.status == 429:
                            wait_time = 2 ** attempt  # Експоненциално увеличаване на изчакването
                            logger.warning(f"Rate limited (status {response.status}). Waiting {wait_time} seconds before retry.")
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"Request failed with status {response.status}: {url}")
                            return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Request error for {url}: {str(e)}")
                await asyncio.sleep(1)
        
        logger.error(f"All {self.max_retries} attempts failed for URL: {url}")
        return None
    
    async def search_book(self, title: str, author: str = None) -> Optional[str]:
        """
        Търси книга в Goodreads по заглавие и опционално автор
        
        Args:
            title: Заглавие на книгата
            author: Автор на книгата (опционално)
            
        Returns:
            Goodreads ID на първия намерен резултат или None
        """
        # Формираме заявката
        query = title
        if author:
            query = f"{title} {author}"
        
        search_url = f"{self.SEARCH_URL}?q={quote_plus(query)}"
        
        html_content = await self._make_request(search_url)
        if not html_content:
            return None
        
        # Парсваме HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Търсим първия резултат
        try:
            # Goodreads има различни HTML структури в зависимост от резултатите
            # Първи метод - търсене в таблица с резултати
            first_result = soup.select_one("table.tableList tr.bookalike")
            if first_result:
                book_url = first_result.select_one("a.bookTitle")["href"]
                book_id = re.search(r"/book/show/(\d+)", book_url)
                if book_id:
                    return book_id.group(1)
            
            # Втори метод - търсене в списък с резултати
            first_result = soup.select_one("div.elementList")
            if first_result:
                book_url = first_result.select_one("a.bookTitle")["href"]
                book_id = re.search(r"/book/show/(\d+)", book_url)
                if book_id:
                    return book_id.group(1)
            
            # Трети метод - директен редирект към книгата
            canonical_link = soup.select_one("link[rel='canonical']")
            if canonical_link and "book/show" in canonical_link["href"]:
                book_id = re.search(r"/book/show/(\d+)", canonical_link["href"])
                if book_id:
                    return book_id.group(1)
            
            logger.warning(f"No book found for query: {query}")
            return None
        except Exception as e:
            logger.error(f"Error parsing search results for {query}: {str(e)}")
            return None
    
    async def get_book_details(self, book_id: str) -> Optional[Dict]:
        """
        Извлича детайли за книга от Goodreads
        
        Args:
            book_id: Goodreads ID на книгата
            
        Returns:
            Речник с детайли за книгата или None при грешка
        """
        book_url = f"{self.BOOK_URL}/{book_id}"
        
        html_content = await self._make_request(book_url)
        if not html_content:
            return None
        
        # Парсваме HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        try:
            # Извличаме данни
            details = {}
            
            # Заглавие
            title_elem = soup.select_one("h1#bookTitle")
            if title_elem:
                details["title"] = title_elem.text.strip()
            
            # Автор
            author_elem = soup.select_one("a.authorName span")
            if author_elem:
                details["author"] = author_elem.text.strip()
            
            # Рейтинг
            rating_elem = soup.select_one("div.ratingValue span")
            if rating_elem:
                try:
                    details["rating"] = float(rating_elem.text.strip())
                except (ValueError, TypeError):
                    details["rating"] = None
            
            # Брой рейтинги
            ratings_count_elem = soup.select_one("meta[itemprop='ratingCount']")
            if ratings_count_elem and ratings_count_elem.get("content"):
                try:
                    details["ratings_count"] = int(ratings_count_elem["content"])
                except (ValueError, TypeError):
                    details["ratings_count"] = 0
            
            # Описание
            description_elem = soup.select_one("div#description span")
            if description_elem:
                details["description"] = description_elem.text.strip()
            
            # Допълнителни детайли
            details_elem = soup.select("div.row")
            for row in details_elem:
                label_elem = row.select_one("div.infoBoxRowTitle")
                value_elem = row.select_one("div.infoBoxRowItem")
                
                if label_elem and value_elem:
                    label = label_elem.text.strip().lower().replace(" ", "_").replace(":", "")
                    value = value_elem.text.strip()
                    details[label] = value
            
            return details
        except Exception as e:
            logger.error(f"Error parsing book details for ID {book_id}: {str(e)}")
            return None
    
    async def get_book_rating(self, book_id: str) -> Optional[float]:
        """
        Извлича само рейтинга на книга
        
        Args:
            book_id: Goodreads ID на книгата
            
        Returns:
            Рейтинг като float или None при грешка
        """
        book_url = f"{self.BOOK_URL}/{book_id}"
        
        html_content = await self._make_request(book_url)
        if not html_content:
            return None
        
        # Парсваме HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        try:
            # Рейтинг
            rating_elem = soup.select_one("div.ratingValue span")
            if rating_elem:
                try:
                    return float(rating_elem.text.strip())
                except (ValueError, TypeError):
                    return None
            
            return None
        except Exception as e:
            logger.error(f"Error parsing book rating for ID {book_id}: {str(e)}")
            return None
    
    async def get_book_reviews(self, book_id: str, limit: int = 5) -> List[Dict]:
        """
        Извлича отзиви за книга
        
        Args:
            book_id: Goodreads ID на книгата
            limit: Максимален брой отзиви за извличане
            
        Returns:
            Списък с отзиви като речници
        """
        reviews_url = f"{self.BOOK_URL}/{book_id}/reviews"
        
        html_content = await self._make_request(reviews_url)
        if not html_content:
            return []
        
        # Парсваме HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        reviews = []
        try:
            review_elems = soup.select("div.review")
            
            for review_elem in review_elems[:limit]:
                review = {}
                
                # Потребител
                user_elem = review_elem.select_one("a.user")
                if user_elem:
                    review["user"] = user_elem.text.strip()
                
                # Рейтинг
                rating_elem = review_elem.select_one("span.staticStars")
                if rating_elem:
                    rating_text = rating_elem.get("title", "")
                    rating_match = re.search(r"(\d+)", rating_text)
                    if rating_match:
                        review["rating"] = int(rating_match.group(1))
                
                # Дата
                date_elem = review_elem.select_one("a.reviewDate")
                if date_elem:
                    review["date"] = date_elem.text.strip()
                
                # Текст
                text_elem = review_elem.select_one("div.reviewText span")
                if text_elem:
                    review["text"] = text_elem.text.strip()
                
                reviews.append(review)
            
            return reviews
        except Exception as e:
            logger.error(f"Error parsing book reviews for ID {book_id}: {str(e)}")
            return []

# Функции за обновяване на книги в базата данни

async def update_book_from_goodreads(db, book_id: int) -> bool:
    """
    Обновява информацията за книга от Goodreads
    
    Args:
        db: Сесия към базата данни
        book_id: ID на книгата в нашата система
        
    Returns:
        True при успешно обновяване, False при грешка
    """
    from app.crud import get_book, update_book  # Избягваме цикличен импорт
    
    # Взимаме книгата от базата
    book = get_book(db, book_id)
    if not book:
        logger.error(f"Book with ID {book_id} not found")
        return False
    
    # Проверяваме дали имаме Goodreads ID или трябва да търсим
    client = GoodreadsClient()
    goodreads_id = book.goodreads_id
    
    if not goodreads_id:
        # Търсим по оригинално заглавие
        search_title = book.original_title if book.original_title else book.title
        goodreads_id = await client.search_book(search_title)
        
        if not goodreads_id:
            logger.warning(f"Could not find book on Goodreads: {search_title}")
            return False
        
        # Записваме Goodreads ID
        update_data = {"goodreads_id": goodreads_id}
        book = update_book(db, book_id, update_data)
    
    # Извличаме рейтинга
    rating = await client.get_book_rating(goodreads_id)
    
    if rating:
        update_data = {
            "goodreads_rating": rating,
            "goodreads_rating_updated": datetime.utcnow()
        }
        book = update_book(db, book_id, update_data)
        logger.info(f"Updated rating for book {book.title} (ID: {book_id}): {rating}")
        return True
    
    logger.warning(f"Could not fetch rating for book {book.title} (ID: {book_id})")
    return False

async def update_books_ratings(db) -> Tuple[int, int]:
    """
    Обновява рейтинги за всички книги, които се нуждаят от обновяване
    
    Args:
        db: Сесия към базата данни
        
    Returns:
        Tuple със (брой успешни обновявания, общ брой книги за обновяване)
    """
    from app.crud import get_books  # Избягваме цикличен импорт
    from app.db.models import Book
    from sqlalchemy import or_
    
    # Взимаме книги, които се нуждаят от обновяване:
    # - Книги без рейтинг или без дата на последно обновяване
    # - Книги, чийто рейтинг не е обновяван в последните 24 часа
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    
    books_to_update = db.query(Book).filter(
        Book.goodreads_id.isnot(None),
        or_(
            Book.goodreads_rating.is_(None),
            Book.goodreads_rating_updated.is_(None),
            Book.goodreads_rating_updated < one_day_ago
        )
    ).all()
    
    total_books = len(books_to_update)
    success_count = 0
    
    for book in books_to_update:
        success = await update_book_from_goodreads(db, book.id)
        if success:
            success_count += 1
        
        # Малка пауза между заявките, за да избегнем rate limiting
        await asyncio.sleep(1)
    
    return success_count, total_books

# Планировчик за периодично обновяване на рейтинги
class GoodreadsUpdater:
    """
    Клас за периодично обновяване на рейтинги от Goodreads
    """
    
    def __init__(self, db_function, interval_hours: int = 24):
        """
        Инициализира планировчика
        
        Args:
            db_function: Функция, която предоставя DB сесия
            interval_hours: Интервал в часове между обновяванията
        """
        self.db_function = db_function
        self.interval_hours = interval_hours
        self.is_running = False
        self.task = None
    
    async def _update_loop(self):
        """
        Основен цикъл за периодично обновяване
        Изпълнява се в безкраен цикъл, докато self.is_running е True
        """
        while self.is_running:
            try:
                # Получаваме DB сесия
                db = self.db_function()
                
                # Обновяваме книгите
                success_count, total_count = await update_books_ratings(db)
                
                logger.info(f"Updated {success_count}/{total_count} books from Goodreads")
                
                # Затваряме сесията
                db.close()
                
                # Изчакваме до следващото обновяване
                await asyncio.sleep(self.interval_hours * 3600)
            except Exception as e:
                logger.error(f"Error in Goodreads update loop: {str(e)}")
                # При грешка изчакваме по-кратко време и опитваме отново
                await asyncio.sleep(300)  # 5 минути
    
    def start(self):
        """
        Стартира периодичното обновяване
        """
        if self.is_running:
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._update_loop())
        logger.info(f"Started Goodreads updater with interval {self.interval_hours} hours")
    
    def stop(self):
        """
        Спира периодичното обновяване
        """
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
        
        logger.info("Stopped Goodreads updater")


# Функция за ръчно обновяване на конкретна книга
async def manual_update_book(db, book_id: int) -> dict:
    """
    Ръчно обновяване на информация за книга от Goodreads
    
    Args:
        db: Сесия към базата данни
        book_id: ID на книгата в нашата система
        
    Returns:
        Речник с резултата от обновяването
    """
    from app.crud import get_book  # Избягваме цикличен импорт
    
    # Проверяваме дали книгата съществува
    book = get_book(db, book_id)
    if not book:
        return {"success": False, "message": "Book not found"}
    
    # Обновяваме книгата
    success = await update_book_from_goodreads(db, book_id)
    
    if success:
        # Взимаме обновената книга
        updated_book = get_book(db, book_id)
        return {
            "success": True,
            "message": "Book updated successfully",
            "rating": updated_book.goodreads_rating,
            "updated_at": updated_book.goodreads_rating_updated
        }
    else:
        return {
            "success": False,
            "message": "Failed to update book from Goodreads"
        }


# Функция за извличане на допълнителна информация за книга
async def fetch_book_details(title: str, author: str = None) -> dict:
    """
    Търси и извлича подробна информация за книга от Goodreads
    
    Args:
        title: Заглавие на книгата
        author: Автор на книгата (опционално)
        
    Returns:
        Речник с информация за книгата или празен речник при грешка
    """
    client = GoodreadsClient()
    
    # Търсим книгата
    goodreads_id = await client.search_book(title, author)
    if not goodreads_id:
        return {}
    
    # Извличаме детайли
    details = await client.get_book_details(goodreads_id)
    if not details:
        return {"goodreads_id": goodreads_id}  # Връщаме поне ID-то
    
    # Форматираме данните в по-подходящ формат
    result = {
        "goodreads_id": goodreads_id,
        "title": details.get("title", ""),
        "author": details.get("author", ""),
        "rating": details.get("rating"),
        "ratings_count": details.get("ratings_count", 0),
        "description": details.get("description", "")
    }
    
    # Добавяме допълнителна информация, ако е налична
    for key in ["publisher", "publication_date", "language", "isbn", "pages"]:
        if key in details:
            result[key] = details[key]
    
    return result


# Функция за извличане на отзиви
async def fetch_book_reviews(book_id: str, limit: int = 5) -> list:
    """
    Извлича отзиви за книга от Goodreads
    
    Args:
        book_id: Goodreads ID на книгата
        limit: Максимален брой отзиви
        
    Returns:
        Списък с отзиви
    """
    client = GoodreadsClient()
    return await client.get_book_reviews(book_id, limit)


# Помощна функция за дебъгване
async def debug_goodreads_search(title: str, author: str = None) -> dict:
    """
    Функция за дебъгване на търсенето в Goodreads
    
    Args:
        title: Заглавие на книгата
        author: Автор на книгата (опционално)
        
    Returns:
        Речник с информация за търсенето
    """
    client = GoodreadsClient()
    
    start_time = datetime.utcnow()
    
    goodreads_id = await client.search_book(title, author)
    
    search_time = datetime.utcnow() - start_time
    
    result = {
        "query": {"title": title, "author": author},
        "goodreads_id": goodreads_id,
        "search_time_ms": search_time.total_seconds() * 1000
    }
    
    if goodreads_id:
        detail_start_time = datetime.utcnow()
        rating = await client.get_book_rating(goodreads_id)
        detail_time = datetime.utcnow() - detail_start_time
        
        result["rating"] = rating
        result["detail_time_ms"] = detail_time.total_seconds() * 1000
    
    return result


# Функция за инициализация
def init_goodreads_updater(db_function):
    """
    Инициализира и връща GoodreadsUpdater
    
    Args:
        db_function: Функция, която връща DB сесия
        
    Returns:
        GoodreadsUpdater обект
    """
    updater = GoodreadsUpdater(db_function)
    return updater
