/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUpdateProps } from "@odoo/owl";
import { useState } from "@odoo/owl";
import { SelectionField } from "@web/views/fields/selection/selection_field";

/**
 * Патч для SelectionField - обновляет опции available_booking_date_selection
 * на основе выбранного тренера
 */
patch(SelectionField.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        
        // Проверяем, это ли поле available_booking_date_selection
        const fieldName = this.props.name;
        const resModel = this.props.record?.resModel;
        
        if (fieldName === 'available_booking_date_selection' && resModel === 'training.booking') {
            this.isDateSelectionField = true;
            this.currentTrainerId = null;
            this.currentSportsCenterId = null;
            this.loadedOptionsState = useState({ options: null });
            
            onMounted(() => {
                this.loadAvailableDates();
            });
            
            onWillUpdateProps((nextProps) => {
                this.checkTrainerChange(nextProps);
            });
        }
    },
    
    async loadAvailableDates() {
        const record = this.props.record;
        const trainerId = record?.data?.trainer_id?.[0];
        const sportsCenterId = record?.data?.sports_center_id?.[0];
        
        if (!trainerId || !sportsCenterId) {
            this.currentTrainerId = null;
            this.currentSportsCenterId = null;
            if (this.loadedOptionsState) {
                this.loadedOptionsState.options = [];
            }
            return;
        }
        
        if (trainerId === this.currentTrainerId && sportsCenterId === this.currentSportsCenterId && this.loadedOptionsState?.options) {
            return; // Данные уже загружены
        }
        
        try {
            const today = new Date();
            // Устанавливаем начало с сегодняшнего дня, а не с начала месяца
            today.setHours(0, 0, 0, 0);
            const startDate = today;
            const endDate = new Date(today.getFullYear(), today.getMonth() + 3, 0);
            
            const formatDate = (date) => {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            };
            
            const dates = await this.orm.call(
                'training.booking',
                'get_trainer_available_dates',
                [],
                {
                    trainer_id: trainerId,
                    sports_center_id: sportsCenterId,
                    start_date: formatDate(startDate),
                    end_date: formatDate(endDate),
                }
            );
            
            // Формируем опции для Selection поля, исключая прошедшие даты
            const options = [];
            const todayStr = formatDate(today);
            
            for (const dateStr of dates) {
                // Пропускаем прошедшие даты
                if (dateStr < todayStr) {
                    continue;
                }
                
                const date = new Date(dateStr + 'T00:00:00');
                const day = String(date.getDate()).padStart(2, '0');
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const year = date.getFullYear();
                
                const weekdays = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
                const weekday = weekdays[date.getDay()];
                
                const label = `${day}.${month}.${year} (${weekday})`;
                options.push([dateStr, label]);
            }
            
            if (this.loadedOptionsState) {
                this.loadedOptionsState.options = options;
            }
            this.currentTrainerId = trainerId;
            this.currentSportsCenterId = sportsCenterId;
            
            console.log(`Загружено ${options.length} доступных дат для тренера ${trainerId}`);
            
        } catch (error) {
            console.error('Ошибка при загрузке доступных дат:', error);
        }
    },
    
    checkTrainerChange(nextProps) {
        const record = nextProps.record || this.props.record;
        const trainerId = record?.data?.trainer_id?.[0];
        const sportsCenterId = record?.data?.sports_center_id?.[0];
        
        if (trainerId !== this.currentTrainerId || sportsCenterId !== this.currentSportsCenterId) {
            this.loadAvailableDates();
        }
    },
    
    get options() {
        // Переопределяем getter для options, чтобы возвращать загруженные опции
        if (this.isDateSelectionField && this.loadedOptionsState) {
            // Если опции загружены (даже если это пустой массив), возвращаем их
            if (this.loadedOptionsState.options !== null && this.loadedOptionsState.options !== undefined) {
                // Убеждаемся, что опции в правильном формате
                const options = Array.isArray(this.loadedOptionsState.options) ? this.loadedOptionsState.options : [];
                return options;
            }
            // Если опции еще не загружены (null), возвращаем из field, чтобы показать поле
            const fieldOptions = this.props.field?.selection || super.options || [];
            // Убеждаемся, что это массив
            return Array.isArray(fieldOptions) ? fieldOptions : [];
        }
        const superOptions = super.options || this.props.field?.selection || [];
        return Array.isArray(superOptions) ? superOptions : [];
    },
    
    get string() {
        // Переопределяем getter для string, чтобы безопасно обрабатывать отсутствующие значения
        if (this.isDateSelectionField) {
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
