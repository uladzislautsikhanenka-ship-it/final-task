# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TrainingType(models.Model):
    _name = 'training.type'
    _description = 'Тип тренировки'
    _order = 'sequence, name'

    name = fields.Char(
        string='Название',
        required=True,
        help='Название типа тренировки'
    )
    
    code = fields.Char(
        string='Код',
        required=True,
        help='Уникальный код типа тренировки'
    )
    
    # Явная категория типа тренировки для корректного определения надбавок тренера
    category = fields.Selection(
        selection=[
            ('individual', 'Индивидуальная'),
            ('split', 'Сплит'),
            ('group', 'Групповая'),
        ],
        string='Категория',
        help='Используется для расчёта надбавки тренера. '
             'Если не заполнено, система попытается определить по коду/названию.'
    )
    
    description = fields.Text(
        string='Описание',
        help='Описание типа тренировки'
    )
    
    # Цена за час (резервная, используется если не задана цена для спортивного центра)
    price_per_hour = fields.Float(
        string='Цена за час (резервная)',
        default=0.0,
        help='Резервная цена за час тренировки. Используется только если не задана цена для конкретного спортивного центра в разделе "Цены на типы тренировок"'
    )
    
    # Количество участников
    min_participants = fields.Integer(
        string='Минимум участников',
        required=True,
        default=1,
        help='Минимальное количество участников'
    )
    
    max_participants = fields.Integer(
        string='Максимум участников',
        required=True,
        default=1,
        help='Максимальное количество участников'
    )
    
    # Продолжительность в часах
    duration_hours = fields.Float(
        string='Продолжительность (часы)',
        required=True,
        default=1.0,
        help='Продолжительность тренировки в часах'
    )
    
    # Активность
    active = fields.Boolean(
        string='Активен',
        default=True,
        help='Активен ли тип тренировки'
    )
    
    # Порядок отображения
    sequence = fields.Integer(
        string='Порядок',
        default=10,
        help='Порядок отображения в списке'
    )
    
    # Цвет для календаря
    color = fields.Integer(
        string='Цвет',
        default=0,
        help='Цвет для отображения в календаре'
    )
    
    # Связанные записи
    booking_ids = fields.One2many(
        'training.booking',
        'training_type_id',
        string='Записи на тренировки',
        help='Записи на данный тип тренировки'
    )
    
    # Цены в спортивных центрах
    training_price_ids = fields.One2many(
        'sports.center.training.price',
        'training_type_id',
        string='Цены в спортивных центрах',
        help='Цены данного типа тренировки в различных спортивных центрах'
    )
    
    # Вычисляемые поля
    total_bookings = fields.Integer(
        string='Всего записей',
        compute='_compute_total_bookings',
        store=True
    )
    
    total_prices = fields.Integer(
        string='Всего цен',
        compute='_compute_total_prices',
        store=True
    )
    
    @api.depends('booking_ids')
    def _compute_total_bookings(self):
        """Вычисляет общее количество записей"""
        for training_type in self:
            training_type.total_bookings = len(training_type.booking_ids)
    
    @api.depends('training_price_ids')
    def _compute_total_prices(self):
        """Вычисляет общее количество цен"""
        for training_type in self:
            training_type.total_prices = len(training_type.training_price_ids)
    
    @api.constrains('min_participants', 'max_participants')
    def _check_participants(self):
        """Проверяет корректность количества участников"""
        for training_type in self:
            if training_type.min_participants <= 0:
                raise ValidationError(
                    _('Минимальное количество участников должно быть больше 0')
                )
            if training_type.max_participants <= 0:
                raise ValidationError(
                    _('Максимальное количество участников должно быть больше 0')
                )
            if training_type.min_participants > training_type.max_participants:
                raise ValidationError(
                    _('Минимальное количество участников не может быть больше максимального')
                )
    
    @api.constrains('price_per_hour')
    def _check_price(self):
        """Проверяет корректность цены"""
        for training_type in self:
            if training_type.price_per_hour < 0:
                raise ValidationError(
                    _('Цена за час не может быть отрицательной')
                )
    
    @api.constrains('duration_hours')
    def _check_duration(self):
        """Проверяет корректность продолжительности"""
        for training_type in self:
            if training_type.duration_hours <= 0:
                raise ValidationError(
                    _('Продолжительность должна быть больше 0')
                )
    
    @api.constrains('code')
    def _check_code_unique(self):
        """Проверяет уникальность кода"""
        for training_type in self:
            existing = self.search([
                ('code', '=', training_type.code),
                ('id', '!=', training_type.id)
            ])
            if existing:
                raise ValidationError(
                    _('Тип тренировки с кодом "%s" уже существует') % training_type.code
                )
    
    def name_get(self):
        """Возвращает отображаемое имя"""
        result = []
        for training_type in self:
            result.append((training_type.id, training_type.name))
        return result
    
    def action_duplicate(self):
        """Дублирует тип тренировки"""
        for training_type in self:
            return {
                'name': _('Дублировать тип тренировки'),
                'type': 'ir.actions.act_window',
                'res_model': 'training.type',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_name': f'Копия {training_type.name}',
                    'default_code': f'{training_type.code}_copy',
                    'default_price_per_hour': training_type.price_per_hour,
                    'default_min_participants': training_type.min_participants,
                    'default_max_participants': training_type.max_participants,
                    'default_duration_hours': training_type.duration_hours,
                    'default_description': training_type.description,
                }
            }
    
    def action_view_bookings(self):
        """Открывает записи на тренировки данного типа"""
        return {
            'name': _('Записи на тренировки'),
            'type': 'ir.actions.act_window',
            'res_model': 'training.booking',
            'view_mode': 'list,form,calendar',
            'domain': [('training_type_id', '=', self.id)],
            'context': {'search_default_training_type_id': self.id},
        }
    
    def action_view_training_prices(self):
        """Открывает цены данного типа тренировки в спортивных центрах"""
        return {
            'name': _('Цены в спортивных центрах'),
            'type': 'ir.actions.act_window',
            'res_model': 'sports.center.training.price',
            'view_mode': 'list,form',
            'domain': [('training_type_id', '=', self.id)],
            'context': {
                'default_training_type_id': self.id,
                'search_default_training_type_id': self.id,
            },
        }
