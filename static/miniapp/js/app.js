/**
 * Universal Business Mini App
 * Telegram Mini Web App for BotFactory AI
 */

// ===== Telegram WebApp SDK =====
const tg = window.Telegram?.WebApp;
let botId = null;

// ===== State =====
const state = {
    business: null,
    catalog: [],
    cart: [],
    filteredCatalog: []
};

// ===== DOM Elements =====
const elements = {};

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initTelegram();
    initTabs();
    initSearch();
    initModals();
    initChat();
    loadData();
});

function initElements() {
    elements.businessLogo = document.getElementById('businessLogo');
    elements.businessName = document.getElementById('businessName');
    elements.businessDescription = document.getElementById('businessDescription');
    elements.catalogGrid = document.getElementById('catalogGrid');
    elements.cartItems = document.getElementById('cartItems');
    elements.cartEmpty = document.getElementById('cartEmpty');
    elements.cartSummary = document.getElementById('cartSummary');
    elements.cartTotal = document.getElementById('cartTotal');
    elements.cartBadge = document.getElementById('cartBadge');
    elements.orderBar = document.getElementById('orderBar');
    elements.orderCount = document.getElementById('orderCount');
    elements.orderTotal = document.getElementById('orderTotal');
    elements.orderButton = document.getElementById('orderButton');
    elements.orderModal = document.getElementById('orderModal');
    elements.orderForm = document.getElementById('orderForm');
    elements.itemModal = document.getElementById('itemModal');
    elements.loading = document.getElementById('loading');
    elements.toast = document.getElementById('toast');
    elements.searchInput = document.getElementById('searchInput');
    elements.contactPhone = document.getElementById('contactPhone');
    elements.contactAddress = document.getElementById('contactAddress');
    elements.contactHours = document.getElementById('contactHours');
    elements.contactTelegram = document.getElementById('contactTelegram');
    elements.callButton = document.getElementById('callButton');
    elements.telegramButton = document.getElementById('telegramButton');
    
    // New dynamic elements
    elements.tabLabelCatalog = document.getElementById('tabKatalogText');
    elements.tabLabelCart = document.getElementById('tabSavatText');
    elements.emptyCartText = document.getElementById('cartEmptyText');
    elements.bookingDateGroup = document.getElementById('bookingDateGroup');
    elements.bookingDateTime = document.getElementById('bookingDateTime');
}

function initTelegram() {
    if (tg) {
        tg.ready();
        tg.expand();

        // Apply Telegram theme
        if (tg.colorScheme === 'light') {
            document.body.classList.add('light-theme');
        }

        // Get bot_id from start parameter
        const startParam = tg.initDataUnsafe?.start_param;
        if (startParam) {
            botId = startParam;
        }

        // Set header color
        tg.setHeaderColor('#1a1a1a');
        tg.setBackgroundColor('#0f0f0f');
    }

    // Fallback: get bot_id from URL
    if (!botId) {
        const urlParams = new URLSearchParams(window.location.search);
        botId = urlParams.get('bot_id') || '1';
    }
}

function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update tabs
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update sections
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById(`${tabName}Section`).classList.add('active');
}

function initSearch() {
    elements.searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        if (query) {
            state.filteredCatalog = state.catalog.filter(item =>
                item.name.toLowerCase().includes(query) ||
                (item.description && item.description.toLowerCase().includes(query))
            );
        } else {
            state.filteredCatalog = [...state.catalog];
        }
        renderCatalog();
    });
}

