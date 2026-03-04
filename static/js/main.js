// --- Chat widget (Jivo-like) ---
function initializeChatWidget() {
    const fab = document.getElementById('chat-fab');
    const widget = document.getElementById('chat-widget');
    const closeBtn = document.getElementById('chat-close');
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-text');
    const openBtn = document.getElementById('open-chatbot');
    const messages = document.getElementById('chat-messages');
    const speedDial = document.getElementById('chat-speed-dial');
    const speedChatBtn = document.getElementById('speed-chat');

    if (!widget || !messages) return;

    const openWidget = () => {
        widget.classList.remove('d-none');
        widget.classList.add('show');
        input && input.focus();
        // Hide speed dial when opening widget
        speedDial && speedDial.classList.remove('open');
    };
    const closeWidget = () => {
        widget.classList.remove('show');
        widget.classList.add('d-none');
    };

    // FAB toggles speed-dial
    fab && fab.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!speedDial) return;
        speedDial.classList.toggle('open');
    });
    openBtn && openBtn.addEventListener('click', openWidget);
    closeBtn && closeBtn.addEventListener('click', closeWidget);
    // Quick action: open chatbot
    speedChatBtn && speedChatBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openWidget();
    });
    // Close actions when clicking outside
    document.addEventListener('click', (e) => {
        if (!speedDial || !speedDial.classList.contains('open')) return;
        const isClickInside = speedDial.contains(e.target) || (fab && fab.contains(e.target));
        if (!isClickInside) speedDial.classList.remove('open');
    });

    form && form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!input || !input.value.trim()) return;

        const userText = input.value.trim();
        appendChatMsg('user', userText);
        input.value = '';

        try {
            const csrf = document.querySelector('meta[name="csrf-token"]');
            const res = await fetch('/api/webchat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf ? csrf.content : ''
                },
                body: JSON.stringify({ message: userText })
            });
            const data = await res.json();
            if (data && data.ok) {
                appendChatMsg('bot', data.reply || 'Javob tayyor! 🤖');
            } else {
                appendChatMsg('bot', "Kechirasiz, hozir javob bera olmadim. Keyinroq urinib ko'ring.");
            }
        } catch (err) {
            appendChatMsg('bot', "Tarmoq xatosi. Iltimos, qayta urinib ko'ring.");
        }
    });

    function appendChatMsg(role, text) {
        const div = document.createElement('div');
        div.className = 'msg ' + (role === 'user' ? 'user' : 'bot');
        div.textContent = text;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }
}
// BotFactory AI JavaScript functionality

document.addEventListener('DOMContentLoaded', function () {
    // Initialize tooltips
    initializeTooltips();

    // Initialize theme toggle
    initializeThemeToggle();

    // Chat widget init
    initializeChatWidget();

    // Initialize form validations
    initializeFormValidations();

    // Initialize dashboard features
    initializeDashboard();

    // Initialize subscription features
    initializeSubscription();

    // Initialize bot management
    initializeBotManagement();

    // Initialize animations
    initializeAnimations();
});

// Theme handling (light/dark) with persistence
function initializeThemeToggle() {
    const toggleBtn = document.getElementById('theme-toggle');
    const saved = localStorage.getItem('theme') || 'auto';
    applyTheme(saved);
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const current = localStorage.getItem('theme') || 'auto';
            const next = current === 'dark' ? 'light' : 'dark';
            localStorage.setItem('theme', next);
            applyTheme(next);
        });
    }
}

function updateNavbarTheme(theme) {
    const navbar = document.querySelector('.navbar');
    const footer = document.querySelector('footer');
    if (!navbar) return;
    // Reset classes
    navbar.classList.remove('navbar-light', 'bg-light', 'navbar-dark', 'bg-primary', 'bg-dark');
    if (theme === 'dark') {
        navbar.classList.add('navbar-dark', 'bg-dark');
        if (footer) {
            footer.classList.remove('bg-light', 'text-dark');
            footer.classList.add('bg-dark', 'text-white');
        }
    } else {
        navbar.classList.add('navbar-light', 'bg-light');
        if (footer) {
            footer.classList.remove('bg-dark', 'text-white');
            footer.classList.add('bg-light', 'text-dark');
        }
    }
}

