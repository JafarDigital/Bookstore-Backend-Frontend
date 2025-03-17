// Глобални променливи
let currentUser = null;
let cart = [];

// Инициализация при зареждане на страницата
document.addEventListener('DOMContentLoaded', function() {
    // Зареждане на данни за потребителя
    loadUserData();
    
    // Зареждане на данни за кошницата
    loadCart();
    
    // Добавяне на обработчик за изход
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
});

// Функция за зареждане на данни за потребителя
function loadUserData() {
    // Проверка за наличие на токен
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        updateUIForGuest();
        return;
    }
    
    // Заявка към API за данни на потребителя
    fetch('/api/users/me', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
    .then(response => {
        console.log("API response status:", response.status);
        console.log("API response type:", response.headers.get('content-type'));
        
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            throw new Error(`Expected JSON response but got ${contentType}`);
        }
        
        return response.json();
    })
    .then(userData => {
        console.log("User data received:", userData);
        currentUser = userData;
        updateUIForUser(userData);
    })
    .catch(error => {
        console.error('Error loading user data:', error);
        // Logging the token for debugging (be careful with this in production)
        console.log("Token used:", token.substring(0, 10) + "...");
        
        // При грешка в автентикацията, изтриваме токените
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        updateUIForGuest();
    });
}

// Функция за обновяване на UI за гост
function updateUIForGuest() {
    const userInfo = document.getElementById('userInfo');
    if (userInfo) {
        userInfo.textContent = 'Гост';
    }
    
    // Скриваме елементите, които изискват автентикация
    document.querySelectorAll('.auth-required').forEach(elem => {
        elem.classList.add('d-none');
    });
    
    // Показваме елементите за гости
    document.querySelectorAll('.no-auth-required').forEach(elem => {
        elem.classList.remove('d-none');
    });
    
    // Скриваме админ елементите
    document.querySelectorAll('.admin-required').forEach(elem => {
        elem.classList.add('d-none');
    });
}

// Функция за обновяване на UI за автентикиран потребител
function updateUIForUser(userData) {
    const userInfo = document.getElementById('userInfo');
    if (userInfo) {
        userInfo.textContent = userData.username;
    }
    
    // Показваме елементите, които изискват автентикация
    document.querySelectorAll('.auth-required').forEach(elem => {
        elem.classList.remove('d-none');
    });
    
    // Скриваме елементите за гости
    document.querySelectorAll('.no-auth-required').forEach(elem => {
        elem.classList.add('d-none');
    });
    
    // Показваме админ елементите, ако потребителят е админ или модератор
    if (userData.role === 'admin' || userData.role === 'moderator') {
        document.querySelectorAll('.admin-required').forEach(elem => {
            elem.classList.remove('d-none');
        });
    } else {
        document.querySelectorAll('.admin-required').forEach(elem => {
            elem.classList.add('d-none');
        });
    }
}

// Функция за изход
function logout(event) {
    event.preventDefault();
    
    // Изтриваме токените
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    
    // Обновяваме UI
    currentUser = null;
    updateUIForGuest();
    
    // Пренасочваме към началната страница
    window.location.href = '/';
}

// Функции за работа с кошницата
function loadCart() {
    const savedCart = localStorage.getItem('cart');
    
    if (savedCart) {
        cart = JSON.parse(savedCart);
        updateCartBadge();
    }
}

function updateCartBadge() {
    const cartBadge = document.getElementById('cartBadge');
    if (cartBadge) {
        const totalItems = cart.reduce((total, item) => total + item.quantity, 0);
        cartBadge.textContent = totalItems;
    }
}

function addToCart(bookId, title, price, quantity = 1) {
    // Проверка дали книгата вече е в кошницата
    const existingItem = cart.find(item => item.bookId === bookId);
    
    if (existingItem) {
        existingItem.quantity += quantity;
    } else {
        cart.push({
            bookId,
            title,
            price,
            quantity
        });
    }
    
    // Запазваме кошницата в localStorage
    localStorage.setItem('cart', JSON.stringify(cart));
    
    // Обновяваме UI
    updateCartBadge();
    
    // Показваме съобщение
    showToast('Добавено в кошницата', `${title} добавена в кошницата.`, 'success');
}

