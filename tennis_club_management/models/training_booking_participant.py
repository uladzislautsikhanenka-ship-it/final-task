# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TrainingBookingParticipant(models.Model):
    _name = 'training.booking.participant'
    _description = 'Участник тренировки'
    _order = 'booking_id, sequence'

    booking_id = fields.Many2one(
        'training.booking',
        string='Запись на тренировку',
        required=True,
        ondelete='cascade',
        help='Запись на тренировку'
    )
    
    participant_id = fields.Many2one(
        'res.partner',
        string='Участник',
        required=True,
        domain=[('is_company', '=', False), ('is_employee', '=', False), ('telegram_chat_id', '!=', False)],
        help='Участник тренировки'
    )
    
    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Переопределяем fields_get для динамического изменения домена поля participant_id"""
        res = super().fields_get(allfields=allfields, attributes=attributes)
        
        if 'participant_id' not in res:
            return res
        
        # Базовый домен: только клиенты (не сотрудники), не компания, с telegram_chat_id
        base_domain = [
            ('is_company', '=', False),
            ('is_employee', '=', False),
            ('telegram_chat_id', '!=', False),
        ]
        
        # Пытаемся получить booking_id из разных источников
        booking_id = None
        
        # 1. Из контекста
        booking_id = self.env.context.get('default_booking_id') or self.env.context.get('booking_id')
        
        # 2. Если это запись в One2many, пытаемся получить из активной записи
        if not booking_id and hasattr(self, 'booking_id') and self.booking_id:
            booking_id = self.booking_id.id
        
        # 3. Если есть активная запись в контексте
        if not booking_id:
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')
            if active_model == 'training.booking' and active_id:
                booking_id = active_id
        
        if booking_id:
            booking = self.env['training.booking'].browse(booking_id)
            if booking.exists():
                domain = base_domain.copy()
                
                # Добавляем фильтр по спортивному центру, если он указан
                if booking.sports_center_id:
                    domain = ['|'] + domain + [
                        ('sports_center_id', '=', booking.sports_center_id.id),
                        ('sports_center_id', '=', False)
                    ]
                
                # Получаем список ID уже выбранных участников
                excluded_ids = []
                if booking.customer_id:
                    excluded_ids.append(booking.customer_id.id)
                if booking.additional_participants:
                    # Получаем все participant_id, включая возможные дубликаты
                    participant_ids = booking.additional_participants.mapped('participant_id').ids
                    # Убираем дубликаты и None значения
                    excluded_ids.extend([pid for pid in participant_ids if pid])
                
                # Исключаем уже выбранных участников
                if excluded_ids:
                    # Убираем дубликаты из списка исключенных
                    excluded_ids = list(set(excluded_ids))
                    domain.append(('id', 'not in', excluded_ids))
                
                res['participant_id']['domain'] = domain
        else:
            # Если booking_id не найден, используем базовый домен
            res['participant_id']['domain'] = base_domain
        
        return res
    
    @api.onchange('participant_id')
    def _onchange_participant_id(self):
        """Обновляет домен при изменении участника"""
        # Не вызываем вычисляемые поля вручную - они автоматически пересчитываются через @api.depends
        # Это предотвращает циклические зависимости и зависания
        pass
    
    sequence = fields.Integer(
        string='Порядок',
        default=10,
        help='Порядок отображения'
    )
    
    # Связанные поля
    training_type_id = fields.Many2one(
        'training.type',
        string='Тип тренировки',
        related='booking_id.training_type_id',
        readonly=True,
        help='Тип тренировки'
    )
    
    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        related='booking_id.sports_center_id',
        readonly=True,
        help='Спортивный центр'
    )
    
    booking_date = fields.Date(
        string='Дата тренировки',
        related='booking_id.booking_date',
        readonly=True,
        help='Дата тренировки'
    )
    
    start_time = fields.Float(
        string='Время начала',
        related='booking_id.start_time',
        readonly=True,
        help='Время начала тренировки'
    )
    
    end_time = fields.Float(
        string='Время окончания',
        related='booking_id.end_time',
        readonly=True,
        help='Время окончания тренировки'
    )
    
    @api.constrains('participant_id', 'booking_id')
    def _check_duplicate_participants(self):
        """Проверяет, что участник не дублируется в одной записи"""
        for participant in self:
            if not participant.booking_id or not participant.participant_id:
                continue
                
            booking = participant.booking_id
            
            # Проверяем, что основной клиент не указан как дополнительный участник
            if booking.customer_id and participant.participant_id.id == booking.customer_id.id:
                raise ValidationError(
                    _('Основной клиент "%s" не может быть указан как дополнительный участник') % booking.customer_id.name
                )
            
            # Проверяем дублирование участников в одной записи (исключая текущую запись)
            existing = self.search([
                ('booking_id', '=', booking.id),
                ('participant_id', '=', participant.participant_id.id),
                ('id', '!=', participant.id),
                ('participant_id', '!=', False)
            ])
            if existing:
                raise ValidationError(
                    _('Участник "%s" уже добавлен в эту запись. Каждый участник может быть добавлен только один раз.') % participant.participant_id.name
                )
    
    @api.model_create_multi
    def create(self, vals_list):
        """Переопределяем create для проверки лимита участников и дубликатов перед созданием"""
        # Собираем все participant_id для каждой booking_id, чтобы проверить дубликаты в рамках одного batch
        booking_participants = {}
        for vals in vals_list:
            if vals.get('booking_id') and vals.get('participant_id'):
                booking_id = vals['booking_id']
                participant_id = vals['participant_id']
                if booking_id not in booking_participants:
                    booking_participants[booking_id] = []
                booking_participants[booking_id].append(participant_id)
        
        # Проверяем дубликаты внутри batch
        for booking_id, participant_ids in booking_participants.items():
            if len(participant_ids) != len(set(participant_ids)):
                # Есть дубликаты в batch
                from collections import Counter
                duplicates = [pid for pid, count in Counter(participant_ids).items() if count > 1]
                if duplicates:
                    duplicate_names = self.env['res.partner'].browse(duplicates).mapped('name')
                    raise ValidationError(
                        _('Нельзя добавить одного и того же участника несколько раз: %s') % ', '.join(duplicate_names)
                    )
        
        # Проверяем лимит и дубликаты ПЕРЕД созданием для каждой записи
        for vals in vals_list:
            if vals.get('booking_id') and vals.get('participant_id'):
                booking = self.env['training.booking'].browse(vals['booking_id'])
                
                # Проверяем, что участник не является основным клиентом
                if booking.customer_id and vals['participant_id'] == booking.customer_id.id:
                    raise ValidationError(
                        _('Основной клиент "%s" не может быть указан как дополнительный участник') % booking.customer_id.name
                    )
                
                # Проверяем дубликаты с уже существующими записями
                existing = self.search([
                    ('booking_id', '=', booking.id),
                    ('participant_id', '=', vals['participant_id']),
                    ('participant_id', '!=', False)
                ])
                if existing:
                    participant_name = self.env['res.partner'].browse(vals['participant_id']).name
                    raise ValidationError(
                        _('Участник "%s" уже добавлен в эту запись. Каждый участник может быть добавлен только один раз.') % participant_name
                    )
                
                # Проверяем лимит
                if booking.training_type_id and booking.training_type_id.max_participants > 0:
                    # Считаем общее количество участников (основной клиент + дополнительные с заполненным participant_id)
                    main_customer = 1 if booking.customer_id else 0
                    filled_participants = len(booking.additional_participants.filtered('participant_id'))
                    # Учитываем текущую создаваемую запись
                    total_participants = main_customer + filled_participants + 1
                    
                    # Если уже достигнут или превышен максимум, не позволяем создать новую запись
                    if total_participants > booking.training_type_id.max_participants:
                        raise ValidationError(
                            _('Достигнут максимальный лимит участников для типа тренировки "%s". '
                              'Максимум: %d, будет участников: %d. '
                              'Невозможно добавить еще участников.') % (
                                booking.training_type_id.name,
                                booking.training_type_id.max_participants,
                                total_participants
                            )
                        )
        
        participants = super().create(vals_list)
        
        # Обновляем вычисляемые поля родительских записей
        for participant in participants:
            if participant.booking_id:
                # Обновляем все связанные вычисляемые поля
                participant.booking_id._compute_participant_count()
                participant.booking_id._compute_has_min_participants()
                participant.booking_id._compute_can_add_participants()
                participant.booking_id._compute_selected_participant_ids()
                participant.booking_id._compute_excluded_participant_ids()
                participant.booking_id._compute_excluded_participant_ids_list()
                participant.booking_id._compute_excluded_participant_ids_for_domain()
        
        return participants
    
    @api.constrains('booking_id', 'participant_id')
    def _check_participants_limit(self):
        """Проверяет лимит участников для типа тренировки"""
        for participant in self:
            if not participant.booking_id or not participant.training_type_id or not participant.participant_id:
                continue
            
            booking = participant.booking_id
            training_type = participant.training_type_id
            
            if training_type.max_participants > 0:
                # Считаем общее количество участников (основной клиент + дополнительные с заполненным participant_id)
                main_customer = 1 if booking.customer_id else 0
                # Считаем только участников с заполненным participant_id (исключая пустые записи)
                filled_participants = len(booking.additional_participants.filtered('participant_id'))
                total_participants = main_customer + filled_participants
                
                if total_participants > training_type.max_participants:
                    raise ValidationError(
                        _('Превышен лимит участников для типа тренировки "%s". '
                          'Максимум: %d, указано: %d. '
                          'Пожалуйста, удалите лишних участников.') % (
                            training_type.name,
                            training_type.max_participants,
                            total_participants
                        )
                    )
    
    def write(self, vals):
        """Переопределяем write для проверки лимита и дубликатов при изменении участника"""
        # Проверяем дубликаты и лимит ПЕРЕД записью
        if 'participant_id' in vals:
            for participant in self:
                if participant.booking_id and participant.booking_id.training_type_id:
                    booking = participant.booking_id
                    training_type = booking.training_type_id
                    
                    # Проверяем, что новый участник не является основным клиентом
                    if vals.get('participant_id') and booking.customer_id:
                        if vals['participant_id'] == booking.customer_id.id:
                            raise ValidationError(
                                _('Основной клиент "%s" не может быть указан как дополнительный участник') % booking.customer_id.name
                            )
                    
                    # Проверяем дубликаты
                    if vals.get('participant_id'):
                        existing = self.search([
                            ('booking_id', '=', booking.id),
                            ('participant_id', '=', vals['participant_id']),
                            ('id', '!=', participant.id),
                            ('participant_id', '!=', False)
                        ])
                        if existing:
                            raise ValidationError(
                                _('Участник уже добавлен в эту запись. Каждый участник может быть добавлен только один раз.')
                            )
                    
                    # Проверяем лимит
                    if training_type.max_participants > 0:
                        main_customer = 1 if booking.customer_id else 0
                        # Считаем участников, исключая текущую запись (если она еще не изменена)
                        other_participants = booking.additional_participants.filtered(
                            lambda p: p.id != participant.id and p.participant_id
                        )
                        filled_participants = len(other_participants)
                        # Если устанавливаем participant_id, добавляем 1
                        if vals.get('participant_id'):
                            filled_participants += 1
                        total_participants = main_customer + filled_participants
                        
                        if total_participants > training_type.max_participants:
                            raise ValidationError(
                                _('Превышен лимит участников для типа тренировки "%s". '
                                  'Максимум: %d, будет указано: %d. '
                                  'Пожалуйста, удалите лишних участников.') % (
                                    training_type.name,
                                    training_type.max_participants,
                                    total_participants
                                )
                            )
        
        result = super().write(vals)
        
        # Обновляем вычисляемые поля родительской записи
        if 'participant_id' in vals:
            for participant in self:
                if participant.booking_id:
                    # Обновляем все связанные вычисляемые поля
                    participant.booking_id._compute_participant_count()
                    participant.booking_id._compute_has_min_participants()
                    participant.booking_id._compute_can_add_participants()
                    participant.booking_id._compute_selected_participant_ids()
                    participant.booking_id._compute_excluded_participant_ids()
                    participant.booking_id._compute_excluded_participant_ids_list()
                    participant.booking_id._compute_excluded_participant_ids_for_domain()
        
        return result
    
    def unlink(self):
        """Переопределяем unlink для обновления вычисляемых полей родительской записи"""
        bookings = self.mapped('booking_id')
        result = super().unlink()
        
        # Обновляем вычисляемые поля родительских записей
        for booking in bookings:
            # Обновляем все связанные вычисляемые поля
            booking._compute_participant_count()
            booking._compute_has_min_participants()
            booking._compute_can_add_participants()
            booking._compute_selected_participant_ids()
            booking._compute_excluded_participant_ids()
            booking._compute_excluded_participant_ids_list()
            booking._compute_excluded_participant_ids_for_domain()
        
        return result