function applyTheme(mode) {
    // Resolve auto to system preference
    let theme = mode;
    if (mode === 'auto') {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        theme = prefersDark ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-bs-theme', theme);
    updateThemeToggleUI(theme);
    updateNavbarTheme(theme);
}

function updateThemeToggleUI(theme) {
    const toggleBtn = document.getElementById('theme-toggle');
    if (!toggleBtn) return;
    const icon = toggleBtn.querySelector('i');
    const text = toggleBtn.querySelector('.theme-toggle-text');
    if (theme === 'dark') {
        if (icon) icon.className = 'fas fa-sun me-1';
        if (text) text.textContent = "Yorug'";
    } else {
        if (icon) icon.className = 'fas fa-moon me-1';
        if (text) text.textContent = "Qorong'i";
    }
}

// Tooltip initialization
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Form validation
function initializeFormValidations() {
    const forms = document.querySelectorAll('.needs-validation');

    Array.prototype.slice.call(forms).forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Password strength checker
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('input', function () {
            checkPasswordStrength(this.value);
        });
    }

    // Confirm password validation
    const confirmPasswordInput = document.getElementById('confirm_password');
    if (confirmPasswordInput && passwordInput) {
        confirmPasswordInput.addEventListener('input', function () {
            validatePasswordConfirmation(passwordInput.value, this.value);
        });
    }

    // Telegram token validation
    const tokenInput = document.getElementById('telegram_token');
    if (tokenInput) {
        tokenInput.addEventListener('input', function () {
            validateTelegramToken(this.value);
        });
    }
}

// Password strength checker
function checkPasswordStrength(password) {
    const strengthIndicator = document.getElementById('password-strength');
    if (!strengthIndicator) return;

    let strength = 0;
    const checks = {
        length: password.length >= 8,
        lowercase: /[a-z]/.test(password),
        uppercase: /[A-Z]/.test(password),
        number: /\d/.test(password),
        special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
    };

    strength = Object.values(checks).filter(Boolean).length;

    const levels = ['Juda zaif', 'Zaif', 'O\'rtacha', 'Kuchli', 'Juda kuchli'];
    const colors = ['danger', 'warning', 'info', 'success', 'success'];

    strengthIndicator.innerHTML = `
        <div class="progress mt-2">
            <div class="progress-bar bg-${colors[strength - 1]}" style="width: ${(strength / 5) * 100}%"></div>
        </div>
        <small class="text-${colors[strength - 1]}">${levels[strength - 1] || ''}</small>
    `;
}

// Password confirmation validation
function validatePasswordConfirmation(password, confirmPassword) {
    const confirmInput = document.getElementById('confirm_password');
    if (!confirmInput) return;

    if (password !== confirmPassword) {
        confirmInput.setCustomValidity('Parollar mos kelmaydi');
        confirmInput.classList.add('is-invalid');
    } else {
        confirmInput.setCustomValidity('');
        confirmInput.classList.remove('is-invalid');
        confirmInput.classList.add('is-valid');
    }
}

// Telegram token validation
function validateTelegramToken(token) {
    const tokenInput = document.getElementById('telegram_token');
    if (!tokenInput) return;

    const tokenPattern = /^\d+:[A-Za-z0-9_-]{35,}$/;

    if (token && !tokenPattern.test(token)) {
        tokenInput.setCustomValidity('Token formati noto\'g\'ri');
        tokenInput.classList.add('is-invalid');
    } else {
        tokenInput.setCustomValidity('');
        tokenInput.classList.remove('is-invalid');
        if (token) tokenInput.classList.add('is-valid');
    }
}

// Dashboard functionality
function initializeDashboard() {
    // Auto-refresh dashboard data
    if (window.location.pathname === '/dashboard') {
        setInterval(refreshDashboardData, 300000); // 5 minutes
    }

    // Bot status toggle
    const statusToggles = document.querySelectorAll('.bot-status-toggle');
    statusToggles.forEach(toggle => {
        toggle.addEventListener('change', function () {
            toggleBotStatus(this.dataset.botId, this.checked);
        });
    });

    // Quick actions
    const quickActions = document.querySelectorAll('.quick-action');
    quickActions.forEach(action => {
        action.addEventListener('click', function (e) {
            e.preventDefault();
            const actionType = this.dataset.action;
            const botId = this.dataset.botId;
            handleQuickAction(actionType, botId);
        });
    });
}