function initModals() {
    // Order modal
    document.getElementById('closeModal').addEventListener('click', () => {
        elements.orderModal.classList.add('hidden');
    });

    elements.orderButton.addEventListener('click', openOrderModal);
    elements.orderForm.addEventListener('submit', submitOrder);

    // Item modal
    document.getElementById('closeItemModal').addEventListener('click', () => {
        elements.itemModal.classList.add('hidden');
    });

    // Quantity controls
    let currentItem = null;
    let currentQty = 1;

    document.getElementById('qtyMinus').addEventListener('click', () => {
        if (currentQty > 1) {
            currentQty--;
            document.getElementById('qtyValue').textContent = currentQty;
        }
    });

    document.getElementById('qtyPlus').addEventListener('click', () => {
        if (currentQty < 99) {
            currentQty++;
            document.getElementById('qtyValue').textContent = currentQty;
        }
    });

    document.getElementById('addToCartBtn').addEventListener('click', () => {
        if (currentItem) {
            addToCart(currentItem, currentQty);
            elements.itemModal.classList.add('hidden');
            currentQty = 1;
            document.getElementById('qtyValue').textContent = '1';
        }
    });

    // Store reference for item modal
    window.openItemModal = (item) => {
        currentItem = item;
        currentQty = 1;
        document.getElementById('qtyValue').textContent = '1';

        document.getElementById('itemModalImage').src = item.image || '/static/images/placeholder.png';
        document.getElementById('itemModalName').textContent = item.name;
        document.getElementById('itemModalDescription').textContent = item.description || '';
        document.getElementById('itemModalPrice').textContent = formatPrice(item.price);

        elements.itemModal.classList.remove('hidden');
    };
}

// ===== Data Loading =====
async function loadData() {
    showLoading();
    try {
        // Load business info
        const businessRes = await fetch(`/api/miniapp/business/${botId}`);
        if (businessRes.ok) {
            state.business = await businessRes.json();
            // Business endpoint ensures the bot is premium/admin, so we lock/unlock here:
            isPremium = true;
            updateVoiceUI();
            renderBusiness();
        }

        // Load catalog
        const catalogRes = await fetch(`/api/miniapp/catalog/${botId}`);
        if (catalogRes.ok) {
            state.catalog = await catalogRes.json();
            state.filteredCatalog = [...state.catalog];
            renderCatalog();
        }

        // Load contact
        const contactRes = await fetch(`/api/miniapp/contact/${botId}`);
        if (contactRes.ok) {
            const contact = await contactRes.json();
            renderContact(contact);
        }
    } catch (error) {
        console.error('Error loading data:', error);
        showToast('Ma\'lumotlarni yuklashda xatolik');
    } finally {
        hideLoading();
    }
}

// ===== Rendering =====
function renderBusiness() {
    if (!state.business) return;

    elements.businessName.textContent = state.business.name || 'Biznes';
    elements.businessDescription.textContent = state.business.description || '';

    if (state.business.logo) {
        elements.businessLogo.src = state.business.logo;
    } else {
        elements.businessLogo.src = '/static/images/default-logo.png';
    }

    // Apply custom theme
    if (state.business.theme) {
        const t = state.business.theme;
        const root = document.documentElement;
        if (t.accent) {
            root.style.setProperty('--accent', t.accent);
            root.style.setProperty('--accent-hover', t.accent);
        }
        if (t.bg) {
            root.style.setProperty('--bg-primary', t.bg);
            document.body.style.background = t.bg;
        }
        if (t.card) {
            root.style.setProperty('--bg-card', t.card);
        }
    }

    // Store currency
    if (state.business.currency) {
        state.currency = state.business.currency;
    }

    // Show welcome text
    if (state.business.welcome_text) {
        const welcomeEl = document.createElement('p');
        welcomeEl.className = 'welcome-text';
        welcomeEl.textContent = state.business.welcome_text;
        welcomeEl.style.cssText = 'color:var(--text-secondary);font-size:13px;padding:8px 16px 0;margin:0;text-align:center;';
        const header = document.querySelector('.header');
        if (header && !document.querySelector('.welcome-text')) {
            header.after(welcomeEl);
        }
    }
}

