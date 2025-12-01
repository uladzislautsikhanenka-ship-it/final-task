/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { FormController } from "@web/views/form/form_controller";

/**
 * Патч для FormController - обновляет таймеры тренировок в реальном времени
 */
patch(FormController.prototype, {
    setup() {
        super.setup();
        this.timerInterval = null;
        this.orm = useService("orm");
        this.stateChangeInProgress = false; // Флаг для предотвращения повторных изменений
        
        // Проверяем, это ли форма training.booking
        if (this.props.resModel === 'training.booking') {
            onMounted(() => {
                this.startTimerUpdates();
            });
            
            onWillUnmount(() => {
                this.stopTimerUpdates();
            });
        }
    },
    
    startTimerUpdates() {
        // Обновляем таймеры каждую секунду для более точного отображения
        this.timerInterval = setInterval(() => {
            this.updateTimers();
        }, 1000); // Каждую секунду
        
        // Первое обновление сразу
        this.updateTimers();
    },
    
    stopTimerUpdates() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    },
    
    async updateTimers() {
        const record = this.model.root;
        if (!record || !record.resId || !record.data) {
            return;
        }
        
        // Проверяем, что запись в статусе confirmed или in_progress
        const state = record.data?.state;
        if (state !== 'confirmed' && state !== 'in_progress') {
            return;
        }
        
        const bookingDate = record.data?.booking_date;
        const startTime = record.data?.start_time;
        const endTime = record.data?.end_time;
        
        if (!bookingDate) {
            return;
        }
        
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const bookingDateObj = new Date(bookingDate);
        bookingDateObj.setHours(0, 0, 0, 0);
        
        // Обновляем таймер до начала для подтвержденных тренировок
        if (state === 'confirmed' && startTime !== undefined && startTime !== null) {
            const startHour = Math.floor(startTime);
            const startMin = Math.round((startTime - startHour) * 60);
            const startDateTime = new Date(bookingDateObj);
            startDateTime.setHours(startHour, startMin, 0, 0);
            
            if (startDateTime > now) {
                const delta = startDateTime - now;
                const totalSeconds = Math.floor(delta / 1000);
                const hours = Math.floor(totalSeconds / 3600);
                const minutes = Math.floor((totalSeconds % 3600) / 60);
                const seconds = totalSeconds % 60;
                
                // Обновляем значение напрямую в DOM для мгновенного отображения
                const hoursStr = String(hours).padStart(2, '0');
                const minutesStr = String(minutes).padStart(2, '0');
                const secondsStr = String(seconds).padStart(2, '0');
                this.updateTimerDisplay('time_until_start', `${hoursStr}:${minutesStr}:${secondsStr}`);
            } else if (!this.stateChangeInProgress) {
                // Время начала наступило - переключаем статус на "в процессе"
                this.updateTimerDisplay('time_until_start', '00:00:00');
                this.stateChangeInProgress = true;
                await this.changeStateToInProgress(record);
                this.stateChangeInProgress = false;
            }
        }
        
        // Обновляем таймер до окончания для тренировок в процессе
        if (state === 'in_progress' && endTime !== undefined && endTime !== null) {
            const endHour = Math.floor(endTime);
            const endMin = Math.round((endTime - endHour) * 60);
            const endDateTime = new Date(bookingDateObj);
            endDateTime.setHours(endHour, endMin, 0, 0);
            
            if (endDateTime > now) {
                const delta = endDateTime - now;
                const totalSeconds = Math.floor(delta / 1000);
                const hours = Math.floor(totalSeconds / 3600);
                const minutes = Math.floor((totalSeconds % 3600) / 60);
                const seconds = totalSeconds % 60;
                
                // Обновляем значение напрямую в DOM для мгновенного отображения
                const hoursStr = String(hours).padStart(2, '0');
                const minutesStr = String(minutes).padStart(2, '0');
                const secondsStr = String(seconds).padStart(2, '0');
                this.updateTimerDisplay('time_until_end', `${hoursStr}:${minutesStr}:${secondsStr}`);
            } else if (!this.stateChangeInProgress) {
                // Время окончания наступило - переключаем статус на "завершена"
                this.updateTimerDisplay('time_until_end', '00:00:00');
                this.stateChangeInProgress = true;
                await this.changeStateToCompleted(record);
                this.stateChangeInProgress = false;
            }
        }
    },
    
    async changeStateToInProgress(record) {
        try {
            // Проверяем текущий статус перед изменением
            if (record.data?.state !== 'confirmed') {
                return;
            }
            
            await this.orm.write(
                'training.booking',
                [record.resId],
                {'state': 'in_progress'}
            );
            // Перезагружаем запись для обновления отображения
            await record.load();
            console.log('[Timer] Статус автоматически изменен на "в процессе"');
        } catch (error) {
            console.error('[Timer] Ошибка при изменении статуса на "в процессе":', error);
            this.stateChangeInProgress = false;
        }
    },
    
    async changeStateToCompleted(record) {
        try {
            // Проверяем текущий статус перед изменением
            if (record.data?.state !== 'in_progress') {
                return;
            }
            
            await this.orm.write(
                'training.booking',
                [record.resId],
                {'state': 'completed'}
            );
            // Перезагружаем запись для обновления отображения
            await record.load();
            console.log('[Timer] Статус автоматически изменен на "завершена"');
        } catch (error) {
            console.error('[Timer] Ошибка при изменении статуса на "завершена":', error);
            this.stateChangeInProgress = false;
        }
    },
    
    updateTimerDisplay(fieldName, value) {
        // Находим поле в DOM и обновляем его значение
        const fieldElement = document.querySelector(`[name="${fieldName}"]`);
        if (fieldElement) {
            const displayElement = fieldElement.querySelector('.o_field_char') || fieldElement;
            if (displayElement) {
                displayElement.textContent = value;
            }
        }
    },
});

