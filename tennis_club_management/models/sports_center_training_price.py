# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SportsCenterTrainingPrice(models.Model):
    _name = 'sports.center.training.price'
    _description = 'Стоимость типа тренировки в спортивном центре'
    _order = 'sports_center_id, training_type_id'
    _rec_name = 'display_name'

    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        required=True,
        ondelete='cascade',
        help='Спортивный центр'
    )
    
    training_type_id = fields.Many2one(
        'training.type',
        string='Тип тренировки',
        required=True,
        help='Тип тренировки'
    )
    
    price_per_hour = fields.Float(
        string='Цена за час',
        required=True,
        default=0.0,
        help='Цена за час тренировки в данном спортивном центре'
    )
    
    active = fields.Boolean(
        string='Активен',
        default=True,
        help='Активна ли данная цена'
    )
    
    # Связанные поля для удобства отображения
    training_type_name = fields.Char(
        string='Название типа',
        related='training_type_id.name',
        readonly=True,
        store=True
    )
    
    training_type_category = fields.Selection(
        string='Категория',
        related='training_type_id.category',
        readonly=True,
        store=True
    )
    
    training_type_code = fields.Char(
        string='Код',
        related='training_type_id.code',
        readonly=True,
        store=True
    )
    
    display_name = fields.Char(
        string='Отображаемое имя',
        compute='_compute_display_name',
        store=True
    )
    
    @api.depends('sports_center_id', 'training_type_id', 'price_per_hour')
    def _compute_display_name(self):
        """Вычисляет отображаемое имя"""
        for record in self:
            if record.sports_center_id and record.training_type_id:
                record.display_name = f"{record.sports_center_id.name} - {record.training_type_id.name} ({record.price_per_hour:.0f} руб/час)"
            else:
                record.display_name = _('Новая цена')
    
    @api.constrains('sports_center_id', 'training_type_id')
    def _check_unique_price(self):
        """Проверяет уникальность комбинации центра и типа тренировки"""
        for record in self:
            existing = self.search([
                ('sports_center_id', '=', record.sports_center_id.id),
                ('training_type_id', '=', record.training_type_id.id),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(
                    _('Цена для типа тренировки "%s" в спортивном центре "%s" уже существует') % (
                        record.training_type_id.name,
                        record.sports_center_id.name
                    )
                )
    
    @api.constrains('price_per_hour')
    def _check_price(self):
        """Проверяет корректность цены"""
        for record in self:
            if record.price_per_hour < 0:
                raise ValidationError(
                    _('Цена за час не может быть отрицательной')
                )