// Subscription functionality
function initializeSubscription() {
    // Payment method selection
    const paymentMethods = document.querySelectorAll('input[name="method"]');
    paymentMethods.forEach(method => {
        method.addEventListener('change', function () {
            updatePaymentMethodDisplay(this.value);
        });
    });

    // Subscription upgrade confirmation - only for buttons WITHOUT data-bs-toggle
    // (buttons with data-bs-toggle="modal" are handled by Bootstrap natively)
    const upgradeButtons = document.querySelectorAll('[data-subscription]:not([data-bs-toggle])');
    upgradeButtons.forEach(button => {
        button.addEventListener('click', function () {
            const subscription = this.dataset.subscription;
            const amount = this.dataset.amount;
            showUpgradeConfirmation(subscription, amount);
        });
    });
}

// Bot management functionality
function initializeBotManagement() {
    // File upload handling
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function () {
            handleFileUpload(this);
        });
    });

    // Bot deletion confirmation
    const deleteButtons = document.querySelectorAll('.delete-bot');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.preventDefault();
            confirmBotDeletion(this.dataset.botId, this.dataset.botName);
        });
    });

    // Knowledge base management
    const knowledgeUpload = document.getElementById('knowledge-upload');
    if (knowledgeUpload) {
        knowledgeUpload.addEventListener('change', function () {
            previewKnowledgeFile(this.files[0]);
        });
    }
}

// Animation initialization
function initializeAnimations() {
    // Fade in animations for cards
    const cards = document.querySelectorAll('.card');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in-up');
            }
        });
    });

    cards.forEach(card => {
        observer.observe(card);
    });

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const href = this.getAttribute('href');
            if (href && href !== '#') {
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
}

// Utility functions
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;

    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', function () {
        toast.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    document.body.appendChild(container);
    return container;
}

function showLoadingSpinner(element) {
    element.classList.add('loading');
    element.disabled = true;
}

function hideLoadingSpinner(element) {
    element.classList.remove('loading');
    element.disabled = false;
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('uz-UZ').format(amount) + ' so\'m';
}

function formatDate(date) {
    return new Intl.DateTimeFormat('uz-UZ').format(new Date(date));
}

// Dashboard functions
function refreshDashboardData() {
    fetch('/api/dashboard/refresh')
        .then(response => response.json())
        .then(data => {
            updateDashboardCards(data);
        })
        .catch(error => {
            console.error('Dashboard refresh error:', error);
        });
}

function updateDashboardCards(data) {
    // Update bot count
    const botCountElement = document.querySelector('[data-metric="bot-count"]');
    if (botCountElement) {
        botCountElement.textContent = data.bot_count;
    }

    // Update active bots
    const activeBotsElement = document.querySelector('[data-metric="active-bots"]');
    if (activeBotsElement) {
        activeBotsElement.textContent = data.active_bots;
    }
}

function toggleBotStatus(botId, isActive) {
    showLoadingSpinner(document.querySelector(`[data-bot-id="${botId}"]`));

    fetch(`/api/bot/${botId}/toggle`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({ active: isActive })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Bot holati yangilandi', 'success');
            } else {
                showToast('Xatolik yuz berdi', 'error');
            }
        })
        .catch(error => {
            showToast('Tarmoq xatosi', 'error');
        })
        .finally(() => {
            hideLoadingSpinner(document.querySelector(`[data-bot-id="${botId}"]`));
        });
}

function handleQuickAction(actionType, botId) {
    let endpoint, message;

    switch (actionType) {
        case 'restart':
            endpoint = `/api/bot/${botId}/restart`;
            message = 'Bot qayta ishga tushirildi';
            break;
        case 'test':
            endpoint = `/api/bot/${botId}/test`;
            message = 'Test xabari yuborildi';
            break;
        default:
            return;
    }

    fetch(endpoint, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCSRFToken()
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast(message, 'success');
            } else {
                showToast(data.error || 'Xatolik yuz berdi', 'error');
            }
        })
        .catch(error => {
            showToast('Tarmoq xatosi', 'error');
        });
}

