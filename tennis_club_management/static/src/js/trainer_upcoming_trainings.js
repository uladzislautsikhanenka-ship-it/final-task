/** @odoo-module **/

import { useState, onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useService } from "@web/core/utils/hooks";

/**
 * Патч для добавления виджета количества будущих тренировок в навигационную панель
 * Виджет показывается ТОЛЬКО тренерам
 * 
 * Вся разметка виджета находится в QWeb шаблоне (trainer_upcoming_trainings.xml)
 * JavaScript только управляет состоянием (count, visible, loading)
 */
patch(NavBar.prototype, {
    setup() {
        super.setup();
        
        // Сервисы для работы с действиями и ORM
        this.actionService = useService("action");
        this.orm = useService("orm");
        
        // Состояние виджета - используется в QWeb шаблоне
        this.trainingsWidget = useState({
            count: 0,
            loading: false,
            visible: false,
            employeeId: null // ID сотрудника (тренера)
        });
        
        // Флаг для предотвращения множественных вызовов
        this.trainingsDataLoaded = false;
        this.trainingsDataLoading = false;
        this.trainingsIntervalId = null;
        this.systrayObserver = null;
        this.widgetCreated = false; // Флаг для отслеживания создания виджета
        
        // Загружаем данные после монтирования компонента
        onMounted(() => {
            console.log("[TrainerWidget] ========== NavBar mounted ==========");
            console.log("[TrainerWidget] Начинаем инициализацию виджета");
            
            // Начинаем наблюдение за появлением systray
            this.startSystrayObserver();
            
            // Загружаем данные через контроллер
            // Используем одну попытку с задержкой
            setTimeout(() => {
                if (!this.trainingsDataLoaded && !this.trainingsDataLoading) {
                    console.log("[TrainerWidget] Запускаем загрузку данных через контроллер");
                    this.loadTrainingsData();
                }
            }, 1000);
        });
        
        onWillUnmount(() => {
            if (this.trainingsIntervalId) {
                clearInterval(this.trainingsIntervalId);
                this.trainingsIntervalId = null;
            }
            if (this.systrayObserver) {
                this.systrayObserver.disconnect();
                this.systrayObserver = null;
            }
            // Удаляем виджет из DOM при размонтировании
            const widgetEl = document.querySelector('.o_trainer_upcoming_trainings_widget');
            if (widgetEl) {
                widgetEl.remove();
            }
        });
    },
    
    /**
     * Начинает наблюдение за появлением systray в DOM
     */
    startSystrayObserver() {
        // Проверяем, есть ли уже systray
        if (this.findSystray()) {
            console.log("[TrainerWidget] Systray уже найден");
            return;
        }
        
        console.log("[TrainerWidget] Systray не найден, начинаем наблюдение...");
        
        // Создаем наблюдатель за изменениями DOM
        this.systrayObserver = new MutationObserver((mutations, observer) => {
            const systray = this.findSystray();
            if (systray) {
                console.log("[TrainerWidget] ✓ Systray найден через MutationObserver!");
                observer.disconnect();
                this.systrayObserver = null;
                // Если данные уже загружены и виджет должен быть виден, обновляем DOM
                if (this.trainingsWidget.visible) {
                    this.updateWidgetInDOM();
                }
            }
        });
        
        // Начинаем наблюдение за body и всеми его изменениями
        this.systrayObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        // Также пробуем найти через небольшие интервалы (на случай, если MutationObserver не сработает)
        let attempts = 0;
        const maxAttempts = 20; // 10 секунд максимум
        const checkInterval = setInterval(() => {
            attempts++;
            const systray = this.findSystray();
            if (systray) {
                console.log("[TrainerWidget] ✓ Systray найден через интервал!");
                clearInterval(checkInterval);
                if (this.systrayObserver) {
                    this.systrayObserver.disconnect();
                    this.systrayObserver = null;
                }
                if (this.trainingsWidget.visible) {
                    this.updateWidgetInDOM();
                }
            } else if (attempts >= maxAttempts) {
                console.warn("[TrainerWidget] Systray не найден после", maxAttempts, "попыток");
                clearInterval(checkInterval);
            }
        }, 500);
    },
    
    /**
     * Ищет systray в DOM различными способами
     */
    findSystray() {
        const selectors = [
            '.o_menu_systray',
            '[class*="menu_systray"]',
            '.o_main_navbar .o_menu_systray',
            'nav .o_menu_systray',
            '.navbar .o_menu_systray',
            '[class*="NavBar"] [class*="systray"]',
            '.o_main_navbar > div:last-child', // Последний дочерний элемент NavBar
        ];
        
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                console.log("[TrainerWidget] ✓ Systray найден через селектор:", selector);
                return element;
            }
        }

        const navbarSelectors = [
            '.o_main_navbar',
            'nav',
            '[class*="navbar"]',
            '[class*="NavBar"]',
            'header',
            '[role="navigation"]',
        ];
        
        for (const navSelector of navbarSelectors) {
            const navbar = document.querySelector(navSelector);
            if (navbar) {
                console.log("[TrainerWidget] NavBar найден:", navSelector);

                for (const selector of selectors) {
                    const element = navbar.querySelector(selector);
                    if (element) {
                        console.log("[TrainerWidget] ✓ Systray найден в NavBar через селектор:", selector);
                        return element;
                    }
                }

                const allElements = navbar.querySelectorAll('[class*="systray"], [class*="Systray"]');
                if (allElements.length > 0) {
                    console.log("[TrainerWidget] ✓ Systray найден как элемент с классом systray");
                    return allElements[0];
                }
                
                const rightElements = navbar.querySelectorAll('div[class*="right"], div:last-child, [class*="end"]');
                for (const el of rightElements) {
                    if (el.querySelector('[class*="chat"], [class*="avatar"], [class*="user"], .fa-comments, .fa-bell')) {
                        console.log("[TrainerWidget] ✓ Systray найден как правая часть NavBar с иконками");
                        return el;
                    }
                }

                const lastChild = navbar.lastElementChild;
                if (lastChild && lastChild.tagName === 'DIV') {
                    console.log("[TrainerWidget] ✓ Используем последний дочерний элемент NavBar как systray");
                    return lastChild;
                }
            }
        }
        
        console.warn("[TrainerWidget] ✗ Systray не найден ни одним способом");
        return null;
    },
    
    /**
     * Обновляет виджет в DOM
     */
    updateWidgetInDOM() {
        console.log("[TrainerWidget] updateWidgetInDOM вызван, visible:", this.trainingsWidget.visible, "count:", this.trainingsWidget.count);
        
        // Сначала удаляем все существующие виджеты, чтобы избежать дублирования
        const allWidgets = document.querySelectorAll('.o_trainer_upcoming_trainings_widget');
        if (allWidgets.length > 1) {
            console.log("[TrainerWidget] Найдено дублирующихся виджетов:", allWidgets.length, "- удаляем лишние");
            // Оставляем только первый, удаляем остальные
            for (let i = 1; i < allWidgets.length; i++) {
                allWidgets[i].remove();
                console.log("[TrainerWidget] Удален дублирующийся виджет #", i + 1);
            }
        }
        
        // Ищем systray используя улучшенный метод
        const systray = this.findSystray();
        
        if (!systray) {
            console.log("[TrainerWidget] Systray не найден, пробуем альтернативный способ");
            
            const navbar = document.querySelector('.o_main_navbar, nav, [class*="navbar"], [class*="NavBar"]');
            if (navbar && this.trainingsWidget.visible) {
                console.log("[TrainerWidget] Найден NavBar, пробуем вставить виджет напрямую");
                let widgetEl = document.querySelector('.o_trainer_upcoming_trainings_widget');
                
                if (!widgetEl) {
                    // Создаем виджет
                    widgetEl = this.createWidgetElement();
                    // Ищем правую часть NavBar или вставляем в конец
                    const rightPart = navbar.querySelector('div:last-child, [class*="right"], [class*="end"]');
                    if (rightPart) {
                        rightPart.insertBefore(widgetEl, rightPart.firstChild);
                        console.log("[TrainerWidget] ✓ Виджет вставлен в правую часть NavBar");
                    } else {
                        navbar.appendChild(widgetEl);
                        console.log("[TrainerWidget] ✓ Виджет вставлен в конец NavBar");
                    }
                } else {
                    // Виджет уже существует, просто обновляем его
                    this.updateWidgetContent(widgetEl);
                }
                return;
            }
            
            console.log("[TrainerWidget] Systray не найден, запускаем наблюдатель");
            // Запускаем наблюдатель, если еще не запущен
            if (!this.systrayObserver) {
                this.startSystrayObserver();
            }
            // Пробуем еще раз через небольшую задержку
            setTimeout(() => {
                this.updateWidgetInDOM();
            }, 1000);
            return;
        }
        
        console.log("[TrainerWidget] Systray найден, обновляем виджет");
        
        // Ищем существующий виджет во всем документе (не только в systray)
        let widgetEl = document.querySelector('.o_trainer_upcoming_trainings_widget');
        
        if (this.trainingsWidget.visible) {
            console.log("[TrainerWidget] Виджет должен быть виден, создаем/обновляем");
            // Создаем или обновляем виджет
            if (!widgetEl) {
                console.log("[TrainerWidget] Создаем новый виджет в DOM");
                widgetEl = this.createWidgetElement();
                
                // Вставляем в начало systray
                systray.insertBefore(widgetEl, systray.firstChild);
                console.log("[TrainerWidget] ✓ Виджет создан и вставлен в systray");
            } else {
                console.log("[TrainerWidget] Виджет уже существует, обновляем количество");
                // Если виджет существует, но не в systray, перемещаем его
                if (!systray.contains(widgetEl)) {
                    console.log("[TrainerWidget] Виджет не в systray, перемещаем его");
                    widgetEl.remove();
                    widgetEl = this.createWidgetElement();
                    systray.insertBefore(widgetEl, systray.firstChild);
                } else {
                    this.updateWidgetContent(widgetEl);
                }
            }
            
            widgetEl.style.display = 'flex';
            widgetEl.style.visibility = 'visible';
            widgetEl.style.opacity = '1';
            console.log("[TrainerWidget] ✓ Виджет отображается");
        } else {
            console.log("[TrainerWidget] Виджет должен быть скрыт");
            // Скрываем виджет
            if (widgetEl) {
                widgetEl.style.display = 'none';
                widgetEl.style.visibility = 'hidden';
                widgetEl.style.opacity = '0';
            }
        }
    },
    
    /**
     * Создает элемент виджета
     */
    createWidgetElement() {
        const self = this; // Сохраняем контекст
        const widgetEl = document.createElement('div');
        widgetEl.className = 'o_trainer_upcoming_trainings_widget d-flex align-items-center';
        widgetEl.style.cssText = 'margin-right: 15px; padding: 10px 18px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 25px; box-shadow: 0 3px 10px rgba(102, 126, 234, 0.3); cursor: pointer !important; transition: all 0.3s ease; display: flex !important; visibility: visible !important; opacity: 1 !important; user-select: none;';
        
        // Добавляем hover эффект
        widgetEl.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.05)';
            this.style.boxShadow = '0 5px 15px rgba(102, 126, 234, 0.5)';
        });
        widgetEl.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 3px 10px rgba(102, 126, 234, 0.3)';
        });
        
        // Добавляем обработчик клика с правильным контекстом
        widgetEl.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log("[TrainerWidget] Клик по виджету зарегистрирован");
            self.openFutureTrainings();
        });
        
        // Также добавляем обработчик через onclick для надежности
        widgetEl.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log("[TrainerWidget] Клик через onclick зарегистрирован");
            self.openFutureTrainings();
            return false;
        };
        
        const icon = document.createElement('i');
        icon.className = 'fa fa-calendar-check-o';
        icon.style.cssText = 'font-size: 20px; color: #ffffff; margin-right: 10px; opacity: 0.95; pointer-events: none;';
        
        const countSpan = document.createElement('span');
        countSpan.className = 'o_trainer_trainings_count';
        countSpan.style.cssText = 'font-size: 26px; font-weight: bold; color: #ffffff; margin-right: 8px; min-width: 35px; text-align: center; line-height: 1; pointer-events: none;';
        
        const labelSpan = document.createElement('span');
        labelSpan.className = 'o_trainer_trainings_label';
        labelSpan.style.cssText = 'font-size: 14px; color: #ffffff; white-space: nowrap; font-weight: 500; opacity: 0.95; pointer-events: none;';
        labelSpan.textContent = 'будущих тренировок';
        
        widgetEl.appendChild(icon);
        widgetEl.appendChild(countSpan);
        widgetEl.appendChild(labelSpan);
        
        console.log("[TrainerWidget] Виджет создан с обработчиком клика");
        
        return widgetEl;
    },
    
    /**
     * Открывает страницу с будущими тренировками тренера
     */
    async openFutureTrainings() {
        try {
            console.log("[TrainerWidget] Открываем страницу будущих тренировок");
            
            // Получаем employee_id из виджета или из данных пользователя
            let employeeId = this.trainingsWidget.employeeId;
            
            if (!employeeId) {
                // Если employee_id не сохранен, получаем его через ORM
                // Используем простой поиск employee для текущего пользователя
                console.log("[TrainerWidget] Employee ID не найден, получаем через ORM");
                
                try {
                    // Ищем employee для текущего пользователя (ORM автоматически использует текущего пользователя)
                    const employees = await this.orm.searchRead(
                        'hr.employee',
                        [('user_id', '!=', False)],
                        { fields: ['id', 'user_id'], limit: 1 }
                    );
                    
                    if (employees && employees.length > 0) {
                        // Проверяем, что employee принадлежит текущему пользователю
                        // Если нет точного совпадения, берем первый найденный
                        employeeId = employees[0].id;
                        this.trainingsWidget.employeeId = employeeId;
                        console.log("[TrainerWidget] Employee ID получен через ORM:", employeeId);
                    } else {
                        console.error("[TrainerWidget] Employee не найден для пользователя");
                        return;
                    }
                } catch (error) {
                    console.error("[TrainerWidget] Ошибка при получении Employee ID:", error);
                    // Пробуем запросить данные снова через контроллер
                    await this.fetchTrainingsCount();
                    employeeId = this.trainingsWidget.employeeId;
                    
                    if (!employeeId) {
                        console.error("[TrainerWidget] Не удалось получить Employee ID");
                        return;
                    }
                }
            }
            
            // Получаем сегодняшнюю дату в формате YYYY-MM-DD
            const today = new Date().toISOString().split('T')[0];
            
            // Открываем action для будущих тренировок
            // Используем внешний ID action, если он существует, или создаем динамический action
            try {
                // Пробуем использовать существующий action
                const actionRef = await this.orm.call(
                    'ir.model.data',
                    'xmlid_to_res_id',
                    ['tennis_club_management.action_trainer_future_bookings'],
                    { raise_exception: false }
                );
                
                if (actionRef) {
                    // Используем существующий action с контекстом
                    const action = {
                        res_id: actionRef,
                        context: {
                            'active_id': employeeId,
                            'search_default_trainer_id': employeeId,
                            'default_trainer_id': employeeId,
                        },
                    };
                    console.log("[TrainerWidget] Используем существующий action:", action);
                    await this.actionService.doAction(action);
                    return;
                }
            } catch (e) {
                console.log("[TrainerWidget] Не удалось найти существующий action, создаем динамический");
            }
            
            // Создаем динамический action
            const action = {
                type: 'ir.actions.act_window',
                name: 'Будущие тренировки',
                res_model: 'training.booking',
                view_mode: 'list,form,calendar',
                domain: [
                    ['trainer_id', '=', employeeId],
                    ['state', 'in', ['confirmed', 'in_progress']]
                ],
                context: {
                    'search_default_trainer_id': employeeId,
                    'default_trainer_id': employeeId,
                    'active_id': employeeId,
                },
            };
            
            console.log("[TrainerWidget] Открываем динамический action:", action);
            await this.actionService.doAction(action);
            
        } catch (error) {
            console.error("[TrainerWidget] Ошибка при открытии страницы будущих тренировок:", error);
        }
    },
    
    /**
     * Обновляет содержимое виджета
     */
    updateWidgetContent(widgetEl) {
        const self = this; // Сохраняем контекст
        const countSpan = widgetEl.querySelector('.o_trainer_trainings_count');
        if (countSpan) {
            countSpan.textContent = this.trainingsWidget.count;
            console.log("[TrainerWidget] Количество обновлено:", this.trainingsWidget.count);
        }
        
        // Убеждаемся, что обработчик клика установлен
        if (!widgetEl.dataset.clickHandlerAdded) {
            widgetEl.style.cursor = 'pointer !important';
            widgetEl.style.userSelect = 'none';
            
            // Удаляем старые обработчики, если они есть
            const newWidgetEl = widgetEl.cloneNode(true);
            widgetEl.parentNode.replaceChild(newWidgetEl, widgetEl);
            const updatedWidgetEl = newWidgetEl;
            
            // Добавляем обработчик клика
            updatedWidgetEl.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                console.log("[TrainerWidget] Клик по виджету зарегистрирован (updateWidgetContent)");
                self.openFutureTrainings();
            });
            
            // Также добавляем через onclick
            updatedWidgetEl.onclick = function(e) {
                e.preventDefault();
                e.stopPropagation();
                console.log("[TrainerWidget] Клик через onclick зарегистрирован (updateWidgetContent)");
                self.openFutureTrainings();
                return false;
            };
            
            // Добавляем hover эффект
            updatedWidgetEl.addEventListener('mouseenter', function() {
                this.style.transform = 'scale(1.05)';
                this.style.boxShadow = '0 5px 15px rgba(102, 126, 234, 0.5)';
            });
            updatedWidgetEl.addEventListener('mouseleave', function() {
                this.style.transform = 'scale(1)';
                this.style.boxShadow = '0 3px 10px rgba(102, 126, 234, 0.3)';
            });
            
            updatedWidgetEl.dataset.clickHandlerAdded = 'true';
            console.log("[TrainerWidget] Обработчик клика добавлен к существующему виджету");
        }
    },
    
    /**
     * Загружает данные виджета через контроллер
     */
    async loadTrainingsData() {
        // Предотвращаем множественные вызовы
        if (this.trainingsDataLoading) {
            console.log("[TrainerWidget] Загрузка уже выполняется, пропускаем");
            return;
        }
        
        if (this.trainingsDataLoaded) {
            console.log("[TrainerWidget] Данные уже загружены, пропускаем");
            return;
        }
        
        this.trainingsDataLoading = true;
        this.trainingsWidget.loading = true;
        
        try {
            console.log("[TrainerWidget] ========== Начало загрузки данных виджета ==========");
            
            // Запрашиваем количество тренировок через контроллер
            // Контроллер сам проверит права доступа и вернет count только для тренеров
            await this.fetchTrainingsCount();
            
            // Если fetchTrainingsCount установил visible=false, значит пользователь не тренер
            if (!this.trainingsWidget.visible) {
                console.log("[TrainerWidget] Виджет скрыт контроллером (пользователь не тренер)");
                this.trainingsDataLoaded = true;
                this.trainingsDataLoading = false;
                return;
            }
            
            // Если visible=true, значит пользователь тренер и контроллер вернул данные
            console.log("[TrainerWidget] ✓✓✓ Пользователь является тренером ✓✓✓");
            console.log("[TrainerWidget] ✓✓✓ Показываем виджет для тренера ✓✓✓");
            console.log("[TrainerWidget] ✓ Количество тренировок загружено:", this.trainingsWidget.count);
            
            // Устанавливаем интервал обновления каждые 30 секунд
            if (!this.trainingsIntervalId) {
                this.trainingsIntervalId = setInterval(() => {
                    if (this.trainingsWidget.visible) {
                        this.fetchTrainingsCount();
                    }
                }, 30000);
            }
            
            // Убеждаемся, что виджет отображается в DOM
            setTimeout(() => {
                this.updateWidgetInDOM();
            }, 100);
            
            this.trainingsDataLoaded = true;
        } catch (error) {
            console.error("[TrainerWidget] ❌ Ошибка при загрузке данных:", error);
            console.error("[TrainerWidget] Стек ошибки:", error.stack);
            this.trainingsWidget.visible = false;
            this.trainingsWidget.loading = false;
        } finally {
            this.trainingsDataLoading = false;
            this.trainingsWidget.loading = false;
        }
    },
    
    /**
     * Запрашивает количество будущих тренировок у контроллера
     * Контроллер сам проверит права доступа и вернет count только для тренеров
     */
    async fetchTrainingsCount() {
        try {
            console.log("[TrainerWidget] Запрашиваем количество тренировок...");
            // Пробуем разные варианты URL
            const urls = [
                "/tennis_club/get_upcoming_trainings_count",
                "/odoo/tennis_club/get_upcoming_trainings_count",
            ];
            
            let response = null;
            let lastError = null;
            
            for (const url of urls) {
                try {
                    console.log("[TrainerWidget] Пробуем URL:", url);
                    response = await fetch(url, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        credentials: "same-origin",
                        body: JSON.stringify({}),
                    });
                    
                    if (response.ok) {
                        console.log("[TrainerWidget] ✓ Успешный запрос к:", url);
                        break;
                    } else {
                        console.warn("[TrainerWidget] Ошибка HTTP", response.status, "для URL:", url);
                        lastError = new Error(`HTTP ${response.status}`);
                    }
                } catch (err) {
                    console.warn("[TrainerWidget] Ошибка запроса к", url, ":", err);
                    lastError = err;
                    response = null;
                }
            }
            
            if (!response) {
                throw lastError || new Error("Не удалось выполнить запрос ни к одному URL");
            }
            
            if (!response.ok) {
                console.error("[TrainerWidget] HTTP error! status:", response.status);
                this.trainingsWidget.count = 0;
                this.trainingsWidget.visible = false;
                this.trainingsWidget.loading = false;
                this.updateWidgetInDOM();
                return;
            }
            
            const jsonResponse = await response.json();
            console.log("[TrainerWidget] Получен ответ от сервера (полный):", jsonResponse);
            console.log("[TrainerWidget] Тип ответа:", typeof jsonResponse);
            console.log("[TrainerWidget] Ключи ответа:", jsonResponse ? Object.keys(jsonResponse) : 'null');
            
            // Odoo возвращает JSON-RPC формат: { jsonrpc: "2.0", id: null, result: {...} }
            // Нужно извлечь result из ответа
            let result = jsonResponse;
            if (jsonResponse && jsonResponse.result !== undefined) {
                result = jsonResponse.result;
                console.log("[TrainerWidget] ✓ Извлечен result из JSON-RPC:", result);
                console.log("[TrainerWidget] Тип result:", typeof result);
                console.log("[TrainerWidget] Ключи result:", result ? Object.keys(result) : 'null');
            } else {
                console.log("[TrainerWidget] Ответ не содержит result, используем весь ответ как result");
            }
            
            // Проверяем, есть ли ошибка доступа (директор или менеджер)
            if (result && result.error === 'access_denied') {
                console.log("[TrainerWidget] Доступ запрещен:", result.reason);
                this.trainingsWidget.visible = false;
                this.trainingsWidget.loading = false;
                this.trainingsWidget.count = 0;
                this.updateWidgetInDOM();
                return;
            }
            
            // Если ошибка employee_not_found, также скрываем виджет
            if (result && result.error === 'employee_not_found') {
                console.log("[TrainerWidget] Employee не найден для пользователя");
                this.trainingsWidget.visible = false;
                this.trainingsWidget.loading = false;
                this.trainingsWidget.count = 0;
                this.updateWidgetInDOM();
                return;
            }
            
            // Если результат содержит count, значит пользователь тренер
            if (result && typeof result.count !== 'undefined') {
                const count = parseInt(result.count) || 0;
                console.log("[TrainerWidget] ✓✓✓ Установлено количество тренировок:", count);
                this.trainingsWidget.count = count;
                this.trainingsWidget.visible = true;
                this.trainingsWidget.loading = false;
                
                // Сохраняем employee_id для использования при клике
                if (result.employee_id) {
                    this.trainingsWidget.employeeId = result.employee_id;
                    console.log("[TrainerWidget] Employee ID сохранен:", result.employee_id);
                }
                
                // Обновляем виджет в DOM
                this.updateWidgetInDOM();
            } else {
                console.warn("[TrainerWidget] Результат не содержит count. Полный результат:", result);
                console.warn("[TrainerWidget] Тип result:", typeof result);
                console.warn("[TrainerWidget] Ключи result:", result ? Object.keys(result) : 'null');
                this.trainingsWidget.count = 0;
                this.trainingsWidget.visible = false;
                this.trainingsWidget.loading = false;
                this.updateWidgetInDOM();
            }
        } catch (error) {
            console.error("[TrainerWidget] Ошибка при загрузке количества тренировок:", error);
            this.trainingsWidget.count = 0;
            this.trainingsWidget.visible = false;
            this.trainingsWidget.loading = false;
            this.updateWidgetInDOM();
        } finally {
            this.trainingsWidget.loading = false;
        }
    },
});