function testAddToCart() {
    addToCart(1, 'Test Book', 19.99);
    console.log('Current cart:', cart);
}

function removeFromCart(bookId) {
    // Намираме индекса на елемента в кошницата
    const index = cart.findIndex(item => item.bookId === bookId);
    
    if (index !== -1) {
        // Запомняме заглавието за съобщението
        const title = cart[index].title;
        
        // Премахваме елемента
        cart.splice(index, 1);
        
        // Запазваме кошницата в localStorage
        localStorage.setItem('cart', JSON.stringify(cart));
        
        // Обновяваме UI
        updateCartBadge();
        
        // Ако сме на страницата на кошницата, обновяваме съдържанието
        if (window.location.pathname === '/cart') {
            renderCart();
        }
        
        // Показваме съобщение
        showToast('Премахнато от кошницата', `${title} премахната от кошницата.`, 'info');
    }
}

function updateCartItemQuantity(bookId, quantity) {
    // Намираме елемента в кошницата
    const item = cart.find(item => item.bookId === bookId);
    
    if (item) {
        item.quantity = quantity;
        
        // Ако количеството е 0, премахваме елемента
        if (quantity <= 0) {
            removeFromCart(bookId);
            return;
        }
        
        // Запазваме кошницата в localStorage
        localStorage.setItem('cart', JSON.stringify(cart));
        
        // Обновяваме UI
        updateCartBadge();
        
        // Ако сме на страницата на кошницата, обновяваме съдържанието
        if (window.location.pathname === '/cart') {
            renderCart();
        }
    }
}

function clearCart() {
    cart = [];
    localStorage.removeItem('cart');
    updateCartBadge();
    
    // Ако сме на страницата на кошницата, обновяваме съдържанието
    if (window.location.pathname === '/cart') {
        renderCart();
    }
    
    showToast('Кошницата е изчистена', 'Всички продукти са премахнати от кошницата.', 'info');
}

// Функция за показване на toast съобщения
function showToast(title, message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastTitle = document.getElementById('toastTitle');
    const toastMessage = document.getElementById('toastMessage');
    
    if (!toast || !toastTitle || !toastMessage) return;
    
    // Настройка на типа на съобщението
    toast.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-info');
    
    switch(type) {
        case 'success':
            toast.classList.add('bg-success', 'text-white');
            break;
        case 'error':
            toast.classList.add('bg-danger', 'text-white');
            break;
        case 'warning':
            toast.classList.add('bg-warning');
            break;
        default:
            toast.classList.add('bg-info', 'text-white');
    }
    
    // Задаване на съдържанието
    toastTitle.textContent = title;
    toastMessage.textContent = message;
    
    // Показване на съобщението
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}

// Функция за показване на модален диалог за потвърждение
function showConfirmDialog(title, message, onConfirm) {
    const confirmModal = document.getElementById('confirmModal');
    const confirmModalLabel = document.getElementById('confirmModalLabel');
    const confirmModalBody = document.getElementById('confirmModalBody');
    const confirmModalBtn = document.getElementById('confirmModalBtn');
    
    if (!confirmModal || !confirmModalLabel || !confirmModalBody || !confirmModalBtn) return;
    
    // Задаване на съдържанието
    confirmModalLabel.textContent = title;
    confirmModalBody.textContent = message;
    
    // Добавяне на обработчик за потвърждение
    confirmModalBtn.onclick = function() {
        onConfirm();
        bootstrap.Modal.getInstance(confirmModal).hide();
    };
    
    // Показване на диалога
    const bsModal = new bootstrap.Modal(confirmModal);
    bsModal.show();
}

// Функция за форматиране на цена
function formatPrice(price) {
    return price.toFixed(2) + ' лв.';
}