function renderCatalog() {
    const items = state.filteredCatalog;

    if (items.length === 0) {
        elements.catalogGrid.innerHTML = `
            <div class="empty-state" style="grid-column: 1/-1;">
                <span class="empty-icon">📦</span>
                <p>Mahsulotlar topilmadi</p>
            </div>
        `;
        return;
    }

    elements.catalogGrid.innerHTML = items.map(item => `
        <div class="catalog-item" onclick="openItemModal(${JSON.stringify(item).replace(/"/g, '&quot;')})">
            <img class="item-image" src="${item.image || '/static/images/placeholder.png'}" alt="${item.name}" onerror="this.src='/static/images/placeholder.png'">
            <div class="item-info">
                <div class="item-name">${item.name}</div>
                <div class="item-price">${formatPrice(item.price)}</div>
            </div>
        </div>
    `).join('');
}

function renderContact(contact) {
    elements.contactPhone.textContent = contact.phone || 'Ko\'rsatilmagan';
    elements.contactAddress.textContent = contact.address || 'Ko\'rsatilmagan';
    elements.contactHours.textContent = contact.working_hours || 'Ko\'rsatilmagan';

    if (contact.phone) {
        elements.callButton.href = `tel:${contact.phone}`;
    }

    // Telegram contact
    if (contact.telegram) {
        let tgId = contact.telegram.trim();
        // Handle full URL format: https://t.me/username
        if (tgId.includes('t.me/')) {
            tgId = tgId.split('t.me/').pop();
        }
        // Remove @ if present
        tgId = tgId.replace('@', '');
        elements.contactTelegram.textContent = `@${tgId}`;
        elements.telegramButton.href = `https://t.me/${tgId}`;
    } else {
        elements.contactTelegram.textContent = 'Ko\'rsatilmagan';
        elements.telegramButton.style.display = 'none';
    }
}

function renderCart() {
    if (state.cart.length === 0) {
        elements.cartItems.innerHTML = '';
        elements.cartEmpty.classList.remove('hidden');
        elements.cartSummary.classList.add('hidden');
        elements.orderBar.classList.add('hidden');
        return;
    }

    elements.cartEmpty.classList.add('hidden');
    elements.cartSummary.classList.remove('hidden');
    elements.orderBar.classList.remove('hidden');

    elements.cartItems.innerHTML = state.cart.map((item, index) => `
        <div class="cart-item">
            <img class="cart-item-image" src="${item.image || '/static/images/placeholder.png'}" alt="${item.name}">
            <div class="cart-item-info">
                <div class="cart-item-name">${item.name}</div>
                <div class="cart-item-price">${formatPrice(item.price)}</div>
                <div class="cart-item-actions">
                    <div class="quantity-control">
                        <button class="qty-btn" onclick="updateCartQty(${index}, -1)">-</button>
                        <span>${item.quantity}</span>
                        <button class="qty-btn" onclick="updateCartQty(${index}, 1)">+</button>
                    </div>
                    <button class="remove-btn" onclick="removeFromCart(${index})">🗑️</button>
                </div>
            </div>
        </div>
    `).join('');

    updateCartSummary();
}

function updateCartSummary() {
    const total = state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);

    elements.cartTotal.textContent = formatPrice(total);
    elements.orderCount.textContent = `${count} ta`;
    elements.orderTotal.textContent = formatPrice(total);

    // Update badge
    if (count > 0) {
        elements.cartBadge.textContent = count;
        elements.cartBadge.classList.remove('hidden');
    } else {
        elements.cartBadge.classList.add('hidden');
    }
}

// ===== Cart Operations =====
function addToCart(item, quantity = 1) {
    const existingIndex = state.cart.findIndex(i => i.id === item.id);

    if (existingIndex >= 0) {
        state.cart[existingIndex].quantity += quantity;
    } else {
        state.cart.push({
            ...item,
            quantity: quantity
        });
    }

    renderCart();
    showToast(`${item.name} savatga qo'shildi`);
}

window.updateCartQty = function (index, delta) {
    if (state.cart[index]) {
        state.cart[index].quantity += delta;
        if (state.cart[index].quantity <= 0) {
            state.cart.splice(index, 1);
        }
        renderCart();
    }
};

window.removeFromCart = function (index) {
    state.cart.splice(index, 1);
    renderCart();
};

