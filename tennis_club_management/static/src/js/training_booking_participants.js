/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { onMounted, onWillUnmount } from "@odoo/owl";

/**
 * Патч для FormController - скрывает кнопку "Add a line" для additional_participants
 * когда достигнут максимум участников
 */
patch(FormController.prototype, {
    setup() {
        super.setup();
        this.hideAddLineInterval = null;
        this.mutationObserver = null;
        this.isUpdating = false; // Флаг для предотвращения бесконечных циклов
        this.lastCanAddValue = null; // Кэш последнего значения
        
        onMounted(() => {
            // Проверяем, это ли форма training.booking
            if (this.props.resModel === 'training.booking') {
                // Небольшая задержка для инициализации формы
                setTimeout(() => {
                    this.hideAddLineButton();
                }, 500);
                
                // Периодически проверяем и скрываем кнопку (реже, чтобы не перегружать)
                this.hideAddLineInterval = setInterval(() => {
                    if (!this.isUpdating) {
                        this.hideAddLineButton();
                    }
                }, 1000);
            }
        });
        
        onWillUnmount(() => {
            if (this.hideAddLineInterval) {
                clearInterval(this.hideAddLineInterval);
            }
            if (this.mutationObserver) {
                this.mutationObserver.disconnect();
            }
        });
    },
    
    /**
     * Скрывает кнопку "Add a line" для additional_participants когда достигнут максимум
     */
    hideAddLineButton() {
        // Предотвращаем бесконечные циклы
        if (this.isUpdating) {
            return;
        }
        
        this.isUpdating = true;
        
        try {
            // Ищем все One2many поля additional_participants
            const participantsFields = document.querySelectorAll(
                'div[name="additional_participants"], ' +
                '[name="additional_participants"], ' +
                '.o_field_one2many[name="additional_participants"], ' +
                '.o_list_view[name="additional_participants"]'
            );
            
            if (participantsFields.length === 0) {
                this.isUpdating = false;
                return;
            }
            
            // Ищем поле can_add_participants в форме
            const form = document.querySelector('.o_form_view, form');
            if (!form) {
                this.isUpdating = false;
                return;
            }
            
            // Пытаемся найти значение can_add_participants из DOM
            let canAdd = true;
            const canAddField = form.querySelector('input[name="can_add_participants"], [name="can_add_participants"]');
            if (canAddField) {
                if (canAddField.tagName === 'INPUT') {
                    canAdd = canAddField.checked || canAddField.value === 'true' || canAddField.value === '1';
                } else {
                    const value = canAddField.getAttribute('value') || 
                                  canAddField.getAttribute('data-value') ||
                                  canAddField.textContent?.trim();
                    canAdd = value === 'true' || value === '1' || value === 'True';
                }
            }
            
            // Если значение не изменилось, не обновляем DOM
            if (this.lastCanAddValue === canAdd) {
                this.isUpdating = false;
                return;
            }
            
            this.lastCanAddValue = canAdd;
        
        participantsFields.forEach(field => {
            // Ищем кнопку "Add a line" внутри этого поля
            const addLineButtons = field.querySelectorAll(
                '.o_list_button_add, ' +
                'button[title*="Add"], ' +
                'button[title*="Добавить"], ' +
                'button[title*="добавить"], ' +
                '.o_field_x2many_list_row_add, ' +
                'a.o_field_x2many_list_row_add, ' +
                '[class*="add_line"], ' +
                '[class*="o_list_add"], ' +
                '.o_list_table .o_list_table_ungrouped tbody tr:last-child td:first-child, ' +
                'tbody .o_data_row:last-child .o_list_add, ' +
                '.o_list_renderer .o_list_table_ungrouped tbody tr:last-child'
            );
            
            // Также ищем через более общие селекторы
            const allButtons = field.querySelectorAll('button, a[href*="#"], .btn');
            allButtons.forEach(btn => {
                const text = (btn.textContent || btn.title || '').toLowerCase();
                if (text.includes('add') || text.includes('добавить') || text.includes('add a line')) {
                    if (!canAdd) {
                        btn.style.display = 'none';
                        btn.style.visibility = 'hidden';
                        btn.style.opacity = '0';
                        btn.style.height = '0';
                        btn.style.width = '0';
                        btn.style.overflow = 'hidden';
                        btn.style.padding = '0';
                        btn.style.margin = '0';
                        btn.setAttribute('disabled', 'disabled');
                        btn.classList.add('o_hidden');
                    } else {
                        btn.style.display = '';
                        btn.style.visibility = '';
                        btn.style.opacity = '';
                        btn.style.height = '';
                        btn.style.width = '';
                        btn.style.overflow = '';
                        btn.style.padding = '';
                        btn.style.margin = '';
                        btn.removeAttribute('disabled');
                        btn.classList.remove('o_hidden');
                    }
                }
            });
            
            // Если нельзя добавлять участников, скрываем кнопки
            if (!canAdd) {
                addLineButtons.forEach(button => {
                    button.style.display = 'none';
                    button.style.visibility = 'hidden';
                    button.style.opacity = '0';
                    button.style.height = '0';
                    button.style.width = '0';
                    button.style.overflow = 'hidden';
                    button.style.padding = '0';
                    button.style.margin = '0';
                    button.setAttribute('disabled', 'disabled');
                    button.classList.add('o_hidden');
                });
            } else {
                // Если можно добавлять, показываем кнопки
                addLineButtons.forEach(button => {
                    button.style.display = '';
                    button.style.visibility = '';
                    button.style.opacity = '';
                    button.style.height = '';
                    button.style.width = '';
                    button.style.overflow = '';
                    button.style.padding = '';
                    button.style.margin = '';
                    button.removeAttribute('disabled');
                    button.classList.remove('o_hidden');
                });
            }
        });
        } finally {
            // Сбрасываем флаг после небольшой задержки
            setTimeout(() => {
                this.isUpdating = false;
            }, 100);
        }
    },
});

