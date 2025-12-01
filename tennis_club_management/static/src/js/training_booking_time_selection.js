/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUpdateProps } from "@odoo/owl";
import { useState } from "@odoo/owl";
import { SelectionField } from "@web/views/fields/selection/selection_field";

/**
 * Патч для SelectionField - обновляет опции available_start_time_selection
 * на основе выбранного тренера, даты и корта
 */
patch(SelectionField.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        
        // Проверяем, это ли поле available_start_time_selection
        const fieldName = this.props.name;
        const resModel = this.props.record?.resModel;
        
        if (fieldName === 'available_start_time_selection' && resModel === 'training.booking') {
            console.log('[TimeSelection] Инициализация поля available_start_time_selection');
            this.isTimeSelectionField = true;
            this.currentTrainerId = null;
            this.currentSportsCenterId = null;
            this.currentBookingDate = null;
            this.currentCourtId = null;
            this.loadedOptionsState = useState({ options: null });
            
            onMounted(() => {
                console.log('[TimeSelection] Компонент смонтирован, загружаем времена');
                this.loadAvailableTimes();
            });
            
            onWillUpdateProps((nextProps) => {
                this.checkFieldsChange(nextProps);
            });
        }
    },
    
    async loadAvailableTimes() {
        const record = this.props.record;
        const trainerId = record?.data?.trainer_id?.[0];
        const sportsCenterId = record?.data?.sports_center_id?.[0];
        // Приоритет отдаем available_booking_date_selection, если оно заполнено
        const bookingDate = record?.data?.available_booking_date_selection || record?.data?.booking_date;
        const courtId = record?.data?.court_id?.[0];
        
        console.log('[TimeSelection] Загрузка времен:', {
            trainerId,
            sportsCenterId,
            bookingDate,
            courtId
        });
        
        if (!trainerId || !sportsCenterId || !bookingDate || !courtId) {
            console.log('[TimeSelection] Не все поля заполнены, очищаем опции');
            this.currentTrainerId = null;
            this.currentSportsCenterId = null;
            this.currentBookingDate = null;
            this.currentCourtId = null;
            if (this.loadedOptionsState) {
                this.loadedOptionsState.options = [];
            }
            return;
        }
        
        // Проверяем, изменились ли параметры
        const paramsChanged = (
            trainerId !== this.currentTrainerId ||
            sportsCenterId !== this.currentSportsCenterId ||
            bookingDate !== this.currentBookingDate ||
            courtId !== this.currentCourtId
        );
        
        if (!paramsChanged && this.loadedOptionsState?.options) {
            return; // Данные уже загружены
        }
        
        try {
            // Конвертируем дату в формат YYYY-MM-DD если нужно
            let dateStr = bookingDate;
            if (bookingDate && typeof bookingDate === 'object') {
                // Если это объект даты
                const year = bookingDate.getFullYear();
                const month = String(bookingDate.getMonth() + 1).padStart(2, '0');
                const day = String(bookingDate.getDate()).padStart(2, '0');
                dateStr = `${year}-${month}-${day}`;
            } else if (bookingDate && typeof bookingDate === 'string' && bookingDate.includes('T')) {
                // Если это ISO строка
                dateStr = bookingDate.split('T')[0];
            }
            
            const availableTimes = await this.orm.call(
                'training.booking',
                'get_available_start_times',
                [],
                {
                    trainer_id: trainerId,
                    sports_center_id: sportsCenterId,
                    booking_date: dateStr,
                    court_id: courtId,
                }
            );
            
            // Формируем опции для Selection поля, исключая прошедшие часы для сегодняшней даты
            const options = [];
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const selectedDate = new Date(dateStr + 'T00:00:00');
            selectedDate.setHours(0, 0, 0, 0);
            const isToday = selectedDate.getTime() === today.getTime();
            const currentHour = isToday ? new Date().getHours() : null;
            
            if (Array.isArray(availableTimes)) {
                for (const timeOption of availableTimes) {
                    let timeValue, timeLabel;
                    
                    if (Array.isArray(timeOption) && timeOption.length >= 2) {
                        timeValue = timeOption[0];
                        timeLabel = timeOption[1];
                    } else if (typeof timeOption === 'object' && timeOption.value !== undefined) {
                        timeValue = timeOption.value;
                        timeLabel = timeOption.label || String(timeOption.value);
                    } else {
                        continue;
                    }
                    
                    // Пропускаем прошедшие часы для сегодняшней даты
                    if (isToday && currentHour !== null) {
                        const hourValue = parseFloat(timeValue);
                        if (!isNaN(hourValue) && hourValue < currentHour) {
                            continue;
                        }
                    }
                    
                    options.push([String(timeValue), timeLabel]);
                }
            }
            
            if (this.loadedOptionsState) {
                this.loadedOptionsState.options = options;
            }
            this.currentTrainerId = trainerId;
            this.currentSportsCenterId = sportsCenterId;
            this.currentBookingDate = bookingDate;
            this.currentCourtId = courtId;
            
            console.log(`[TimeSelection] Загружено ${options.length} доступных часов для тренера ${trainerId} на дату ${dateStr}`, options);
            
        } catch (error) {
            console.error('[TimeSelection] Ошибка при загрузке доступных часов:', error);
            if (this.loadedOptionsState) {
                this.loadedOptionsState.options = [];
            }
        }
    },
    
    checkFieldsChange(nextProps) {
        const record = nextProps.record || this.props.record;
        const trainerId = record?.data?.trainer_id?.[0];
        const sportsCenterId = record?.data?.sports_center_id?.[0];
        // Приоритет отдаем available_booking_date_selection, если оно заполнено
        const bookingDate = record?.data?.available_booking_date_selection || record?.data?.booking_date;
        const courtId = record?.data?.court_id?.[0];
        
        // Нормализуем bookingDate для сравнения
        let normalizedBookingDate = bookingDate;
        if (bookingDate && typeof bookingDate === 'string' && bookingDate.includes('T')) {
            normalizedBookingDate = bookingDate.split('T')[0];
        }
        
        const paramsChanged = (
            trainerId !== this.currentTrainerId ||
            sportsCenterId !== this.currentSportsCenterId ||
            normalizedBookingDate !== this.currentBookingDate ||
            courtId !== this.currentCourtId
        );
        
        if (paramsChanged) {
            this.loadAvailableTimes();
        }
    },
    
    get options() {
        // Переопределяем getter для options, чтобы возвращать загруженные опции
        if (this.isTimeSelectionField && this.loadedOptionsState) {
            // Если опции загружены (даже если это пустой массив), возвращаем их
            if (this.loadedOptionsState.options !== null && this.loadedOptionsState.options !== undefined) {
                // Убеждаемся, что опции в правильном формате
                const options = Array.isArray(this.loadedOptionsState.options) ? this.loadedOptionsState.options : [];
                console.log('[TimeSelection] Возвращаем загруженные опции:', options);
                return options;
            }
            // Если опции еще не загружены (null), возвращаем из field, чтобы показать поле
            const fieldOptions = this.props.field?.selection || super.options || [];
            // Убеждаемся, что это массив
            const result = Array.isArray(fieldOptions) ? fieldOptions : [];
            console.log('[TimeSelection] Опции еще не загружены, возвращаем из field:', result);
            return result;
        }
        const superOptions = super.options || this.props.field?.selection || [];
        return Array.isArray(superOptions) ? superOptions : [];
    },
    
    get string() {
        // Переопределяем getter для string, чтобы безопасно обрабатывать отсутствующие значения
        if (this.isTimeSelectionField) {
            const value = this.props.record?.data?.[this.props.name];
            if (!value) {
                return '';
            }
            const opts = this.options;
            const option = opts.find(opt => opt && opt[0] === value);
            if (option && option[1]) {
                return option[1];
            }
            // Если значение не найдено в опциях, возвращаем само значение
            return String(value);
        }
        return super.string || '';
    },
});

