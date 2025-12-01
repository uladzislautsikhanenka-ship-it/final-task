# -*- coding: utf-8 -*-

from odoo import models, fields


class TrainingWeekday(models.Model):
    _name = 'training.weekday'
    _description = 'День недели для повторяющихся тренировок'
    _order = 'sequence'

    name = fields.Char(string='Название', required=True)
    code = fields.Integer(string='Код дня', required=True, help='0=Пн ... 6=Вс')
    sequence = fields.Integer(string='Порядок', default=10)



