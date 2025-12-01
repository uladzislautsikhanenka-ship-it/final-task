# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class AvailableDate(models.TransientModel):
    """Виртуальная модель для выбора доступных дат тренера"""
    _name = 'available.date'
    _description = 'Доступная дата тренера'
    _order = 'date'

    name = fields.Char(string='Дата', compute='_compute_name', store=True)
    date = fields.Date(string='Дата', required=True, index=True)
    trainer_id = fields.Many2one('hr.employee', string='Тренер', required=True, index=True)
    sports_center_id = fields.Many2one('sports.center', string='Спортивный центр', required=True, index=True)
    
    @api.depends('date')
    def _compute_name(self):
        """Форматирует дату для отображения"""
        for rec in self:
            if rec.date:
                # Форматируем дату: ДД.ММ.ГГГГ (День недели)
                weekdays = {
                    0: 'Пн',
                    1: 'Вт',
                    2: 'Ср',
                    3: 'Чт',
                    4: 'Пт',
                    5: 'Сб',
                    6: 'Вс'
                }
                weekday = rec.date.weekday()
                weekday_name = weekdays.get(weekday, '')
                rec.name = f"{rec.date.strftime('%d.%m.%Y')} ({weekday_name})"
            else:
                rec.name = ''
    
    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Переопределяем search_read для динамической генерации записей"""
        # Получаем trainer_id и sports_center_id из domain
        trainer_id = None
        sports_center_id = None
        
        if domain:
            for condition in domain:
                if isinstance(condition, (list, tuple)) and len(condition) == 3:
                    field, operator, value = condition
                    if field == 'trainer_id':
                        trainer_id = value
                    elif field == 'sports_center_id':
                        sports_center_id = value
        
        # Если trainer_id и sports_center_id не найдены в domain, пробуем из контекста
        if not trainer_id:
            trainer_id = self.env.context.get('default_trainer_id') or self.env.context.get('trainer_id')
        if not sports_center_id:
            sports_center_id = self.env.context.get('default_sports_center_id') or self.env.context.get('sports_center_id')
        
        if not trainer_id or not sports_center_id:
            return []
        
        # Получаем доступные даты через метод training.booking
        dates = self.env['training.booking'].get_trainer_available_dates(
            trainer_id=trainer_id,
            sports_center_id=sports_center_id
        )
        
        # Создаем записи для каждой даты
        records = []
        for idx, date_str in enumerate(dates):
            date_obj = fields.Date.from_string(date_str)
            records.append({
                'id': idx + 1,  # Временный ID
                'name': self._format_date_name(date_obj),
                'date': date_str,
                'trainer_id': trainer_id,
                'sports_center_id': sports_center_id,
            })
        
        # Применяем фильтры из domain
        if domain:
            for condition in domain:
                if isinstance(condition, (list, tuple)) and len(condition) == 3:
                    field, operator, value = condition
                    if field == 'date' and operator == '=':
                        records = [r for r in records if r['date'] == value]
                    elif field == 'date' and operator == '>=':
                        records = [r for r in records if r['date'] >= value]
                    elif field == 'date' and operator == '<=':
                        records = [r for r in records if r['date'] <= value]
        
        # Применяем сортировку
        if order:
            reverse = order.startswith('-')
            field_name = order.lstrip('-')
            records.sort(key=lambda x: x.get(field_name, ''), reverse=reverse)
        
        # Применяем offset и limit
        if offset:
            records = records[offset:]
        if limit:
            records = records[:limit]
        
        return records
    
    @api.model
    def _format_date_name(self, date_obj):
        """Форматирует дату для отображения"""
        weekdays = {
            0: 'Пн',
            1: 'Вт',
            2: 'Ср',
            3: 'Чт',
            4: 'Пт',
            5: 'Сб',
            6: 'Вс'
        }
        weekday = date_obj.weekday()
        weekday_name = weekdays.get(weekday, '')
        return f"{date_obj.strftime('%d.%m.%Y')} ({weekday_name})"
    
    @api.model
    def read(self, ids, fields=None, load='_classic_read'):
        """Переопределяем read для чтения виртуальных записей"""
        result = []
        for rec_id in ids:
            # Получаем данные из контекста или создаем временную запись
            result.append({
                'id': rec_id,
                'name': f"Дата {rec_id}",
            })
        return result

