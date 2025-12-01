/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { useService } from "@web/core/utils/hooks";

/**
 * Патч для CalendarController - добавляем загрузку тренировок в правую панель
 * только для календаря доступности тренера
 */
patch(CalendarController.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        
        // Проверяем, это ли календарь доступности тренера
        this.isTrainerAvailabilityCalendar = this.props.resModel === "trainer.availability";
        
        if (this.isTrainerAvailabilityCalendar) {
            this.loadTrainingsInterval = null;
            this.sidebarCreated = false;
            
            onMounted(() => {
                // Сохраняем список дат с тренировками для подсветки
                this.trainingDatesList = [];
                
                // Скрываем текстовые надписи событий в календаре доступности
                this.hideEventTexts();
                
                // Пробуем создать панель несколько раз с задержками
                const tryCreate = (attempt = 0) => {
                    if (attempt > 10) {
                        console.warn('[TrainerCalendar] Не удалось создать панель после 10 попыток');
                        return;
                    }
                    
                    if (!this.sidebarCreated) {
                        this.createTrainingsSidebar();
                        if (this.sidebarCreated) {
                            this.loadTrainingsData();
                            // Обновляем данные каждые 30 секунд
                            this.loadTrainingsInterval = setInterval(() => {
                                this.loadTrainingsData();
                            }, 30000);
                            
                            // Отслеживаем изменения календаря (переключение месяцев)
                            this.setupCalendarObserver();
                        } else {
                            setTimeout(() => tryCreate(attempt + 1), 300);
                        }
                    }
                };
                
                // Начинаем попытки
                setTimeout(() => tryCreate(), 500);
                
                // Периодически скрываем текстовые надписи и обновляем окраску (на случай динамической загрузки)
                // Используем более частый интервал для надежности
                this.hideTextsInterval = setInterval(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 300);
                
                // Также применяем стили сразу после загрузки и периодически
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 100);
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 500);
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 1000);
                const observer = new MutationObserver(() => {
                    if (!this.sidebarCreated) {
                        this.createTrainingsSidebar();
                        if (this.sidebarCreated) {
                            this.loadTrainingsData();
                            this.setupCalendarObserver();
                            observer.disconnect();
                        }
                    }
                });
                
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
                setTimeout(() => observer.disconnect(), 10000);
            });
            
            onWillUnmount(() => {
                if (this.loadTrainingsInterval) {
                    clearInterval(this.loadTrainingsInterval);
                }
                if (this.hideTextsInterval) {
                    clearInterval(this.hideTextsInterval);
                }
                if (this.calendarObserver) {
                    this.calendarObserver.disconnect();
                    this.calendarObserver = null;
                }
                if (this.calendarNavigationHandler) {
                    document.removeEventListener('click', this.calendarNavigationHandler);
                    this.calendarNavigationHandler = null;
                }
                // Удаляем правую панель при размонтировании
                this.removeTrainingsSidebar();
            });
        }
    },
    
    /**
     * Создает правую панель с тренировками
     */
    createTrainingsSidebar() {
        if (this.sidebarCreated) {
            return;
        }
        
        // Пробуем разные селекторы для поиска контейнера календаря
        let calendarContainer = document.querySelector('.o_view_manager_content');
        if (!calendarContainer) {
            calendarContainer = document.querySelector('.o_content');
        }
        if (!calendarContainer) {
            calendarContainer = document.querySelector('.o_action_manager');
        }
        if (!calendarContainer) {
            console.warn('[TrainerCalendar] Не найден контейнер календаря');
            return;
        }
        
        // Ищем календарь - пробуем разные варианты
        let calendarView = calendarContainer.querySelector('.o_calendar_view');
        if (!calendarView) {
            calendarView = calendarContainer.querySelector('[class*="Calendar"]');
        }
        if (!calendarView) {
            calendarView = calendarContainer.querySelector('.o_calendar_container');
        }
        if (!calendarView) {
            // Ищем по структуре - календарь обычно в div с классом содержащим calendar
            const allDivs = calendarContainer.querySelectorAll('div');
            for (const div of allDivs) {
                if (div.className && (div.className.includes('calendar') || div.className.includes('Calendar'))) {
                    calendarView = div;
                    break;
                }
            }
        }
        
        if (!calendarView) {
            console.warn('[TrainerCalendar] Не найден элемент календаря, пробуем добавить панель в контейнер');
            // Если не нашли календарь, просто добавляем панель справа от контейнера
            this.addSidebarToContainer(calendarContainer);
            return;
        }
        
        // Проверяем, не создана ли уже обертка
        let wrapper = calendarView.closest('.o_trainer_availability_calendar_wrapper');
        if (!wrapper) {
            // Создаем обертку для календаря и панели
            wrapper = document.createElement('div');
            wrapper.className = 'o_trainer_availability_calendar_wrapper';
            
            // Обертываем календарь
            const calendarParent = calendarView.parentElement;
            calendarParent.insertBefore(wrapper, calendarView);
            wrapper.appendChild(calendarView);
        }
        
        // Создаем контейнер для календаря, если его нет
        let calendarDiv = wrapper.querySelector('.o_calendar_container');
        if (!calendarDiv) {
            calendarDiv = document.createElement('div');
            calendarDiv.className = 'o_calendar_container';
            wrapper.insertBefore(calendarDiv, calendarView);
            calendarDiv.appendChild(calendarView);
        }
        
        // Проверяем, не создана ли уже панель
        let sidebarContainer = wrapper.querySelector('.o_trainings_sidebar_container');
        if (sidebarContainer) {
            this.sidebarCreated = true;
            return;
        }
        
        // Создаем правую панель
        sidebarContainer = document.createElement('div');
        sidebarContainer.className = 'o_trainings_sidebar_container';
        wrapper.appendChild(sidebarContainer);
        
        const sidebar = document.createElement('div');
        sidebar.className = 'o_trainer_trainings_sidebar';
        sidebarContainer.appendChild(sidebar);
        
        // Добавляем заголовок
        const header = document.createElement('div');
        header.className = 'o_trainer_trainings_header';
        header.innerHTML = '<h3><i class="fa fa-dumbbell"/> Мои тренировки</h3>';
        sidebar.appendChild(header);
        
        // Секция "Сегодня"
        const todaySection = document.createElement('div');
        todaySection.className = 'o_trainings_today_section';
        todaySection.innerHTML = `
            <h4 class="o_section_title"><i class="fa fa-calendar-day"/> Сегодня</h4>
            <div class="o_trainings_list_today"></div>
            <div class="o_no_trainings_today" style="display: none;">
                <p class="text-muted">Нет тренировок на сегодня</p>
            </div>
        `;
        sidebar.appendChild(todaySection);
        
        // Секция "Ближайшие"
        const upcomingSection = document.createElement('div');
        upcomingSection.className = 'o_trainings_upcoming_section';
        upcomingSection.innerHTML = `
            <h4 class="o_section_title"><i class="fa fa-calendar-alt"/> Ближайшие</h4>
            <div class="o_trainings_list_upcoming"></div>
            <div class="o_no_trainings_upcoming" style="display: none;">
                <p class="text-muted">Нет будущих тренировок</p>
            </div>
        `;
        sidebar.appendChild(upcomingSection);
        
        // Индикатор загрузки - скрываем сразу, показываем только при загрузке
        const loading = document.createElement('div');
        loading.className = 'o_loading_trainings';
        loading.innerHTML = '<i class="fa fa-spinner fa-spin"/> Загрузка...';
        loading.style.display = 'none'; // Скрываем сразу
        sidebar.appendChild(loading);
        
        this.sidebarCreated = true;
        console.log('[TrainerCalendar] Правая панель создана');
    },
    
    /**
     * Добавляет панель прямо в контейнер, если календарь не найден
     */
    addSidebarToContainer(container) {
        // Проверяем, не создана ли уже панель
        if (container.querySelector('.o_trainings_sidebar_container')) {
            this.sidebarCreated = true;
            return;
        }
        
        // Создаем обертку
        const wrapper = document.createElement('div');
        wrapper.className = 'o_trainer_availability_calendar_wrapper';
        wrapper.style.display = 'flex';
        wrapper.style.flexDirection = 'row';
        
        // Находим основной контент и оборачиваем его
        const mainContent = container.querySelector('.o_view_manager_content, .o_content > div:first-child') || container.firstElementChild;
        if (mainContent) {
            const calendarDiv = document.createElement('div');
            calendarDiv.className = 'o_calendar_container';
            calendarDiv.style.flex = '1';
            calendarDiv.appendChild(mainContent.cloneNode(true));
            wrapper.appendChild(calendarDiv);
        }
        
        // Создаем правую панель
        const sidebarContainer = document.createElement('div');
        sidebarContainer.className = 'o_trainings_sidebar_container';
        wrapper.appendChild(sidebarContainer);
        
        const sidebar = document.createElement('div');
        sidebar.className = 'o_trainer_trainings_sidebar';
        sidebarContainer.appendChild(sidebar);
        
        // Добавляем заголовок и секции (код такой же как выше)
        const header = document.createElement('div');
        header.className = 'o_trainer_trainings_header';
        header.innerHTML = '<h3><i class="fa fa-dumbbell"/> Мои тренировки</h3>';
        sidebar.appendChild(header);
        
        const todaySection = document.createElement('div');
        todaySection.className = 'o_trainings_today_section';
        todaySection.innerHTML = `
            <h4 class="o_section_title"><i class="fa fa-calendar-day"/> Сегодня</h4>
            <div class="o_trainings_list_today"></div>
            <div class="o_no_trainings_today" style="display: none;">
                <p class="text-muted">Нет тренировок на сегодня</p>
            </div>
        `;
        sidebar.appendChild(todaySection);
        
        const upcomingSection = document.createElement('div');
        upcomingSection.className = 'o_trainings_upcoming_section';
        upcomingSection.innerHTML = `
            <h4 class="o_section_title"><i class="fa fa-calendar-alt"/> Ближайшие</h4>
            <div class="o_trainings_list_upcoming"></div>
            <div class="o_no_trainings_upcoming" style="display: none;">
                <p class="text-muted">Нет будущих тренировок</p>
            </div>
        `;
        sidebar.appendChild(upcomingSection);
        
        const loading = document.createElement('div');
        loading.className = 'o_loading_trainings';
        loading.innerHTML = '<i class="fa fa-spinner fa-spin"/> Загрузка...';
        sidebar.appendChild(loading);
        
        container.appendChild(wrapper);
        this.sidebarCreated = true;
    },
    
    /**
     * Удаляет правую панель
     */
    removeTrainingsSidebar() {
        const wrapper = document.querySelector('.o_trainer_availability_calendar_wrapper');
        if (wrapper) {
            const calendarView = wrapper.querySelector('.o_calendar_view, [class*="calendar"]');
            if (calendarView) {
                const parent = wrapper.parentElement;
                parent.insertBefore(calendarView, wrapper);
                wrapper.remove();
            }
        }
        this.sidebarCreated = false;
    },
    
    /**
     * Загружает данные о тренировках тренера и отображает их в правой панели
     */
    async loadTrainingsData() {
        if (!this.isTrainerAvailabilityCalendar) {
            return;
        }
        
        // Показываем индикатор загрузки
        const sidebar = document.querySelector('.o_trainer_trainings_sidebar');
        if (sidebar) {
            const loading = sidebar.querySelector('.o_loading_trainings');
            if (loading) {
                loading.style.display = 'block';
            }
        }
        
        try {
            console.log('[TrainerCalendar] Загружаем тренировки через контроллер...');
            
            // Используем контроллер, который сам найдет employee для текущего пользователя
            // (та же логика, что и в виджете заголовка)
            const urls = [
                "/tennis_club/get_trainer_trainings",
                "/odoo/tennis_club/get_trainer_trainings",
            ];
            
            let response = null;
            let lastError = null;
            
            for (const url of urls) {
                try {
                    console.log('[TrainerCalendar] Пробуем URL:', url);
                    response = await fetch(url, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        credentials: "same-origin",
                        body: JSON.stringify({}),
                    });
                    
                    if (response.ok) {
                        console.log('[TrainerCalendar] ✓ Успешный запрос к:', url);
                        break;
                    } else {
                        console.warn('[TrainerCalendar] Ошибка HTTP', response.status, "для URL:", url);
                        lastError = new Error(`HTTP ${response.status}`);
                    }
                } catch (err) {
                    console.warn('[TrainerCalendar] Ошибка запроса к', url, ':', err);
                    lastError = err;
                }
            }
            
            if (!response || !response.ok) {
                console.error('[TrainerCalendar] Не удалось получить данные о тренировках:', lastError);
                this.hideLoading();
                const sidebar = document.querySelector('.o_trainer_trainings_sidebar');
                if (sidebar) {
                    const noToday = sidebar.querySelector('.o_no_trainings_today');
                    const noUpcoming = sidebar.querySelector('.o_no_trainings_upcoming');
                    if (noToday) noToday.style.display = 'block';
                    if (noUpcoming) noUpcoming.style.display = 'block';
                }
                return;
            }
            
            const jsonResponse = await response.json();
            console.log('[TrainerCalendar] Получен ответ от сервера (полный):', jsonResponse);
            console.log('[TrainerCalendar] Тип ответа:', typeof jsonResponse);
            console.log('[TrainerCalendar] Ключи ответа:', jsonResponse ? Object.keys(jsonResponse) : 'null');
            
            // Odoo возвращает JSON-RPC формат: { jsonrpc: "2.0", id: null, result: {...} }
            // Нужно извлечь result из ответа (как в виджете заголовка)
            let trainings = jsonResponse;
            if (jsonResponse && jsonResponse.result !== undefined) {
                trainings = jsonResponse.result;
                console.log('[TrainerCalendar] ✓ Извлечен result из JSON-RPC:', trainings);
                console.log('[TrainerCalendar] Тип result:', typeof trainings);
                console.log('[TrainerCalendar] Ключи result:', trainings ? Object.keys(trainings) : 'null');
            } else {
                console.log('[TrainerCalendar] Ответ не содержит result, используем весь ответ как result');
            }
            
            if (!trainings) {
                console.error('[TrainerCalendar] Данные о тренировках отсутствуют');
                this.hideLoading();
                const sidebar = document.querySelector('.o_trainer_trainings_sidebar');
                if (sidebar) {
                    const noToday = sidebar.querySelector('.o_no_trainings_today');
                    const noUpcoming = sidebar.querySelector('.o_no_trainings_upcoming');
                    if (noToday) noToday.style.display = 'block';
                    if (noUpcoming) noUpcoming.style.display = 'block';
                }
                return;
            }
            
            if (trainings.error) {
                console.warn('[TrainerCalendar] Ошибка от контроллера:', trainings.error);
                this.hideLoading();
                const sidebar = document.querySelector('.o_trainer_trainings_sidebar');
                if (sidebar) {
                    const noToday = sidebar.querySelector('.o_no_trainings_today');
                    const noUpcoming = sidebar.querySelector('.o_no_trainings_upcoming');
                    if (noToday) noToday.style.display = 'block';
                    if (noUpcoming) noUpcoming.style.display = 'block';
                }
                return;
            }
            
            // Проверяем структуру данных
            const todayTrainings = trainings.today || [];
            const upcomingTrainings = trainings.upcoming || [];
            console.log('[TrainerCalendar] Сегодняшних тренировок:', todayTrainings.length);
            console.log('[TrainerCalendar] Будущих тренировок:', upcomingTrainings.length);
            
            if (todayTrainings.length > 0) {
                console.log('[TrainerCalendar] Первая сегодняшняя тренировка:', todayTrainings[0]);
            }
            if (upcomingTrainings.length > 0) {
                console.log('[TrainerCalendar] Первая будущая тренировка:', upcomingTrainings[0]);
            }
            
            this.renderTrainings(trainings);
        } catch (error) {
            console.error("[TrainerCalendar] Ошибка загрузки тренировок:", error);
            this.hideLoading();
            // Показываем сообщения "Нет тренировок" при ошибке
            const sidebar = document.querySelector('.o_trainer_trainings_sidebar');
            if (sidebar) {
                const noToday = sidebar.querySelector('.o_no_trainings_today');
                const noUpcoming = sidebar.querySelector('.o_no_trainings_upcoming');
                if (noToday) noToday.style.display = 'block';
                if (noUpcoming) noUpcoming.style.display = 'block';
            }
        }
    },
    
    /**
     * Отображает тренировки в правой панели
     */
    renderTrainings(trainings) {
        const sidebar = document.querySelector('.o_trainer_trainings_sidebar');
        if (!sidebar) {
            return;
        }
        
        const todayList = sidebar.querySelector('.o_trainings_list_today');
        const upcomingList = sidebar.querySelector('.o_trainings_list_upcoming');
        const noToday = sidebar.querySelector('.o_no_trainings_today');
        const noUpcoming = sidebar.querySelector('.o_no_trainings_upcoming');
        const loading = sidebar.querySelector('.o_loading_trainings');
        
        // Скрываем индикатор загрузки
        if (loading) {
            loading.style.display = 'none';
        }
        
        // Очищаем списки
        if (todayList) {
            todayList.innerHTML = '';
        }
        if (upcomingList) {
            upcomingList.innerHTML = '';
        }
        
        // Отображаем тренировки на сегодня
        const todayTrainings = trainings.today || [];
        if (todayTrainings.length > 0) {
            if (noToday) noToday.style.display = 'none';
            if (todayList) {
                todayTrainings.forEach(training => {
                    todayList.appendChild(this.createTrainingCard(training, true));
                });
            }
        } else {
            if (noToday) noToday.style.display = 'block';
        }
        
        // Отображаем будущие тренировки
        const upcomingTrainings = trainings.upcoming || [];
        if (upcomingTrainings.length > 0) {
            if (noUpcoming) noUpcoming.style.display = 'none';
            if (upcomingList) {
                upcomingTrainings.forEach(training => {
                    upcomingList.appendChild(this.createTrainingCard(training, false));
                });
            }
        } else {
            if (noUpcoming) noUpcoming.style.display = 'block';
        }
        
        // Сохраняем список дат для подсветки
        this.trainingDatesList = trainings.training_dates || [];
        
        // Подсвечиваем даты с тренировками в календаре
        if (this.trainingDatesList.length > 0) {
            setTimeout(() => {
                this.highlightTrainingDates(this.trainingDatesList);
            }, 300);
        }
    },
    
    /**
     * Настраивает наблюдатель за изменениями календаря для обновления подсветки
     */
    setupCalendarObserver() {
        if (this.calendarObserver) {
            this.calendarObserver.disconnect();
        }
        
        const calendarContainer = document.querySelector('.o_calendar_view, .o_calendar_container, [class*="calendar"]');
        if (!calendarContainer) {
            return;
        }
        
        this.calendarObserver = new MutationObserver((mutations) => {
            // При изменении календаря скрываем текстовые надписи и обновляем подсветку
            if (this.isTrainerAvailabilityCalendar) {
                // Проверяем, были ли изменения в структуре календаря
                const hasRelevantChanges = mutations.some(mutation => {
                    return mutation.type === 'childList' || 
                           (mutation.type === 'attributes' && mutation.attributeName === 'class');
                });
                
                if (hasRelevantChanges) {
                    // Применяем стили несколько раз с разными задержками для надежности
                    setTimeout(() => {
                        this.hideEventTexts();
                    }, 50);
                    setTimeout(() => {
                        this.hideEventTexts();
                    }, 200);
                    setTimeout(() => {
                        this.hideEventTexts();
                    }, 500);
                } else {
                    // Для других изменений применяем один раз
                    setTimeout(() => {
                        this.hideEventTexts();
                    }, 100);
                }
            }
            if (this.trainingDatesList && this.trainingDatesList.length > 0) {
                setTimeout(() => {
                    this.highlightTrainingDates(this.trainingDatesList);
                }, 200);
            }
        });
        
        this.calendarObserver.observe(calendarContainer, {
            childList: true,
            subtree: true,
            attributes: true
        });
        
                // Также отслеживаем клики по навигации календаря
        const handleCalendarNavigation = (e) => {
            const target = e.target;
            if (target.closest('.o_calendar_prev, .o_calendar_next, .fc-prev-button, .fc-next-button, [class*="prev"], [class*="next"], .fc-toolbar-button, .fc-button')) {
                // Вызываем несколько раз с задержками для надежности
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                    if (this.trainingDatesList && this.trainingDatesList.length > 0) {
                        this.highlightTrainingDates(this.trainingDatesList);
                    }
                }, 200);
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 500);
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 1000);
                setTimeout(() => {
                    if (this.isTrainerAvailabilityCalendar) {
                        this.hideEventTexts();
                    }
                }, 1500);
            }
        };
        
        document.addEventListener('click', handleCalendarNavigation);
        
        // Сохраняем обработчик для последующего удаления
        this.calendarNavigationHandler = handleCalendarNavigation;
    },
    
    /**
     * Подсвечивает даты с тренировками в календаре зеленоватым фоном
     */
    highlightTrainingDates(trainingDates) {
        // Убираем предыдущую подсветку
        const previousHighlighted = document.querySelectorAll('.o_calendar_day_with_training');
        previousHighlighted.forEach(el => {
            el.classList.remove('o_calendar_day_with_training');
        });
        
        // Подсвечиваем новые даты
        trainingDates.forEach(dateStr => {
            // Парсим дату в формате 'YYYY-MM-DD'
            const date = new Date(dateStr + 'T00:00:00');
            const day = date.getDate();
            const month = date.getMonth();
            const year = date.getFullYear();
            
            // Ищем ячейки календаря с этой датой
            // В Odoo календаре даты обычно имеют атрибут data-date или содержат число дня
            const calendarCells = document.querySelectorAll('.o_calendar_cell, .fc-day, [class*="calendar-day"], .o_calendar_view td, .o_calendar_view .fc-daygrid-day');
            
            calendarCells.forEach(cell => {
                // Проверяем разные способы определения даты в ячейке
                const cellDate = cell.getAttribute('data-date');
                const cellText = cell.textContent.trim();
                const cellDay = parseInt(cellText);
                
                // Проверяем по data-date атрибуту
                if (cellDate) {
                    const cellDateObj = new Date(cellDate + 'T00:00:00');
                    if (cellDateObj.getDate() === day && 
                        cellDateObj.getMonth() === month && 
                        cellDateObj.getFullYear() === year) {
                        cell.classList.add('o_calendar_day_with_training');
                        return;
                    }
                }
                
                // Проверяем по тексту (число дня)
                if (!isNaN(cellDay) && cellDay === day) {
                    // Дополнительно проверяем, что это правильный месяц
                    // Ищем родительский элемент с информацией о месяце
                    const monthIndicator = cell.closest('[class*="month"], [class*="Month"]');
                    if (monthIndicator || cell.closest('.o_calendar_view')) {
                        // Проверяем, что ячейка не из другого месяца (обычно серые)
                        const isOtherMonth = cell.classList.contains('fc-day-other') || 
                                           cell.classList.contains('o_calendar_day_other') ||
                                           window.getComputedStyle(cell).color.includes('rgb(128');
                        
                        if (!isOtherMonth) {
                            cell.classList.add('o_calendar_day_with_training');
                        }
                    }
                }
            });
        });
        
        // Также пробуем найти по более специфичным селекторам Odoo
        setTimeout(() => {
            trainingDates.forEach(dateStr => {
                const date = new Date(dateStr + 'T00:00:00');
                const day = date.getDate();
                
                // Ищем все элементы, которые могут быть днями календаря
                const allPossibleCells = document.querySelectorAll(
                    '.o_calendar_view td, ' +
                    '.fc-daygrid-day, ' +
                    '[class*="day"], ' +
                    '.o_calendar_cell'
                );
                
                allPossibleCells.forEach(cell => {
                    const text = cell.textContent.trim();
                    const cellDay = parseInt(text);
                    
                    if (cellDay === day && text.length <= 2) {
                        // Проверяем, что это не заголовок или другой элемент
                        const isHeader = cell.tagName === 'TH' || 
                                        cell.classList.contains('fc-col-header-cell') ||
                                        cell.closest('thead');
                        
                        if (!isHeader) {
                            // Проверяем, что это не из другого месяца
                            const isOtherMonth = cell.classList.contains('fc-day-other') ||
                                               window.getComputedStyle(cell).opacity < '0.5';
                            
                            if (!isOtherMonth) {
                                cell.classList.add('o_calendar_day_with_training');
                            }
                        }
                    }
                });
            });
        }, 500);
    },
    
    /**
     * Создает карточку тренировки с четким и структурированным отображением
     */
    createTrainingCard(training, isToday) {
        const card = document.createElement('div');
        card.className = `o_training_card ${isToday ? 'o_training_today' : 'o_training_upcoming'}`;
        card.dataset.bookingId = training.id;
        if (training.group_id) {
            card.dataset.groupId = training.group_id;
        }
        card.style.cursor = 'pointer';
        
        // Определяем подсказку и обработчик в зависимости от типа тренировки
        // Для групповых тренировок убираем возможность открыть карточку группы
        // Тренер видит только список участников
        if (training.is_group_training && training.group_id) {
            // Для групповых тренировок не делаем карточку кликабельной
            card.style.cursor = 'default';
        } else {
            card.title = 'Нажмите для просмотра деталей тренировки';
            card.addEventListener('click', (e) => {
                e.stopPropagation();
                this.openTrainingForm(training.id);
            });
        }
        
        // Экранируем HTML для безопасности
        const escapeHtml = (text) => {
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        };
        
        let html = '';
        
        // Дата (для всех тренировок, но для сегодня можно показать "Сегодня")
        if (isToday) {
            html += `<div class="o_training_date">
                <i class="fa fa-calendar"/> <strong>Сегодня</strong>
            </div>`;
        } else {
            html += `<div class="o_training_date">
                <i class="fa fa-calendar"/> ${escapeHtml(training.date_display || '')}
            </div>`;
        }
        
        // Время тренировки
        html += `<div class="o_training_time">
            <i class="fa fa-clock-o"/> 
            <strong>${escapeHtml(training.start_time || '')} - ${escapeHtml(training.end_time || '')}</strong>
        </div>`;
        
        // Разделитель
        html += `<div class="o_training_divider"></div>`;
        
        // Спортивный центр (без иконки)
        html += `<div class="o_training_field">
            <span class="o_field_label">Спортивный центр:</span>
            <span class="o_field_value">${escapeHtml(training.sports_center || 'Не указан')}</span>
        </div>`;
        
        // Корт (без иконки)
        html += `<div class="o_training_field">
            <span class="o_field_label">Корт:</span>
            <span class="o_field_value">${escapeHtml(training.court || 'Не указан')}</span>
        </div>`;
        
        // Для групповых тренировок показываем название группы
        if (training.is_group_training && training.group_name) {
            html += `<div class="o_training_field" style="background-color: #e7f3ff; padding: 8px; border-radius: 4px; margin: 5px 0;">
                <span class="o_field_label"><i class="fa fa-users"/> Группа:</span>
                <span class="o_field_value" style="font-weight: bold; color: #0066cc;">${escapeHtml(training.group_name)}</span>
            </div>`;
        }
        
        // Клиенты/Участники (без иконки)
        // Для групповых тренировок показываем всех участников из группы
        const participantCount = training.participant_count || 1;
        const participantLabel = participantCount > 1 ? 'Участники' : 'Клиент';
        html += `<div class="o_training_field">
            <span class="o_field_label">${participantLabel}:</span>
            <span class="o_field_value">${escapeHtml(training.customer || 'Не указан')}${participantCount > 1 ? ` (${participantCount} чел.)` : ''}</span>
        </div>`;
        
        // Программа (тип тренировки) (без иконки)
        html += `<div class="o_training_field">
            <span class="o_field_label">Программа:</span>
            <span class="o_field_value">${escapeHtml(training.training_type || 'Не указан')}</span>
        </div>`;
        
        // Разделитель перед статусом
        html += `<div class="o_training_divider"></div>`;
        
        // Статус
        html += `<div class="o_training_state">
            <span class="badge badge-${this.getStateBadgeClass(training.state)}">
                ${escapeHtml(training.state_display || '')}
            </span>
        </div>`;
        
        card.innerHTML = html;
        return card;
    },
    
    /**
     * Возвращает класс для бейджа статуса
     */
    getStateBadgeClass(state) {
        const stateClasses = {
            'confirmed': 'success',
            'in_progress': 'warning',
            'draft': 'secondary',
            'completed': 'info',
            'cancelled': 'danger'
        };
        return stateClasses[state] || 'secondary';
    },
    
    /**
     * Открывает форму тренировки
     */
    openTrainingForm(bookingId) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'training.booking',
            res_id: bookingId,
            views: [[false, 'form']],
            target: 'current',
        });
    },
    
    
    /**
     * Скрывает индикатор загрузки
     */
    hideLoading() {
        const loading = document.querySelector('.o_loading_trainings');
        if (loading) {
            loading.style.display = 'none';
        }
    },
    
    /**
     * Скрывает текстовые надписи событий в календаре доступности
     * Оставляет только зеленоватый цвет для дней, когда тренер работает
     */
    hideEventTexts() {
        if (!this.isTrainerAvailabilityCalendar) {
            return;
        }
        
        // Находим контейнер календаря доступности
        const calendarContainer = document.querySelector('.o_calendar_view, .fc-view-harness, [class*="calendar"]');
        if (!calendarContainer) {
            return;
        }
        
        // Сначала убираем предыдущую окраску только у ячеек, которые больше не содержат событий
        const allCells = document.querySelectorAll(
            '.fc-daygrid-day, .fc-timegrid-col, .o_calendar_cell, .fc-day, td[class*="day"], .o_calendar_view td'
        );
        allCells.forEach(cell => {
            // Проверяем, есть ли еще события в ячейке
            const hasEvents = cell.querySelectorAll('.fc-event, .fc-daygrid-event, .fc-timegrid-event, .o_calendar_event').length > 0;
            if (cell.classList.contains('o_calendar_day_with_availability') && !hasEvents) {
                // Убираем окраску только если событий больше нет
                cell.classList.remove('o_calendar_day_with_availability');
                cell.style.removeProperty('background-color');
                cell.style.removeProperty('background');
                cell.style.removeProperty('border-radius');
            }
        });
        
        // Ищем все события в календаре доступности
        const events = calendarContainer.querySelectorAll(
            '.fc-event, .fc-daygrid-event, .fc-timegrid-event, .o_calendar_event, .fc-list-event'
        );
        
        // Собираем уникальные ячейки с событиями для последующей окраски
        const cellsWithAvailability = new Set();
        
        events.forEach(event => {
            // Скрываем текстовые элементы внутри события
            const textElements = event.querySelectorAll(
                '.fc-event-title, .fc-event-title-container, .fc-list-event-title, ' +
                '.fc-event-main-frame, .fc-event-main, .fc-event-time, ' +
                '.fc-sticky, .fc-event-title.fc-sticky, .fc-event-main-frame > *, ' +
                'span, div, p, a'
            );
            
            textElements.forEach(el => {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
                el.style.opacity = '0';
                el.style.height = '0';
                el.style.width = '0';
                el.style.overflow = 'hidden';
                el.style.fontSize = '0';
                el.style.lineHeight = '0';
                el.style.padding = '0';
                el.style.margin = '0';
                el.textContent = '';
            });
            
            // Полностью скрываем событие
            event.style.display = 'none';
            event.style.visibility = 'hidden';
            event.style.opacity = '0';
            event.style.height = '0';
            event.style.minHeight = '0';
            event.style.width = '0';
            event.style.padding = '0';
            event.style.margin = '0';
            event.style.overflow = 'hidden';
            event.style.borderRadius = '0';
            event.style.border = 'none';
            event.style.fontSize = '0';
            event.style.lineHeight = '0';
            event.textContent = '';
            
            // Скрываем все дочерние элементы с текстом
            const allChildren = event.querySelectorAll('*');
            allChildren.forEach(child => {
                child.style.display = 'none';
                child.style.visibility = 'hidden';
                child.style.opacity = '0';
                child.style.height = '0';
                child.style.width = '0';
                child.style.overflow = 'hidden';
                child.textContent = '';
            });
            
            // Находим родительскую ячейку календаря для этого события
            let parentCell = event.closest('.fc-daygrid-day, .fc-timegrid-col, .o_calendar_cell, .fc-day, td[class*="day"]');
            if (!parentCell) {
                // Пробуем найти через другие селекторы
                parentCell = event.parentElement;
                while (parentCell && parentCell !== calendarContainer) {
                    if (parentCell.classList.contains('fc-daygrid-day') || 
                        parentCell.classList.contains('fc-timegrid-col') ||
                        parentCell.classList.contains('o_calendar_cell') ||
                        parentCell.classList.contains('fc-day') ||
                        (parentCell.tagName === 'TD' && parentCell.className.includes('day'))) {
                        break;
                    }
                    parentCell = parentCell.parentElement;
                }
            }
            
            if (parentCell && parentCell !== calendarContainer) {
                cellsWithAvailability.add(parentCell);
            }
        });
        
        // Теперь окрашиваем все ячейки с событиями доступности
        cellsWithAvailability.forEach(cell => {
            // Проверяем, что это ячейка с датой (не заголовок)
            const cellNumber = cell.querySelector('.fc-daygrid-day-number, .o_calendar_day_number, [class*="day-number"]');
            const isHeader = cell.tagName === 'TH' || 
                           cell.closest('thead') || 
                           cell.classList.contains('fc-col-header-cell') ||
                           cell.classList.contains('fc-col-header');
            
            // Проверяем, что ячейка в текущем месяце (не из другого месяца)
            const isOtherMonth = cell.classList.contains('fc-day-other') || 
                               cell.classList.contains('fc-day-past') ||
                               cell.classList.contains('fc-day-future') ||
                               (window.getComputedStyle(cell).opacity && parseFloat(window.getComputedStyle(cell).opacity) < 0.5);
            
            if (!isHeader && !isOtherMonth) {
                // Окрашиваем всю ячейку в зеленоватый цвет с использованием setAttribute для надежности
                cell.classList.add('o_calendar_day_with_availability');
                
                // Применяем стили через setProperty с important для максимального приоритета
                cell.style.setProperty('background-color', '#d4edda', 'important');
                cell.style.setProperty('background', 'linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%)', 'important');
                cell.style.setProperty('border-radius', '4px', 'important');
                
                // Также устанавливаем через setAttribute для дополнительной надежности
                const existingStyle = cell.getAttribute('style') || '';
                if (!existingStyle.includes('background-color: #d4edda')) {
                    cell.setAttribute('style', 
                        existingStyle + 
                        'background-color: #d4edda !important; ' +
                        'background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important; ' +
                        'border-radius: 4px !important;'
                    );
                }
            }
        });
        
        // Дополнительно: ищем ячейки по data-date атрибуту, если он есть
        const cellsByDate = calendarContainer.querySelectorAll('[data-date]');
        cellsByDate.forEach(cell => {
            const cellEvents = cell.querySelectorAll('.fc-event, .fc-daygrid-event, .fc-timegrid-event, .o_calendar_event');
            if (cellEvents.length > 0) {
                const isHeader = cell.tagName === 'TH' || 
                               cell.closest('thead') || 
                               cell.classList.contains('fc-col-header-cell');
                const isOtherMonth = cell.classList.contains('fc-day-other');
                
                if (!isHeader && !isOtherMonth) {
                    cell.setAttribute('style', 
                        'background-color: #d4edda !important; ' +
                        'background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important; ' +
                        'border-radius: 4px !important;'
                    );
                    cell.style.setProperty('background-color', '#d4edda', 'important');
                    cell.style.setProperty('background', 'linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%)', 'important');
                    cell.style.setProperty('border-radius', '4px', 'important');
                    cell.classList.add('o_calendar_day_with_availability');
                }
            }
        });
        
        // Дополнительная проверка: ищем все ячейки, которые содержат события, даже если они были пропущены
        setTimeout(() => {
            const allDayCells = calendarContainer.querySelectorAll(
                '.fc-daygrid-day:not(.fc-day-other), .fc-timegrid-col, .o_calendar_cell, .fc-day:not(.fc-day-other)'
            );
            allDayCells.forEach(cell => {
                const hasEvents = cell.querySelectorAll('.fc-event, .fc-daygrid-event, .fc-timegrid-event, .o_calendar_event').length > 0;
                if (hasEvents && !cell.classList.contains('o_calendar_day_with_availability')) {
                    const isHeader = cell.tagName === 'TH' || 
                                   cell.closest('thead') || 
                                   cell.classList.contains('fc-col-header-cell');
                    if (!isHeader) {
                        cell.setAttribute('style', 
                            'background-color: #d4edda !important; ' +
                            'background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important; ' +
                            'border-radius: 4px !important;'
                        );
                        cell.style.setProperty('background-color', '#d4edda', 'important');
                        cell.style.setProperty('background', 'linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%)', 'important');
                        cell.style.setProperty('border-radius', '4px', 'important');
                        cell.classList.add('o_calendar_day_with_availability');
                    }
                }
            });
        }, 100);
    }
});