// Payment functions
function updatePaymentMethodDisplay(method) {
    const methodCards = document.querySelectorAll('.payment-card');
    methodCards.forEach(card => {
        card.classList.remove('selected');
    });

    const selectedCard = document.querySelector(`input[value="${method}"]`).closest('.payment-method').querySelector('.payment-card');
    selectedCard.classList.add('selected');
}

function showUpgradeConfirmation(subscription, amount) {
    const modal = new bootstrap.Modal(document.getElementById('upgradeConfirmModal'));
    document.getElementById('upgrade-subscription').textContent = subscription;
    document.getElementById('upgrade-amount').textContent = formatCurrency(amount);
    modal.show();
}

// File handling functions
function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;

    const allowedTypes = [
        'text/plain',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/csv',
        'application/csv',
        'application/vnd.ms-excel',  // CSV yoki eski Excel
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // Yangi Excel .xlsx
        'text/comma-separated-values',
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp'
    ];
    const maxSize = 16 * 1024 * 1024; // 16MB

    if (!allowedTypes.includes(file.type)) {
        showToast('Faqat .txt, .docx, .csv, excel va rasm fayllari qo\'llab-quvvatlanadi', 'error');
        input.value = '';
        return;
    }

    if (file.size > maxSize) {
        showToast('Fayl hajmi 16MB dan oshmasligi kerak', 'error');
        input.value = '';
        return;
    }

    updateFileUploadDisplay(input, file);
}

function updateFileUploadDisplay(input, file) {
    const displayElement = input.nextElementSibling;
    if (displayElement && displayElement.classList.contains('file-upload-display')) {
        displayElement.innerHTML = `
            <i class="fas fa-file-text me-2"></i>
            ${file.name} (${formatFileSize(file.size)})
        `;
    }
}

function previewKnowledgeFile(file) {
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (e) {
        const preview = document.getElementById('knowledge-preview');
        if (preview) {
            const content = e.target.result;
            preview.innerHTML = `
                <h6>Fayl preview:</h6>
                <div class="border p-3 bg-light">
                    <pre class="mb-0">${content.substring(0, 500)}${content.length > 500 ? '...' : ''}</pre>
                </div>
            `;
        }
    };

    if (file.type === 'text/plain') {
        reader.readAsText(file);
    }
}

function confirmBotDeletion(botId, botName) {
    if (confirm(`"${botName}" botini o'chirishni xohlaysizmi? Bu amalni bekor qilib bo'lmaydi.`)) {
        deleteBotRequest(botId);
    }
}

function deleteBotRequest(botId) {
    fetch(`/api/bot/${botId}/delete`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': getCSRFToken()
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Bot o\'chirildi', 'success');
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showToast('Xatolik yuz berdi', 'error');
            }
        })
        .catch(error => {
            showToast('Tarmoq xatosi', 'error');
        });
}

// Utility functions
function getCSRFToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.getAttribute('content') : '';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Copy to clipboard function
function copyToClipboard(text, successMessage = 'Nusxalandi!') {
    navigator.clipboard.writeText(text).then(function () {
        showToast(successMessage, 'success');
    }, function (err) {
        showToast('Nusxalashda xatolik', 'error');
    });
}

// Auto-save functionality for forms
function initializeAutoSave(formSelector) {
    const form = document.querySelector(formSelector);
    if (!form) return;

    const inputs = form.querySelectorAll('input, textarea, select');
    inputs.forEach(input => {
        input.addEventListener('input', debounce(() => {
            saveFormData(form);
        }, 1000));
    });
}

function saveFormData(form) {
    const formData = new FormData(form);
    const data = Object.fromEntries(formData);
    localStorage.setItem(`form_${form.id}`, JSON.stringify(data));
}

function loadFormData(form) {
    const savedData = localStorage.getItem(`form_${form.id}`);
    if (savedData) {
        const data = JSON.parse(savedData);
        Object.keys(data).forEach(key => {
            const input = form.querySelector(`[name="${key}"]`);
            if (input) {
                input.value = data[key];
            }
        });
    }
}

// Export functions for global use
window.BotFactory = {
    showToast,
    formatCurrency,
    formatDate,
    copyToClipboard,
    toggleBotStatus,
    handleQuickAction
};