// Функция за форматиране на дата
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('bg-BG', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Функция за рендериране на рейтинг със звезди
function renderStars(rating) {
    const stars = [];
    
    // Добавяме пълни звезди
    for (let i = 1; i <= Math.floor(rating); i++) {
        stars.push('<i class="fas fa-star"></i>');
    }
    
    // Добавяме половин звезда, ако е необходимо
    if (rating % 1 >= 0.5) {
        stars.push('<i class="fas fa-star-half-alt"></i>');
    }
    
    // Добавяме празни звезди до 5
    const emptyStars = 5 - Math.ceil(rating);
    for (let i = 1; i <= emptyStars; i++) {
        stars.push('<i class="far fa-star"></i>');
    }
    
    return stars.join('');
}

// API функции с управление на токените
async function fetchWithToken(url, options = {}) {
    // Взимаме токена от localStorage
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        return fetch(url, options);
    }
    
    // Добавяме Authorization хедър
    const headers = options.headers || {};
    headers['Authorization'] = `Bearer ${token}`;
    
    // Изпълняваме заявката
    const response = await fetch(url, { ...options, headers });
    
    // Ако имаме грешка 401 (Unauthorized), опитваме да обновим токена
    if (response.status === 401) {
        const refreshed = await refreshToken();
        
        // Ако сме успели да обновим токена, повтаряме заявката
        if (refreshed) {
            // Взимаме новия токен
            const newToken = localStorage.getItem('access_token');
            headers['Authorization'] = `Bearer ${newToken}`;
            
            return fetch(url, { ...options, headers });
        }
        
        // Ако не сме успели да обновим токена, връщаме оригиналния отговор
        return response;
    }
    
    return response;
}

// Функция за обновяване на access token чрез refresh token
async function refreshToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    
    if (!refreshToken) {
        return false;
    }
    
    try {
        const response = await fetch('/api/token/refresh', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: `refresh_token=${encodeURIComponent(refreshToken)}`
        });
        
        if (!response.ok) {
            throw new Error('Failed to refresh token');
        }
        
        const data = await response.json();
        
        // Запазваме новия access token
        localStorage.setItem('access_token', data.access_token);
        
        return true;
    } catch (error) {
        console.error('Error refreshing token:', error);
        
        // Изтриваме токените при грешка
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        
        // Обновяваме UI за гост
        currentUser = null;
        updateUIForGuest();
        
        return false;
    }
}

// Функция за извличане на данни от форма
function getFormData(form) {
    const formData = new FormData(form);
    const data = {};
    
    for (let [key, value] of formData.entries()) {
        // Проверка за множествени стойности (напр. checkboxes)
        if (key.endsWith('[]')) {
            const realKey = key.slice(0, -2);
            if (!data[realKey]) {
                data[realKey] = [];
            }
            data[realKey].push(value);
        } else {
            data[key] = value;
        }
    }
    
    return data;
}

