from datetime import datetime, timedelta
from typing import List, Optional, Union, Dict, Any
import os
import secrets
import pyotp
import qrcode
import io
import base64
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.models import User, UserRole

# Конфигурация
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
# Използваме променлива от средата или генерираме случаен ключ
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
# Ключ за 2FA
TOTP_SECRET_KEY = os.getenv("TOTP_SECRET_KEY", "BOOKSHOPSECRETKEY123")

# Инстанция за хеширане на пароли
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 схема за извличане на токен от хедъри
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Клас за потребителски данни от токен
class TokenData:
    def __init__(self, user_id: str = None, username: str = None, role: str = None):
        self.user_id = user_id
        self.username = username
        self.role = role

# Функции за работа с пароли
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверява дали текстовата парола съвпада с хеширания вариант"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Хешира парола"""
    return pwd_context.hash(password)

# JWT функции
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Създава JWT access token
    
    Args:
        data: Данни за включване в токена
        expires_delta: Период на валидност (по подразбиране 30 минути)
        
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """
    Създава JWT refresh token с по-дълъг период на валидност
    
    Args:
        data: Данни за включване в токена
        
    Returns:
        JWT refresh token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> TokenData:
    """
    Декодира JWT token и извлича потребителските данни
    
    Args:
        token: JWT token за декодиране
        
    Returns:
        TokenData обект с потребителски данни
        
    Raises:
        HTTPException: Ако токенът е невалиден или е изтекъл
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")
        role = payload.get("role")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return TokenData(user_id=user_id, username=username, role=role)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# 2FA функции
def generate_totp_secret() -> str:
    """Генерира случаен secret key за TOTP"""
    return pyotp.random_base32()

def get_totp_uri(username: str, secret: str, issuer: str = "BookshopApp") -> str:
    """
    Генерира URI за TOTP QR код
    
    Args:
        username: Потребителско име
        secret: TOTP secret key
        issuer: Име на издателя на TOTP
        
    Returns:
        URI string за QR код
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name=issuer
    )

def generate_qr_code(totp_uri: str) -> str:
    """
    Генерира QR код като base64 string
    
    Args:
        totp_uri: TOTP URI
        
    Returns:
        Base64 encoded PNG image
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Конвертираме до base64 string
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def verify_totp(token: str, secret: str) -> bool:
    """
    Проверява TOTP token
    
    Args:
        token: 6-цифрен TOTP код
        secret: TOTP secret key
        
    Returns:
        Булева стойност дали кодът е валиден
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token)

# Получаване на текущ потребител
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = None) -> User:
    """
    Извлича текущия потребител от JWT token
    
    Args:
        token: JWT access token
        db: Сесия за база данни
        
    Returns:
        User обект
        
    Raises:
        HTTPException: Ако автентикацията е неуспешна
    """
    token_data = decode_token(token)
    
    # Ако нямаме DB сесия, вдигаме грешка вместо да връщаме token_data
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database session not available",
        )
    
    from app.crud import get_user  # Избягваме цикличен импорт
    
    user = get_user(db, int(token_data.user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

# RBAC - Проверка на ролите
def check_role(required_roles: List[UserRole]):
    """
    Dependency за проверка на потребителски роли
    
    Args:
        required_roles: Списък с необходими роли за достъп
    
    Returns:
        Dependency функция за FastAPI
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role} not authorized to access this resource"
            )
        return current_user  # Връща User обекта, без DB сесията
    return role_checker

# Helpers за често използвани роли
check_admin = check_role([UserRole.ADMIN])
check_moderator = check_role([UserRole.ADMIN, UserRole.MODERATOR])
check_vip = check_role([UserRole.ADMIN, UserRole.MODERATOR, UserRole.VIP])
check_authenticated = check_role([UserRole.ADMIN, UserRole.MODERATOR, UserRole.VIP, UserRole.USER])

