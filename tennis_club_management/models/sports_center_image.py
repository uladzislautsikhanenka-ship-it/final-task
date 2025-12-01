# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SportsCenterImage(models.Model):
    _name = 'sports.center.image'
    _description = 'Фотография спортивного центра'
    _order = 'sequence, id'

    name = fields.Char(
        string='Название',
        help='Название фотографии'
    )
    
    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        required=True,
        ondelete='cascade',
        help='Спортивный центр, к которому относится фотография'
    )
    
    image = fields.Binary(
        string='Фотография',
        required=True,
        attachment=True,
        help='Фотография спортивного центра'
    )
    
    image_medium = fields.Binary(
        string='Фотография (средний размер)',
        compute='_compute_image_medium',
        store=True,
        help='Фотография среднего размера для отображения в списках'
    )
    
    sequence = fields.Integer(
        string='Порядок',
        default=10,
        help='Порядок отображения фотографии'
    )
    
    @api.depends('image')
    def _compute_image_medium(self):
        """Вычисляет изображение среднего размера"""
        for record in self:
            if record.image:
                # В Odoo обычно используется resize_image, но для простоты
                # можно использовать простое изображение
                record.image_medium = record.image
            else:
                record.image_medium = False
    
    @api.model_create_multi
    def create(self, vals_list):
        """Проверяет ограничение на максимум 5 фотографий при создании"""
        # Проверяем перед созданием
        for vals in vals_list:
            if 'sports_center_id' in vals:
                sports_center = self.env['sports.center'].browse(vals['sports_center_id'])
                existing_count = len(sports_center.image_ids)
                if existing_count >= 5:
                    raise ValidationError(
                        _('Можно загрузить максимум 5 фотографий для спортивного центра')
                    )
        return super().create(vals_list)

