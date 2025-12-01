# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TennisCourt(models.Model):
    _name = 'tennis.court'
    _description = 'Теннисный корт'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sports_center_id, court_number'

    name = fields.Char(
        string='Название корта',
        required=True,
        tracking=True,
        help='Название теннисного корта'
    )
    
    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        required=True,
        tracking=True,
        help='Спортивный центр, к которому принадлежит корт'
    )
    
    court_number = fields.Integer(
        string='Номер корта',
        required=True,
        help='Номер корта в центре'
    )
    
    # Наследуем время работы от центра
    work_start_time = fields.Float(
        string='Время начала работы',
        related='sports_center_id.work_start_time',
        readonly=True,
        help='Время начала работы (наследуется от центра)'
    )
    
    work_end_time = fields.Float(
        string='Время окончания работы',
        related='sports_center_id.work_end_time',
        readonly=True,
        help='Время окончания работы (наследуется от центра)'
    )
    
    # Состояние корта
    state = fields.Selection([
        ('available', 'Доступен'),
        ('maintenance', 'На обслуживании'),
        ('closed', 'Закрыт'),
    ], string='Состояние', default='available', tracking=True)
    
    # Дополнительная информация
    surface_type = fields.Selection([
        ('hard', 'Хард'),
        ('clay', 'Грунт'),
        ('grass', 'Трава'),
        ('synthetic', 'Синтетика'),
    ], string='Тип покрытия', default='hard')
    
    capacity = fields.Integer(
        string='Вместимость',
        default=4,
        help='Максимальное количество игроков на корте'
    )
    
    has_lighting = fields.Boolean(
        string='Освещение',
        default=True,
        help='Наличие освещения на корте'
    )
    
    has_roof = fields.Boolean(
        string='Крыша',
        default=False,
        help='Наличие крыши над кортом'
    )
    
    # Активность
    active = fields.Boolean(
        string='Активен',
        default=True,
        tracking=True
    )
    
    # Информация о создании
    create_date = fields.Datetime(
        string='Дата создания',
        readonly=True
    )
    
    # Вычисляемые поля
    full_name = fields.Char(
        string='Полное название',
        compute='_compute_full_name',
        store=True
    )
    
    work_hours = fields.Char(
        string='Часы работы',
        compute='_compute_work_hours',
        store=True
    )
    
    # Поле для определения, является ли пользователь тренером (для readonly в представлениях)
    is_trainer = fields.Boolean(
        string='Является тренером',
        compute='_compute_is_trainer',
        store=False
    )

    @api.depends('name', 'sports_center_id.name')
    def _compute_full_name(self):
        """Вычисляет полное название корта"""
        for court in self:
            court.full_name = f"{court.sports_center_id.name} - {court.name}"

    @api.depends('work_start_time', 'work_end_time')
    def _compute_work_hours(self):
        """Вычисляет строку с часами работы"""
        for court in self:
            if court.work_start_time and court.work_end_time:
                start_hour = int(court.work_start_time)
                start_min = int((court.work_start_time - start_hour) * 60)
                end_hour = int(court.work_end_time)
                end_min = int((court.work_end_time - end_hour) * 60)
                
                court.work_hours = f"{start_hour:02d}:{start_min:02d} - {end_hour:02d}:{end_min:02d}"
            else:
                court.work_hours = "Не указано"
    
    @api.depends()
    def _compute_is_trainer(self):
        """Вычисляет, является ли текущий пользователь тренером"""
        for court in self:
            court.is_trainer = self.env.user.has_group('tennis_club_management.group_tennis_trainer')

    @api.constrains('court_number', 'sports_center_id')
    def _check_court_number(self):
        """Проверяет уникальность номера корта в центре"""
        for court in self:
            if court.court_number <= 0:
                raise ValidationError(
                    _('Номер корта должен быть больше 0')
                )
            
            # Проверяем уникальность номера в рамках центра
            existing = self.search([
                ('sports_center_id', '=', court.sports_center_id.id),
                ('court_number', '=', court.court_number),
                ('id', '!=', court.id)
            ])
            if existing:
                raise ValidationError(
                    _('Корт с номером %d уже существует в центре %s') % 
                    (court.court_number, court.sports_center_id.name)
                )

    @api.constrains('capacity')
    def _check_capacity(self):
        """Проверяет корректность вместимости"""
        for court in self:
            if court.capacity <= 0:
                raise ValidationError(
                    _('Вместимость корта должна быть больше 0')
                )

    def write(self, vals):
        """Обновляет запись корта с проверкой прав доступа для тренеров"""
        # Проверяем, что тренеры не могут изменять записи кортов
        if self.env.user.has_group('tennis_club_management.group_tennis_trainer'):
            raise ValidationError(
                _('Тренеры не имеют права изменять информацию о кортах.')
            )
        return super().write(vals)

    def action_set_maintenance(self):
        """Устанавливает корт на обслуживание"""
        # Проверяем, что пользователь не является тренером
        if self.env.user.has_group('tennis_club_management.group_tennis_trainer'):
            raise ValidationError(
                _('Тренеры не имеют права изменять статус корта.')
            )
        self.write({'state': 'maintenance'})

    def action_set_available(self):
        """Делает корт доступным"""
        # Проверяем, что пользователь не является тренером
        if self.env.user.has_group('tennis_club_management.group_tennis_trainer'):
            raise ValidationError(
                _('Тренеры не имеют права изменять статус корта.')
            )
        self.write({'state': 'available'})

    def action_set_closed(self):
        """Закрывает корт"""
        # Проверяем, что пользователь не является тренером
        if self.env.user.has_group('tennis_club_management.group_tennis_trainer'):
            raise ValidationError(
                _('Тренеры не имеют права изменять статус корта.')
            )
        self.write({'state': 'closed'})

    def action_open_sports_center(self):
        """Открывает карточку спортивного центра"""
        return {
            'name': _('Спортивный центр'),
            'type': 'ir.actions.act_window',
            'res_model': 'sports.center',
            'res_id': self.sports_center_id.id,
            'view_mode': 'form',
        }