# Rate limiting функционалност
class RateLimiter:
    """
    Проста имплементация на rate limiting с използване на in-memory dict.
    За production среда е по-добре да се използва Redis.
    """
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = {}  # {ip: [(timestamp, count), ...]}
    
    def is_allowed(self, ip: str) -> bool:
        """
        Проверява дали заявката е в рамките на лимита
        
        Args:
            ip: IP адрес на клиента
            
        Returns:
            Булева стойност дали заявката е разрешена
        """
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Премахване на стари записи
        if ip in self.requests:
            self.requests[ip] = [r for r in self.requests[ip] if r[0] > minute_ago]
        else:
            self.requests[ip] = []
        
        # Броене на заявки за последната минута
        count = sum(r[1] for r in self.requests[ip])
        
        if count >= self.requests_per_minute:
            return False
        
        # Добавяне на текущата заявка
        self.requests[ip].append((now, 1))
        return True

# Инстанция на rate limiter
rate_limiter = RateLimiter()

# Продължение на предходния файл security.py

# Rate limit middleware
async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware за ограничаване на заявките по IP адрес
    
    Args:
        request: FastAPI Request обект
        call_next: Следваща middleware функция
        
    Returns:
        Response обект
        
    Забележка: Този middleware се прилага на ниво приложение и 
    ограничава всички заявки, идващи от един и същ IP адрес.
    За по-сложни случаи може да се имплементира различен лимит за
    различните endpoint-и или по-сложна логика.
    """
    client_ip = request.client.host
    
    # Пропускаме static файлове
    if request.url.path.startswith("/static"):
        return await call_next(request)
    
    # Проверяваме дали заявката е в рамките на лимита
    if not rate_limiter.is_allowed(client_ip):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests"},
        )
    
    # Обработка на заявката
    return await call_next(request)

class SecurityUtils:
    """
    Помощен клас с методи за сигурност
    """
    
    @staticmethod
    def require_2fa_for_role(user: User) -> bool:
        """
        Проверява дали ролята на потребителя изисква 2FA
        
        Args:
            user: Потребителски обект
            
        Returns:
            Булева стойност дали се изисква 2FA
        """
        # return user.role in [UserRole.ADMIN, UserRole.MODERATOR]
        return False # временно, докато не се настрои двуфакторната верификация
    
    @staticmethod
    def setup_2fa(user: User, db: Session) -> dict:
        """
        Подготвя 2FA за потребител
        
        Args:
            user: Потребителски обект
            db: База данни сесия
            
        Returns:
            Речник със secret и QR код за настройка
        """
        # Генерираме secret
        secret = generate_totp_secret()
        
        # Създаваме URI
        totp_uri = get_totp_uri(user.username, secret)
        
        # Генерираме QR код
        qr_code = generate_qr_code(totp_uri)
        
        # Запазваме secret в базата данни
        user.two_factor_secret = secret
        db.commit()
        
        return {
            "secret": secret,
            "qr_code": qr_code
        }
    
    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
        """
        Автентикира потребител по парола
        
        Args:
            db: База данни сесия
            username: Потребителско име
            password: Парола
            
        Returns:
            User обект ако автентикацията е успешна, иначе None
        """
        from app.crud import get_user_by_username  # Избягваме цикличен импорт
        
        user = get_user_by_username(db, username)
        if not user:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        return user
    
    @staticmethod
    def generate_tokens(user: User) -> dict:
        """
        Генерира access и refresh токени за потребител
        
        Args:
            user: Потребителски обект
            
        Returns:
            Речник с токените
        """
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    @staticmethod
    def refresh_access_token(refresh_token: str) -> dict:
        """
        Обновява access token с refresh token
        
        Args:
            refresh_token: JWT refresh token
            
        Returns:
            Нов access token
            
        Raises:
            HTTPException: Ако refresh token е невалиден
        """
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Проверяваме дали е refresh token, а не access token
            if "exp" not in payload or datetime.fromtimestamp(payload["exp"]) < datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Създаваме нов token
            token_data = {
                "sub": payload.get("sub"),
                "username": payload.get("username"),
                "role": payload.get("role")
            }
            
            access_token = create_access_token(token_data)
            
            return {
                "access_token": access_token,
                "token_type": "bearer"
            }
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    @staticmethod
    def validate_password_strength(password: str) -> bool:
        """
        Проверява силата на паролата
        
        Args:
            password: Текстова парола
            
        Returns:
            True ако паролата отговаря на изискванията, иначе False
        """
        # Минимални изисквания за парола
        if len(password) < 8:
            return False
        
        # Проверка за поне една цифра
        if not any(char.isdigit() for char in password):
            return False
        
        # Проверка за поне една главна буква
        if not any(char.isupper() for char in password):
            return False
        
        # Проверка за поне една малка буква
        if not any(char.islower() for char in password):
            return False
        
        # Проверка за поне един специален символ
        if not any(char in "!@#$%^&*()-_=+[]{}|;:'\",.<>/?`~" for char in password):
            return False
        
        return True

# Функции за обработка на API заявки

async def authenticate_endpoint(
    username: str, 
    password: str, 
    db: Session,
    require_2fa: bool = False
) -> dict:
    """
    Обработва заявка за автентикация
    
    Args:
        username: Потребителско име
        password: Парола
        db: База данни сесия
        require_2fa: Дали се изисква 2FA
        
    Returns:
        Речник с резултат от автентикацията
        
    Raises:
        HTTPException: При неуспешна автентикация
    """
    user = SecurityUtils.authenticate_user(db, username, password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверка дали 2FA е задължително за тази роля
    requires_2fa = SecurityUtils.require_2fa_for_role(user)
    
    # Ако потребителят има активирано 2FA, изискваме токен
    if user.two_factor_enabled:
        if require_2fa:
            # Ще върнем само специален токен, който ще се използва за 2FA endpoint
            token_data = {
                "sub": str(user.id),
                "username": user.username,
                "pending_2fa": True
            }
            temporary_token = create_access_token(
                token_data, 
                expires_delta=timedelta(minutes=5)  # Кратък живот за 2FA токена
            )
            
            return {
                "detail": "2FA required",
                "temporary_token": temporary_token
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is required for this account"
            )
    
    # Ако ролята изисква 2FA, но потребителят не го е активирал
    if requires_2fa and not user.two_factor_enabled:
        # Подготвяме 2FA настройки
        twofa_setup = SecurityUtils.setup_2fa(user, db)
        
        # Връщаме временен токен и данни за 2FA настройка
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "setup_2fa": True
        }
        temporary_token = create_access_token(
            token_data, 
            expires_delta=timedelta(minutes=15)
        )
        
        return {
            "detail": "2FA setup required",
            "temporary_token": temporary_token,
            "2fa_setup": twofa_setup
        }
    
    # Нормална автентикация без 2FA
    return SecurityUtils.generate_tokens(user)

async def verify_2fa_endpoint(
    token: str, 
    totp_code: str, 
    db: Session
) -> dict:
    """
    Верифицира 2FA код
    
    Args:
        token: Временен токен от първата стъпка на автентикация
        totp_code: 6-цифрен TOTP код
        db: База данни сесия
        
    Returns:
        Токени за достъп при успешна верификация
        
    Raises:
        HTTPException: При неуспешна верификация
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if "pending_2fa" not in payload or not payload["pending_2fa"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        
        from app.crud import get_user  # Избягваме цикличен импорт
        
        user = get_user(db, int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Проверяваме TOTP кода
        if not verify_totp(totp_code, user.two_factor_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA code"
            )
        
        # Връщаме нормални токени за достъп
        return SecurityUtils.generate_tokens(user)
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def setup_2fa_endpoint(
    token: str, 
    totp_code: str, 
    db: Session
) -> dict:
    """
    Завършва настройката на 2FA
    
    Args:
        token: Временен токен от първата стъпка на автентикация
        totp_code: 6-цифрен TOTP код за проверка
        db: База данни сесия
        
    Returns:
        Токени за достъп при успешна настройка
        
    Raises:
        HTTPException: При неуспешна настройка
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if "setup_2fa" not in payload or not payload["setup_2fa"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        
        from app.crud import get_user  # Избягваме цикличен импорт
        
        user = get_user(db, int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Проверяваме TOTP кода
        if not verify_totp(totp_code, user.two_factor_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA code"
            )
        
        # Активираме 2FA
        user.two_factor_enabled = True
        db.commit()
        
        # Връщаме нормални токени за достъп
        return SecurityUtils.generate_tokens(user)
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