// ===== Order =====
function openOrderModal() {
    if (state.cart.length === 0) return;

    // Pre-fill from Telegram user data
    if (tg && tg.initDataUnsafe?.user) {
        const user = tg.initDataUnsafe.user;
        document.getElementById('customerName').value = `${user.first_name || ''} ${user.last_name || ''}`.trim();
    }

    // Render order items
    document.getElementById('modalOrderItems').innerHTML = state.cart.map(item => `
        <div style="display: flex; justify-content: space-between; padding: 8px 0;">
            <span>${item.name} x${item.quantity}</span>
            <span>${formatPrice(item.price * item.quantity)}</span>
        </div>
    `).join('');

    const total = state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    document.getElementById('modalTotal').textContent = formatPrice(total);

    elements.orderModal.classList.remove('hidden');
}

async function submitOrder(e) {
    e.preventDefault();

    const orderData = {
        bot_id: botId,
        customer_name: document.getElementById('customerName').value,
        customer_phone: document.getElementById('customerPhone').value,
        customer_address: document.getElementById('customerAddress').value,
        booking_datetime: elements.bookingDateTime ? elements.bookingDateTime.value : null,
        note: document.getElementById('orderNote').value,
        items: state.cart.map(item => ({
            id: item.id,
            name: item.name,
            price: item.price,
            quantity: item.quantity
        })),
        total: state.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0),
        telegram_user_id: tg?.initDataUnsafe?.user?.id || null
    };

    showLoading();

    try {
        const response = await fetch('/api/miniapp/order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(orderData)
        });

        if (response.ok) {
            // Clear cart
            state.cart = [];
            renderCart();

            // Close modal
            elements.orderModal.classList.add('hidden');

            // Show success
            showToast('✅ Buyurtma qabul qilindi!');

            // Send data to Telegram
            if (tg) {
                tg.sendData(JSON.stringify({
                    type: 'order',
                    success: true,
                    order_id: (await response.json()).order_id
                }));
            }
        } else {
            const error = await response.json();
            showToast(`❌ Xatolik: ${error.message || 'Buyurtma yuborilmadi'}`);
        }
    } catch (error) {
        console.error('Order error:', error);
        showToast('❌ Tarmoq xatosi');
    } finally {
        hideLoading();
    }
}

// ===== Utilities =====
function formatPrice(price) {
    if (!price) return '0 ' + (state.currency || "so'm");
    return Number(price).toLocaleString('uz-UZ') + ' ' + (state.currency || "so'm");
}

function showLoading() {
    elements.loading.classList.remove('hidden');
}

function hideLoading() {
    elements.loading.classList.add('hidden');
}

function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.classList.remove('hidden');

    setTimeout(() => {
        elements.toast.classList.add('hidden');
    }, 3000);
}

// ===== AI Chat Module =====
let isPremium = false;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

function initChat() {
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const liveCallBtn = document.getElementById('liveCallInitBtn');

    if (!chatInput || !chatSendBtn) return;

    // Send text message
    chatSendBtn.addEventListener('click', () => sendTextMessage());
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendTextMessage();
        }
    });

    chatInput.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        const voiceLock = document.getElementById('voiceLock');
        if (val.length > 0) {
            liveCallBtn.classList.add('hidden');
            if (voiceLock) voiceLock.classList.add('hidden');
        } else {
            liveCallBtn.classList.remove('hidden');
            if (typeof updateVoiceUI === 'function') updateVoiceUI();
        }
    });
}

function checkPremiumStatus() {
    // This will be called after business data loads
    // Premium check is done via the chat API response
}

function updateVoiceUI() {
    const liveCallBtn = document.getElementById('liveCallInitBtn');
    const voiceLock = document.getElementById('voiceLock');
    if (!liveCallBtn || !voiceLock) return;

    if (isPremium) {
        liveCallBtn.classList.remove('hidden');
        voiceLock.classList.add('hidden');
    } else {
        liveCallBtn.classList.add('hidden');
        voiceLock.classList.remove('hidden');
    }
}