// Функция за генериране на шаблони с книги
function generateBookCard(book) {
    // Определяне дали книгата е в промоция
    let promotionHTML = '';
    let priceHTML = '';
    
    if (book.promotion) {
        const discountedPrice = book.price * (1 - book.promotion.discount_percentage / 100);
        
        promotionHTML = `
            <div class="position-absolute top-0 start-0 bg-warning text-dark p-2">
                <small>-${book.promotion.discount_percentage}%</small>
            </div>
        `;
        
        priceHTML = `
            <span class="text-decoration-line-through text-muted me-2">${formatPrice(book.price)}</span>
            <span class="text-danger fw-bold">${formatPrice(discountedPrice)}</span>
        `;
    } else {
        priceHTML = `<span class="text-primary fw-bold">${formatPrice(book.price)}</span>`;
    }
    
    // Определяне на наличност
    let stockHTML = '';
    if (!book.in_stock) {
        stockHTML = `
            <div class="position-absolute top-0 end-0 bg-danger text-white p-2">
                <small>Изчерпана</small>
            </div>
        `;
    }
    
    // Добавяме рейтинг, ако има такъв
    let ratingHTML = '';
    if (book.goodreads_rating) {
        ratingHTML = `
            <div class="rating mb-2">
                ${renderStars(book.goodreads_rating)}
                <small class="text-muted ms-1">${book.goodreads_rating.toFixed(1)}</small>
            </div>
        `;
    }
    
    // Създаваме HTML за картата
    return `
        <div class="col-md-4 col-lg-3 mb-4">
            <div class="card h-100">
                <div class="position-relative">
                    <img src="/static/book-placeholder.jpg" class="card-img-top" alt="${book.title}">
                    ${promotionHTML}
                    ${stockHTML}
                </div>
                <div class="card-body d-flex flex-column">
                    <h5 class="card-title">${book.title}</h5>
                    <p class="card-text text-muted">${book.publisher || ''}</p>
                    ${ratingHTML}
                    <div class="d-flex justify-content-between align-items-center mt-auto">
                        ${priceHTML}
                        <a href="/books/${book.id}" class="btn btn-sm btn-outline-primary">Детайли</a>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Функции за работа със страницата на кошницата
function renderCart() {
    const cartContainer = document.getElementById('cartContainer');
    
    if (cart.length === 0) {
        cartContainer.innerHTML = `
            <div class="alert alert-info">
                Кошницата е празна. <a href="/search">Разгледайте нашите книги</a>.
            </div>
        `;
        
        document.getElementById('clearCartBtn').disabled = true;
        document.getElementById('updateCartBtn').disabled = true;
        document.getElementById('cartSummary').classList.add('d-none');
        return;
    }
    
    let html = '';
    
    cart.forEach(item => {
        const itemTotal = item.price * item.quantity;
        
        html += `
            <div class="cart-item d-flex flex-wrap align-items-center py-3 border-bottom">
                <div class="col-md-5 mb-2 mb-md-0">
                    <h5 class="mb-0"><a href="/books/${item.bookId}" class="text-decoration-none">${item.title}</a></h5>
                    <div class="text-primary">${formatPrice(item.price)}</div>
                </div>
                <div class="col-5 col-md-3 mb-2 mb-md-0">
                    <div class="input-group input-group-sm" style="max-width: 120px;">
                        <button class="btn btn-outline-secondary" type="button" onclick="updateCartItemQuantity(${item.bookId}, ${item.quantity - 1})">-</button>
                        <input type="number" class="form-control text-center" value="${item.quantity}" min="1" onchange="updateCartItemQuantity(${item.bookId}, parseInt(this.value) || 1)">
                        <button class="btn btn-outline-secondary" type="button" onclick="updateCartItemQuantity(${item.bookId}, ${item.quantity + 1})">+</button>
                    </div>
                </div>
                <div class="col-4 col-md-2 text-end mb-2 mb-md-0">
                    <span class="fw-bold">${formatPrice(itemTotal)}</span>
                </div>
                <div class="col-3 col-md-2 text-end">
                    <button class="btn btn-sm btn-outline-danger" onclick="removeFromCart(${item.bookId})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
    });
    
    // Add header and footer to cart
    html = `
        <div class="d-none d-md-flex fw-bold border-bottom pb-2 mb-2">
            <div class="col-md-5">Книга</div>
            <div class="col-md-3">Количество</div>
            <div class="col-md-2 text-end">Сума</div>
            <div class="col-md-2 text-end">Действия</div>
        </div>
        ${html}
    `;
    
    cartContainer.innerHTML = html;
    
    document.getElementById('clearCartBtn').disabled = false;
    document.getElementById('updateCartBtn').disabled = false;
    document.getElementById('cartSummary').classList.remove('d-none');
    
    // Update totals
    updateTotals();
}

