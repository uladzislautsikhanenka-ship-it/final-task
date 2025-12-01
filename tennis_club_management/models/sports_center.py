# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, time


class SportsCenter(models.Model):
    _name = 'sports.center'
    _description = 'Спортивный центр'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Название',
        required=True,
        tracking=True,
        help='Название спортивного центра'
    )
    
    manager_id = fields.Many2one(
        'hr.employee',
        string='Менеджер',
        required=True,
        tracking=True,
        help='Менеджер спортивного центра'
    )
    
    # Время работы
    work_start_time = fields.Float(
        string='Время начала работы',
        required=True,
        default=8.0,
        help='Время начала работы (в часах, например 8.0 = 08:00)'
    )
    
    work_end_time = fields.Float(
        string='Время окончания работы',
        required=True,
        default=22.0,
        help='Время окончания работы (в часах, например 22.0 = 22:00)'
    )
    
    # Количество кортов (вычисляемое поле)
    court_count = fields.Integer(
        string='Количество теннисных кортов',
        compute='_compute_court_count',
        store=True,
        readonly=True,
        help='Количество теннисных кортов в центре (вычисляется автоматически)'
    )
    
    # Связанные корты
    court_ids = fields.One2many(
        'tennis.court',
        'sports_center_id',
        string='Теннисные корты',
        help='Теннисные корты данного центра'
    )
    
    # Сотрудники центра
    employee_ids = fields.One2many(
        'hr.employee',
        'sports_center_id',
        string='Сотрудники',
        help='Сотрудники данного центра'
    )
    
    # Тренеры центра (будет добавлено в будущих версиях)
    # trainer_ids = fields.One2many(
    #     'hr.employee',
    #     'sports_center_id',
    #     string='Тренеры',
    #     domain=[('job_id.name', 'ilike', 'тренер')],
    #     help='Тренеры данного центра'
    # )
    
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
    
    current_datetime = fields.Datetime(
        string='Текущая дата и время',
        compute='_compute_current_datetime',
        store=False
    )
    
    # Поле для определения, является ли пользователь тренером (для readonly в представлениях)
    is_trainer = fields.Boolean(
        string='Является тренером',
        compute='_compute_is_trainer',
        store=False
    )
    
    # Вычисляемые поля
    total_courts = fields.Integer(
        string='Всего кортов',
        compute='_compute_total_courts',
        store=True
    )
    
    total_employees = fields.Integer(
        string='Всего сотрудников',
        compute='_compute_total_employees',
        store=True
    )
    
    # Клиенты центра (res.partner)
    customer_ids = fields.One2many(
        'res.partner',
        'sports_center_id',
        string='Клиенты',
        help='Клиенты, связанные с данным спортивным центром'
    )
    
    total_customers = fields.Integer(
        string='Всего клиентов',
        compute='_compute_total_customers',
        store=True
    )
    
    # Фотографии спортивного центра
    image_ids = fields.One2many(
        'sports.center.image',
        'sports_center_id',
        string='Фотографии',
        help='Фотографии спортивного центра (максимум 5)'
    )
    
    # Цены на типы тренировок
    training_price_ids = fields.One2many(
        'sports.center.training.price',
        'sports_center_id',
        string='Цены на типы тренировок',
        help='Цены на типы тренировок в данном спортивном центре'
    )
    
    # total_trainers = fields.Integer(
    #     string='Всего тренеров',
    #     compute='_compute_total_trainers',
    #     store=True
    # )

    @api.depends('court_ids')
    def _compute_court_count(self):
        """Вычисляет количество кортов"""
        for center in self:
            center.court_count = len(center.court_ids)

    @api.depends('court_ids')
    def _compute_total_courts(self):
        """Вычисляет общее количество кортов"""
        for center in self:
            center.total_courts = len(center.court_ids)

    @api.depends('employee_ids')
    def _compute_total_employees(self):
        """Вычисляет общее количество сотрудников"""
        for center in self:
            center.total_employees = len(center.employee_ids.filtered('active'))

    @api.depends('customer_ids')
    def _compute_total_customers(self):
        """Вычисляет общее количество клиентов"""
        for center in self:
            center.total_customers = len(center.customer_ids)

    # @api.depends('trainer_ids')
    # def _compute_total_trainers(self):
    #     """Вычисляет общее количество тренеров"""
    #     for center in self:
    #         center.total_trainers = len(center.trainer_ids)

    @api.depends()
    def _compute_current_datetime(self):
        """Вычисляет текущую дату и время"""
        for center in self:
            center.current_datetime = fields.Datetime.now()
    
    @api.depends()
    def _compute_is_trainer(self):
        """Вычисляет, является ли текущий пользователь тренером"""
        for center in self:
            center.is_trainer = self.env.user.has_group('tennis_club_management.group_tennis_trainer')

    @api.constrains('work_start_time', 'work_end_time')
    def _check_work_time(self):
        """Проверяет корректность времени работы"""
        for center in self:
            if center.work_start_time >= center.work_end_time:
                raise ValidationError(
                    _('Время начала работы должно быть меньше времени окончания работы')
                )
            if center.work_start_time < 0 or center.work_start_time > 24:
                raise ValidationError(
                    _('Время начала работы должно быть от 0 до 24 часов')
                )
            if center.work_end_time < 0 or center.work_end_time > 24:
                raise ValidationError(
                    _('Время окончания работы должно быть от 0 до 24 часов')
                )
    
    @api.constrains('image_ids')
    def _check_max_images(self):
        """Проверяет, что количество фотографий не превышает 5"""
        for center in self:
            if len(center.image_ids) > 5:
                raise ValidationError(
                    _('Можно загрузить максимум 5 фотографий для спортивного центра')
                )


    def action_open_courts(self):
        """Открывает список кортов центра"""
        return {
            'name': _('Теннисные корты'),
            'type': 'ir.actions.act_window',
            'res_model': 'tennis.court',
            'view_mode': 'list,form',
            'domain': [('sports_center_id', '=', self.id)],
            'context': {'default_sports_center_id': self.id},
        }

    def action_open_employees(self):
        """Открывает список сотрудников центра"""
        return {
            'name': _('Сотрудники'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('sports_center_id', '=', self.id)],
            'context': {'default_sports_center_id': self.id},
        }

    def action_open_customers(self):
        """Открывает список клиентов центра (res.partner)"""
        return {
            'name': _('Клиенты'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('sports_center_id', '=', self.id)],
            'context': {'default_sports_center_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        """Создает спортивные центры и автоматически связывает менеджеров"""
        # Проверяем, что пользователь не является тренером
        if self.env.user.has_group('tennis_club_management.group_tennis_trainer'):
            raise ValidationError(
                _('Тренеры не имеют права создавать новые спортивные центры.')
            )
        
        # Проверяем, что менеджеры не являются менеджерами других центров
        for vals in vals_list:
            if vals.get('manager_id'):
                manager = self.env['hr.employee'].browse(vals['manager_id'])
                if manager.position == 'manager' and manager.sports_center_id:
                    raise ValidationError(
                        _('Сотрудник "%s" уже является менеджером спортивного центра "%s". '
                          'У одного спортивного центра может быть только один менеджер.') % (
                            manager.name,
                            manager.sports_center_id.name
                        )
                    )
        
        centers = super().create(vals_list)
        
        # Автоматически связываем менеджеров с центрами
        for center in centers:
            if center.manager_id:
                center.manager_id.write({
                    'sports_center_id': center.id,
                    'position': 'manager'
                })
        
        return centers

    def write(self, vals):
        """Обновляет связь менеджера с центром при изменении"""
        # Проверяем, что новый менеджер не является менеджером другого центра
        if 'manager_id' in vals:
            for center in self:
                if vals['manager_id']:
                    new_manager = self.env['hr.employee'].browse(vals['manager_id'])
                    # Проверяем, не является ли он уже менеджером другого центра
                    if new_manager.position == 'manager' and new_manager.sports_center_id and new_manager.sports_center_id.id != center.id:
                        raise ValidationError(
                            _('Сотрудник "%s" уже является менеджером спортивного центра "%s". '
                              'У одного спортивного центра может быть только один менеджер.') % (
                                new_manager.name,
                                new_manager.sports_center_id.name
                            )
                        )
                    # Проверяем, нет ли у этого центра уже другого менеджера (даже не в manager_id)
                    existing_managers = self.env['hr.employee'].search([
                        ('sports_center_id', '=', center.id),
                        ('position', '=', 'manager'),
                        ('id', '!=', vals['manager_id']),
                        ('active', '=', True)
                    ])
                    if existing_managers:
                        # Убираем позицию менеджера у существующих менеджеров
                        existing_managers.write({'position': 'trainer'})
                    # Если у центра был старый менеджер, убираем у него позицию менеджера
                    if center.manager_id and center.manager_id.id != vals['manager_id']:
                        old_manager = center.manager_id
                        if old_manager.sports_center_id.id == center.id:
                            old_manager.write({'position': 'trainer'})
        
        result = super().write(vals)
        
        if 'manager_id' in vals:
            for center in self:
                if center.manager_id:
                    # Устанавливаем позицию менеджера и связываем с центром
                    center.manager_id.write({
                        'sports_center_id': center.id,
                        'position': 'manager'
                    })
                # Если менеджер был удален, находим всех менеджеров этого центра и меняем их позицию
                elif not center.manager_id:
                    managers = self.env['hr.employee'].search([
                        ('sports_center_id', '=', center.id),
                        ('position', '=', 'manager'),
                        ('active', '=', True)
                    ])
                    for manager in managers:
                        manager.write({'position': 'trainer'})
        
        return result

    @api.model
    def action_open_my_centers(self):
        """Возвращает действие открытия центров с учетом прав пользователя"""
        action = self.env.ref('tennis_club_management.action_sports_center').read()[0]
        user = self.env.user
        employee = user.sudo().employee_id
        if employee and employee.sports_center_id:
            action['domain'] = [('id', '=', employee.sports_center_id.id)]
        elif employee:
            action['domain'] = ['|', ('employee_ids.user_id', '=', user.id), ('manager_id.user_id', '=', user.id)]
        else:
            action['domain'] = []
        return action

    # def action_open_trainers(self):
    #     """Открывает список тренеров центра"""
    #     return {
    #         'name': _('Тренеры'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'hr.employee',
    #         'view_mode': 'list,form',
    #         'domain': [('sports_center_id', '=', self.id)],
    #         'context': {'default_sports_center_id': self.id},
    #     }

    def action_open_analytics(self):
        """Открыть визард аналитики по центру"""
        self.ensure_one()
        wizard = self.env['sports.center.analytics.wizard'].create({
            'sports_center_id': self.id,
        })
        return wizard.action_open()
    
    def action_open_training_prices(self):
        """Открывает список цен на типы тренировок для данного центра"""
        self.ensure_one()
        return {
            'name': _('Цены на типы тренировок'),
            'type': 'ir.actions.act_window',
            'res_model': 'sports.center.training.price',
            'view_mode': 'list,form',
            'domain': [('sports_center_id', '=', self.id)],
            'context': {
                'default_sports_center_id': self.id,
                'search_default_sports_center_id': self.id,
            },
        }