function addChatBubble(text, type, audioB64) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;

    // Remove welcome message
    const welcome = chatMessages.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${type}`;

    const label = document.createElement('span');
    label.className = 'bubble-label';
    label.textContent = type === 'user' ? 'Siz' : '🤖 AI';
    bubble.appendChild(label);

    const textEl = document.createElement('div');
    textEl.textContent = text;
    bubble.appendChild(textEl);

    // Audio player for bot responses
    if (audioB64 && type === 'bot') {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.src = `data:audio/mp3;base64,${audioB64}`;
        bubble.appendChild(audio);
        // Auto-play
        setTimeout(() => audio.play().catch(() => {}), 300);
    }

    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;

    const typing = document.createElement('div');
    typing.className = 'chat-typing';
    typing.id = 'typingIndicator';
    typing.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chatMessages.appendChild(typing);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

async function sendTextMessage() {
    const chatInput = document.getElementById('chatInput');
    if (!chatInput) return;

    const message = chatInput.value.trim();
    if (!message) return;

    chatInput.value = '';
    const chatSendB = document.getElementById('chatSendBtn');
    if (chatSendB) chatSendB.classList.add('hidden');
    updateVoiceUI();
    
    addChatBubble(message, 'user');
    showTypingIndicator();

    try {
        const baseUrl = window.location.origin;
        const response = await fetch(`${baseUrl}/api/miniapp/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bot_id: botId, message: message })
        });

        hideTypingIndicator();
        const data = await response.json();

        if (data.success) {
            addChatBubble(data.reply, 'bot');
            if (data.is_premium !== undefined) {
                isPremium = data.is_premium;
                updateVoiceUI();
            }
        } else {
            addChatBubble(data.error || 'Xatolik yuz berdi', 'bot');
        }
    } catch (err) {
        hideTypingIndicator();
        addChatBubble('Tarmoq xatosi. Qayta urinib ko\'ring.', 'bot');
    }
}

async function toggleRecording() {
    if (isRecording) {
        stopRecording();
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            await sendVoiceMessage(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;

        const voiceBtn = document.getElementById('voiceRecordBtn');
        const recIndicator = document.getElementById('recordingIndicator');
        if (voiceBtn) voiceBtn.classList.add('recording');
        if (recIndicator) recIndicator.classList.remove('hidden');
    } catch (err) {
        showToast('Mikrofon ruxsati berilmadi');
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }
    isRecording = false;

    const voiceBtn = document.getElementById('voiceRecordBtn');
    const recIndicator = document.getElementById('recordingIndicator');
    if (voiceBtn) voiceBtn.classList.remove('recording');
    if (recIndicator) recIndicator.classList.add('hidden');
}

async function sendVoiceMessage(audioBlob) {
    addChatBubble('🎤 Ovozli xabar yuborildi', 'user');
    showTypingIndicator();

    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'voice.webm');

        const baseUrl = window.location.origin;
        const response = await fetch(`${baseUrl}/api/miniapp/voice-chat?bot_id=${botId}`, {
            method: 'POST',
            body: formData
        });

        hideTypingIndicator();
        const data = await response.json();

        if (response.status === 403) {
            addChatBubble('🔒 ' + (data.message || 'Ovozli chat faqat Premium obunachilarga mavjud!'), 'bot');
            isPremium = false;
            updateVoiceUI();
            return;
        }

        if (data.success) {
            if (data.user_text) {
                // Show what was transcribed
                const userBubble = document.querySelector('.chat-bubble.user:last-of-type');
                if (userBubble) {
                    const textDiv = userBubble.querySelector('div');
                    if (textDiv) textDiv.textContent = `🎤 "${data.user_text}"`;
                }
            }
            addChatBubble(data.reply, 'bot', data.audio_response);
        } else {
            addChatBubble(data.error || 'Xatolik yuz berdi', 'bot');
        }
    } catch (err) {
        hideTypingIndicator();
        addChatBubble('Tarmoq xatosi. Qayta urinib ko\'ring.', 'bot');
    }
}