// Функция за изпращане на поръчка
async function submitOrder(form) {
    const formData = getFormData(form);
    
    // Добавяме книгите от кошницата
    formData.items = cart.map(item => ({
        book_id: item.bookId,
        quantity: item.quantity
    }));
    
    // Проверка дали имаме артикули в кошницата
    if (formData.items.length === 0) {
        showToast('Грешка', 'Кошницата е празна', 'error');
        return false;
    }
    
    // Определяме API endpoint в зависимост от това дали потребителят е логнат
    const endpoint = currentUser ? '/api/orders' : '/api/guest-orders';
    
    try {
        const response = await fetchWithToken(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams(formData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Грешка при създаване на поръчка');
        }
        
        const data = await response.json();
        
        // Изчистваме кошницата
        clearCart();
        
        // Показваме съобщение за успех
        showToast('Успех', 'Поръчката е създадена успешно', 'success');
        
        // Пренасочваме към страницата с поръчки или към началната страница
        setTimeout(() => {
            window.location.href = currentUser ? '/orders' : '/';
        }, 1500);
        
        return true;
    } catch (error) {
        console.error('Error submitting order:', error);
        showToast('Грешка', error.message, 'error');
        return false;
    }
}

// Функция за добавяне на отзив
async function submitReview(form, bookId) {
    if (!currentUser) {
        showToast('Грешка', 'Трябва да сте влезли в профила си, за да добавите отзив', 'error');
        return false;
    }
    
    const formData = getFormData(form);
    
    try {
        const response = await fetchWithToken(`/api/books/${bookId}/reviews`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams(formData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Грешка при добавяне на отзив');
        }
        
        const data = await response.json();
        
        // Показваме съобщение за успех
        showToast('Успех', 'Отзивът е добавен успешно', 'success');
        
        // Презареждаме страницата, за да се покаже новият отзив
        setTimeout(() => {
            window.location.reload();
        }, 1500);
        
        return true;
    } catch (error) {
        console.error('Error submitting review:', error);
        showToast('Грешка', error.message, 'error');
        return false;
    }
}

// Инициализация на специфични страници
function initializeSearchPage() {
    const categoryFilter = document.getElementById('categoryFilter');
    const priceMinFilter = document.getElementById('priceMinFilter');
    const priceMaxFilter = document.getElementById('priceMaxFilter');
    const inStockFilter = document.getElementById('inStockFilter');
    const sortByFilter = document.getElementById('sortByFilter');
    const sortOrderFilter = document.getElementById('sortOrderFilter');
    const applyFiltersBtn = document.getElementById('applyFilters');
    
    // Ако не сме на страницата за търсене, прекратяваме
    if (!categoryFilter || !applyFiltersBtn) return;
    
    // Добавяме обработчици за бутоните
    applyFiltersBtn.addEventListener('click', () => {
        // Изграждаме URL с филтрите
        const params = new URLSearchParams(window.location.search);
        
        //Дебъгване
        console.log("Original params:", params.toString());
        
        // Обновяваме параметрите от филтрите
        if (categoryFilter.value) {
            params.set('category_id', categoryFilter.value);
            console.log("Setting category_id to:", categoryFilter.value); // Дебъгване
        } else {
            params.delete('category_id');
        }
        
        if (priceMinFilter.value) {
            params.set('min_price', priceMinFilter.value);
        } else {
            params.delete('min_price');
        }
        
        if (priceMaxFilter.value) {
            params.set('max_price', priceMaxFilter.value);
        } else {
            params.delete('max_price');
        }
        
        if (inStockFilter.checked) {
            params.set('in_stock', 'true');
        } else {
            params.delete('in_stock');
        }
        
        if (sortByFilter.value) {
            params.set('sort_by', sortByFilter.value);
            console.log("Setting sort_by to:", sortByFilter.value); // Дебъгване
        } else {
            params.delete('sort_by');
        }
        
        if (sortOrderFilter.value) {
            params.set('sort_desc', sortOrderFilter.value === 'desc' ? 'true' : 'false');
            console.log("Setting sort_desc to:", sortOrderFilter.value === 'desc' ? 'true' : 'false'); //Дебъг
        } else {
            params.delete('sort_desc');
        }
        
        // Пренасочваме към новия URL
        window.location.href = `/search?${params.toString()}`;
    });
}

// Викаме функциите за инициализация на специфични страници
document.addEventListener('DOMContentLoaded', function() {
    // Проверяваме на коя страница сме
    const path = window.location.pathname;
    
    if (path === '/search') {
        initializeSearchPage();
    } else if (path === '/cart') {
        renderCart();
    }
});
