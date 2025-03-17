import json
import redis
from typing import Optional, List, Any, Dict, Union
from datetime import timedelta
import logging
from fastapi import Depends

# Конфигуриране на логера
logger = logging.getLogger(__name__)

class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        Инициализира Redis кеш клиент
        
        Args:
            redis_url: Връзка към Redis сървъра
        """
        self.redis = redis.from_url(redis_url)
        # Проверяваме връзката при стартиране
        try:
            self.redis.ping()
            logger.info("Successfully connected to Redis")
        except redis.ConnectionError:
            logger.error("Could not connect to Redis")
            self.redis = None
    
    def get(self, key: str) -> Optional[Any]:
        """
        Извлича данни от кеша по ключ
        
        Args:
            key: Ключ за търсене в кеша
            
        Returns:
            Кешираната стойност или None, ако ключът не е намерен
        """
        if not self.redis:
            return None
        
        try:
            data = self.redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None
    
    def set(self, key: str, value: Any, expires: int = 3600) -> bool:
        """
        Записва данни в кеша
        
        Args:
            key: Ключ за записване
            value: Стойност за записване (ще бъде сериализирана до JSON)
            expires: Време за изтичане в секунди (по подразбиране 1 час)
            
        Returns:
            True ако операцията е успешна, иначе False
        """
        if not self.redis:
            return False
        
        try:
            serialized_value = json.dumps(value)
            self.redis.setex(key, expires, serialized_value)
            return True
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Изтрива запис от кеша
        
        Args:
            key: Ключ за изтриване
            
        Returns:
            True ако ключът е изтрит, иначе False
        """
        if not self.redis:
            return False
        
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Изтрива всички ключове, които съвпадат с даден шаблон
        
        Args:
            pattern: Шаблон за съвпадение (напр. "book:*")
            
        Returns:
            Брой изтрити ключове
        """
        if not self.redis:
            return 0
            
        try:
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Error clearing pattern from cache: {e}")
            return 0
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Увеличава стойност на ключ с определена стойност
        Полезно за броене на посещения/импресии
        
        Args:
            key: Ключ за увеличаване
            amount: Стойност за добавяне
            
        Returns:
            Новата стойност след увеличаването или None при грешка
        """
        if not self.redis:
            return None
            
        try:
            return self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Error incrementing key: {e}")
            return None

# Функции за кеширане на конкретни сценарии в приложението

# Префикси за кеш ключове
BOOK_DETAIL_PREFIX = "book:detail:"
BOOK_SEARCH_PREFIX = "book:search:"
CATEGORY_PREFIX = "category:"
BESTSELLERS_KEY = "bestsellers"
TOP_RATED_KEY = "top_rated"

def get_book_cache_key(book_id: int) -> str:
    """Генерира кеш ключ за детайли на книга"""
    return f"{BOOK_DETAIL_PREFIX}{book_id}"

def get_book_search_cache_key(query: str, category_id: Optional[int] = None, in_stock: Optional[bool] = None) -> str:
    """
    Генерира кеш ключ за резултати от търсене
    Включва всички параметри на търсенето в ключа
    """
    key = f"{BOOK_SEARCH_PREFIX}{query}"
    if category_id is not None:
        key += f":cat{category_id}"
    if in_stock is not None:
        key += f":stock{int(in_stock)}"
    return key

def get_category_cache_key(category_id: Optional[int] = None) -> str:
    """Генерира кеш ключ за категории"""
    if category_id:
        return f"{CATEGORY_PREFIX}{category_id}"
    return f"{CATEGORY_PREFIX}all"

# Функции за инвалидиране на кеша при обновяване
def invalidate_book_cache(cache: RedisCache, book_id: int) -> None:
    """
    Инвалидира кеша за книга, когато книгата се промени
    
    Args:
        cache: Redis кеш клиент
        book_id: ID на книгата, която е обновена
    """
    # Изтриваме конкретната книга от кеша
    cache.delete(get_book_cache_key(book_id))
    
    # Изтриваме свързани резултати от търсенето
    # Използваме wildcard подход, тъй като не знаем в кои търсения участва книгата
    cache.clear_pattern(f"{BOOK_SEARCH_PREFIX}*")
    
    # Инвалидираме бестселъри и най-оценени книги
    cache.delete(BESTSELLERS_KEY)
    cache.delete(TOP_RATED_KEY)

def invalidate_category_cache(cache: RedisCache, category_id: int) -> None:
    """
    Инвалидира кеша за категория при промяна
    
    Args:
        cache: Redis кеш клиент
        category_id: ID на категорията, която е обновена
    """
    # Изтриваме конкретната категория
    cache.delete(get_category_cache_key(category_id))
    
    # Изтриваме целия списък категории
    cache.delete(get_category_cache_key())
    
    # Изтриваме свързани резултати от търсенето
    cache.clear_pattern(f"{BOOK_SEARCH_PREFIX}*:cat{category_id}*")

# Създаваме глобален RedisCache обект
redis_cache = RedisCache()

# Dependency за инжектиране в endpoints
def get_cache() -> RedisCache:
    return redis_cache
