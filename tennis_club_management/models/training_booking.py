# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class TrainingBooking(models.Model):
    _name = 'training.booking'
    _description = 'Запись на тренировку'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'booking_date, start_time'

    name = fields.Char(
        string='Номер записи',
        required=True,
        default=lambda self: _('New'),
        help='Номер записи на тренировку'
    )
    
    # Основные поля
    customer_id = fields.Many2one(
        'res.partner',
        string='Клиент',
        required=False,
        tracking=True,
        domain=[('is_company', '=', False), ('is_employee', '=', False)],
        help='Клиент, записывающийся на тренировку'
    )
    
    group_id = fields.Many2one(
        'training.group',
        string='Группа',
        required=False,
        tracking=True,
        domain="[('training_type_id', '=', training_type_id), ('active', '=', True)]",
        help='Группа для групповой тренировки'
    )
    
    # Вычисляемое поле для определения, является ли тип тренировки групповым
    is_group_training = fields.Boolean(
        string='Групповая тренировка',
        compute='_compute_is_group_training',
        store=False,
        help='Является ли тип тренировки групповым'
    )
    
    trainer_id = fields.Many2one(
        'hr.employee',
        string='Тренер',
        required=True,
        tracking=True,
        domain=[('job_id.name', 'ilike', 'тренер')],
        help='Тренер, проводящий тренировку'
    )
    
    court_id = fields.Many2one(
        'tennis.court',
        string='Теннисный корт',
        required=True,
        tracking=True,
        help='Корт, на котором проводится тренировка'
    )
    
    training_type_id = fields.Many2one(
        'training.type',
        string='Тип тренировки',
        required=True,
        tracking=True,
        help='Тип тренировки'
    )
    
    # Связанные поля типа тренировки для удобства использования в представлениях
    training_type_min_participants = fields.Integer(
        string='Минимум участников',
        related='training_type_id.min_participants',
        readonly=True,
        store=False,
        help='Минимальное количество участников для данного типа тренировки'
    )
    
    training_type_max_participants = fields.Integer(
        string='Максимум участников',
        related='training_type_id.max_participants',
        readonly=True,
        store=False,
        help='Максимальное количество участников для данного типа тренировки'
    )
    
    # Дата и время
    booking_date = fields.Date(
        string='Дата тренировки',
        required=True,
        tracking=True,
        help='Дата проведения тренировки'
    )
    
    # Поле для выбора даты из доступных дат тренера (используется как Selection)
    # ВАЖНО: Это compute поле без store, оно не хранится в базе данных
    available_booking_date_selection = fields.Selection(
        selection='_get_available_dates_selection',
        string='Дата тренировки (из доступных)',
        compute='_compute_available_booking_date_selection',
        inverse='_inverse_available_booking_date_selection',
        store=False,
        readonly=False,
        help='Выберите дату из доступных дат тренера'
    )
    
    start_time = fields.Float(
        string='Время начала',
        required=True,
        tracking=True,
        help='Время начала тренировки (в часах, например 10.5 = 10:30)'
    )
    
    # Поле для выбора времени начала из доступных часов тренера (используется как Selection)
    available_start_time_selection = fields.Selection(
        selection='_get_available_times_selection',
        string='Время начала (из доступных)',
        compute='_compute_available_start_time_selection',
        inverse='_inverse_available_start_time_selection',
        store=False,
        readonly=False,
        help='Выберите время начала из доступных часов тренера'
    )
    
    end_time = fields.Float(
        string='Время окончания',
        required=True,
        help='Время окончания тренировки (в часах, например 11.5 = 11:30)'
    )
    
    # Дополнительные участники (для сплит и групповых тренировок)
    additional_participants = fields.One2many(
        'training.booking.participant',
        'booking_id',
        string='Дополнительные участники',
        help='Дополнительные участники тренировки'
    )

    participant_count = fields.Integer(
        string='Участников',
        compute='_compute_participant_count',
        store=False,
        help='Общее число участников (включая основного клиента)'
    )
    
    # Статус записи
    state = fields.Selection([
        ('draft', 'Черновик'),
        ('confirmed', 'Подтверждена'),
        ('in_progress', 'В процессе'),
        ('completed', 'Завершена'),
        ('cancelled', 'Отменена'),
    ], string='Статус', default='draft', tracking=True)
    
    # Цвет для календаря (зеленый для завершенных, цвет типа тренировки для остальных)
    color = fields.Integer(
        string='Цвет',
        compute='_compute_color',
        store=False,
        help='Цвет для отображения в календаре'
    )
    
    @api.depends('state', 'training_type_id', 'training_type_id.color')
    def _compute_color(self):
        """Вычисляет цвет для календаря на основе статуса тренировки"""
        for booking in self:
            if booking.state == 'completed':
                # Зеленый цвет для завершенных тренировок (10 - темно-зеленый в Odoo)
                booking.color = 10
            elif booking.state == 'in_progress':
                # Желтый цвет для тренировок в процессе (3 - желтый в Odoo)
                booking.color = 3
            elif booking.state == 'cancelled':
                # Красный цвет для отмененных тренировок (1 - красный в Odoo)
                booking.color = 1
            elif booking.training_type_id and booking.training_type_id.color:
                # Используем цвет типа тренировки для остальных (если установлен)
                booking.color = booking.training_type_id.color
            else:
                # По умолчанию используем цвет типа тренировки или серый
                booking.color = booking.training_type_id.color if booking.training_type_id else 0
    
    # Поля для отслеживания отправленных напоминаний
    reminder_1day_sent = fields.Boolean(
        string='Напоминание за день отправлено',
        default=False,
        help='Отметка о том, что напоминание за день до тренировки было отправлено'
    )
    
    reminder_2hours_sent = fields.Boolean(
        string='Напоминание за 2 часа отправлено',
        default=False,
        help='Отметка о том, что напоминание за 2 часа до тренировки было отправлено'
    )
    
    # Поле для определения, записал ли тренер сам себе
    is_trainer_self_booking = fields.Boolean(
        string='Запись тренера самому себе',
        compute='_compute_is_trainer_self_booking',
        store=True,
        help='Указывает, что запись создана тренером самому себе'
    )
    
    # Финансовые поля
    price_per_hour = fields.Float(
        string='Цена за час',
        compute='_compute_price_per_hour',
        store=True,
        help='Цена за час тренировки (из настроек спортивного центра или типа тренировки)'
    )

    trainer_extra_per_hour = fields.Float(
        string='Надбавка тренера (руб/час)',
        compute='_compute_trainer_extra',
        store=False
    )

    final_price_per_hour = fields.Float(
        string='Итоговая цена за час',
        compute='_compute_trainer_extra',
        store=False
    )
    
    duration_hours = fields.Float(
        string='Продолжительность (часы)',
        related='training_type_id.duration_hours',
        readonly=True,
        help='Продолжительность тренировки в часах'
    )
    
    total_price = fields.Float(
        string='Общая стоимость',
        compute='_compute_total_price',
        store=True,
        help='Общая стоимость тренировки'
    )
    
    # Связанные поля
    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        required=True,
        tracking=True,
        help='Спортивный центр'
    )
    
    # Вычисляемое поле для определения спортивного центра текущего пользователя
    user_sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр пользователя',
        compute='_compute_user_sports_center_id',
        store=False,
        help='Спортивный центр текущего пользователя (для фильтрации)'
    )
    
    # Вычисляемые поля
    customer_balance = fields.Float(
        string='Баланс клиента',
        related='customer_id.balance',
        readonly=True,
        help='Текущий баланс клиента'
    )
    
    # Поле для доступного времени
    available_times = fields.Text(
        string='Доступное время',
        compute='_compute_available_times',
        help='Список доступного времени для выбранного корта и даты'
    )
    
    can_afford = fields.Boolean(
        string='Достаточно средств',
        compute='_compute_can_afford',
        help='Достаточно ли средств у клиента'
    )
    
    has_min_participants = fields.Boolean(
        string='Достаточно участников',
        compute='_compute_has_min_participants',
        store=False,
        help='Достигнуто ли минимальное количество участников'
    )
    
    # Поля для таймеров
    time_until_start = fields.Char(
        string='До начала',
        compute='_compute_time_until_start',
        store=False,
        help='Время до начала тренировки'
    )
    
    time_until_end = fields.Char(
        string='До окончания',
        compute='_compute_time_until_end',
        store=False,
        help='Время до окончания тренировки'
    )
    
    can_confirm = fields.Boolean(
        string='Можно подтвердить',
        compute='_compute_can_confirm',
        store=False,
        help='Можно ли подтвердить запись (достаточно средств и участников)'
    )
    
    can_add_participants = fields.Boolean(
        string='Можно добавить участников',
        compute='_compute_can_add_participants',
        store=False,
        help='Можно ли добавить еще участников (не достигнут максимум)'
    )
    
    selected_participant_ids = fields.Many2many(
        'res.partner',
        string='Выбранные участники',
        compute='_compute_selected_participant_ids',
        store=False,
        help='Список уже выбранных участников (для исключения из домена)'
    )
    
    excluded_participant_ids = fields.Char(
        string='Исключенные участники (ID)',
        compute='_compute_excluded_participant_ids',
        store=False,
        help='Список ID уже выбранных участников для использования в домене'
    )
    
    excluded_participant_ids_list = fields.Char(
        string='Исключенные участники (список ID)',
        compute='_compute_excluded_participant_ids_list',
        store=False,
        help='Список ID уже выбранных участников в формате списка для домена'
    )
    
    excluded_participant_ids_for_domain = fields.Many2many(
        'res.partner',
        string='Исключенные участники для домена',
        compute='_compute_excluded_participant_ids_for_domain',
        store=False,
        help='Список уже выбранных участников для использования в домене'
    )

    # Повторяющиеся тренировки
    is_recurring = fields.Boolean(string='Постоянные занятия')
    recur_months = fields.Integer(string='Сколько месяцев', default=1)
    recur_times_per_week = fields.Integer(string='Раз в неделю', default=1)
    recur_weekday_ids = fields.Many2many('training.weekday', string='Дни недели')
    recur_start_time = fields.Float(string='Время начала (повт.)')
    recur_end_time = fields.Float(string='Время окончания (повт.)')
    recur_total_sessions = fields.Integer(string='Всего занятий', compute='_compute_recurrence_totals', store=False)
    overall_total_price = fields.Float(string='Итоговая сумма', compute='_compute_recurrence_totals', store=False)
    
    # Информация о времени
    start_time_display = fields.Char(
        string='Время начала',
        compute='_compute_time_display',
        help='Время начала в читаемом формате'
    )
    
    end_time_display = fields.Char(
        string='Время окончания',
        compute='_compute_time_display',
        help='Время окончания в читаемом формате'
    )
    
    # Поле для отображения всех участников в календаре
    all_participants_display = fields.Char(
        string='Все участники',
        compute='_compute_all_participants_display',
        help='Список всех участников тренировки для отображения в календаре'
    )
    
    # Поля datetime для календаря (объединяют дату и время)
    booking_datetime_start = fields.Datetime(
        string='Дата и время начала',
        compute='_compute_booking_datetime',
        store=True,
        help='Дата и время начала тренировки для календаря'
    )
    
    booking_datetime_end = fields.Datetime(
        string='Дата и время окончания',
        compute='_compute_booking_datetime',
        store=True,
        help='Дата и время окончания тренировки для календаря'
    )
    
    
    @api.depends('booking_date', 'start_time', 'end_time')
    def _compute_booking_datetime(self):
        """Вычисляет datetime начала и окончания тренировки"""
        for booking in self:
            if booking.booking_date and booking.start_time is not None:
                # Преобразуем float время в часы и минуты
                start_hour = int(booking.start_time)
                start_min = int((booking.start_time - start_hour) * 60)
                booking.booking_datetime_start = datetime.combine(
                    booking.booking_date,
                    datetime.min.time()
                ).replace(hour=start_hour, minute=start_min, second=0)
            else:
                booking.booking_datetime_start = False
            
            if booking.booking_date and booking.end_time is not None:
                # Преобразуем float время в часы и минуты
                end_hour = int(booking.end_time)
                end_min = int((booking.end_time - end_hour) * 60)
                booking.booking_datetime_end = datetime.combine(
                    booking.booking_date,
                    datetime.min.time()
                ).replace(hour=end_hour, minute=end_min, second=0)
            else:
                booking.booking_datetime_end = False
    
    @api.depends('training_type_id', 'training_type_id.category')
    def _compute_is_group_training(self):
        """Вычисляет, является ли тип тренировки групповым"""
        for booking in self:
            if booking.training_type_id:
                # Проверяем категорию типа тренировки
                category = booking.training_type_id.category
                if category == 'group':
                    booking.is_group_training = True
                else:
                    # Fallback: проверяем код и название
                    code = (booking.training_type_id.code or '').strip().upper()
                    name = (booking.training_type_id.name or '').strip().lower()
                    if code in ('GROUP', 'GRP') or 'груп' in name or 'group' in name:
                        booking.is_group_training = True
                    else:
                        booking.is_group_training = False
            else:
                booking.is_group_training = False
    
    @api.depends('sports_center_id', 'training_type_id')
    def _compute_price_per_hour(self):
        """Вычисляет цену за час из настроек спортивного центра или типа тренировки"""
        for booking in self:
            price = 0.0
            # Сначала ищем цену в настройках спортивного центра
            if booking.sports_center_id and booking.training_type_id:
                price_record = self.env['sports.center.training.price'].search([
                    ('sports_center_id', '=', booking.sports_center_id.id),
                    ('training_type_id', '=', booking.training_type_id.id),
                    ('active', '=', True)
                ], limit=1)
                if price_record:
                    price = price_record.price_per_hour
                else:
                    # Если цена не найдена в центре, используем цену из типа тренировки
                    price = booking.training_type_id.price_per_hour or 0.0
            elif booking.training_type_id:
                # Если нет центра, используем цену из типа тренировки
                price = booking.training_type_id.price_per_hour or 0.0
            booking.price_per_hour = price
    
    @api.depends('price_per_hour', 'start_time', 'end_time', 'trainer_extra_per_hour')
    def _compute_total_price(self):
        """Вычисляет общую стоимость на основе времени"""
        for booking in self:
            if booking.start_time and booking.end_time:
                duration = booking.end_time - booking.start_time
                unit = (booking.price_per_hour or 0.0) + (booking.trainer_extra_per_hour or 0.0)
                booking.total_price = unit * duration
            else:
                booking.total_price = 0.0

    @api.depends('trainer_id', 'training_type_id')
    def _compute_trainer_extra(self):
        for booking in self:
            extra = 0.0
            if booking.trainer_id and booking.training_type_id:
                # 1) Приоритет — явная категория типа тренировки
                category = booking.training_type_id.category
                if category == 'individual':
                    extra = booking.trainer_id.price_extra_individual or 0.0
                elif category == 'split':
                    extra = booking.trainer_id.price_extra_split or 0.0
                elif category == 'group':
                    extra = booking.trainer_id.price_extra_group or 0.0
                else:
                    # 2) Fallback по коду
                    code = (booking.training_type_id.code or '').strip().upper()
                    name = (booking.training_type_id.name or '').strip().lower()
                    if code in ('INDIVIDUAL', 'IND'):
                        extra = booking.trainer_id.price_extra_individual or 0.0
                    elif code in ('SPLIT', 'PAIR'):
                        extra = booking.trainer_id.price_extra_split or 0.0
                    elif code in ('GROUP', 'GRP'):
                        extra = booking.trainer_id.price_extra_group or 0.0
                    else:
                        # 3) Fallback по названию (рус/англ, регистронезависимо)
                        if 'инд' in name or 'individual' in name:
                            extra = booking.trainer_id.price_extra_individual or 0.0
                        elif 'сплит' in name or 'split' in name or 'парн' in name:
                            extra = booking.trainer_id.price_extra_split or 0.0
                        elif 'груп' in name or 'group' in name:
                            extra = booking.trainer_id.price_extra_group or 0.0
            booking.trainer_extra_per_hour = extra
            booking.final_price_per_hour = (booking.price_per_hour or 0.0) + extra
    
    @api.depends('customer_balance', 'total_price', 'participant_count', 'additional_participants', 'additional_participants.participant_id', 'training_type_id')
    def _compute_can_afford(self):
        """Проверяет, достаточно ли средств у всех участников"""
        for booking in self:
            # Определяем, является ли тренировка сплит или групповой
            is_split_or_group = False
            if booking.training_type_id:
                category = booking.training_type_id.category
                if category in ('split', 'group'):
                    is_split_or_group = True
                elif category not in ('individual',):
                    # Fallback: проверяем по коду и названию
                    code = (booking.training_type_id.code or '').strip().upper()
                    name = (booking.training_type_id.name or '').strip().lower()
                    if code in ('SPLIT', 'PAIR', 'GROUP', 'GRP') or \
                       'сплит' in name or 'split' in name or 'парн' in name or \
                       'груп' in name or 'group' in name:
                        is_split_or_group = True
                # Также проверяем по количеству участников
                if booking.participant_count > 1:
                    is_split_or_group = True
            
            # Собираем всех участников
            all_participants = []
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок берем участников из группы
                all_participants = list(booking.group_id.participant_ids)
            else:
                # Для негрупповых тренировок берем основного клиента и дополнительных участников
                if booking.customer_id:
                    all_participants.append(booking.customer_id)
                
                # Добавляем дополнительных участников
                for participant in booking.additional_participants:
                    if participant.participant_id:
                        all_participants.append(participant.participant_id)
            
            if not all_participants:
                booking.can_afford = False
                continue
            
            # Для групповых тренировок каждый участник платит полную стоимость
            if booking.is_group_training and booking.group_id:
                # Каждый участник группы должен иметь полную стоимость на балансе
                booking.can_afford = all(
                    participant.balance >= booking.total_price 
                    for participant in all_participants
                )
            # Для сплит тренировок делим стоимость между участниками
            elif is_split_or_group and len(all_participants) > 1:
                price_per_participant = booking.total_price / len(all_participants)
                booking.can_afford = all(
                    participant.balance >= price_per_participant 
                    for participant in all_participants
                )
            else:
                # Для индивидуальных тренировок проверяем только основного клиента
                if booking.customer_id:
                    booking.can_afford = booking.customer_balance >= booking.total_price
                else:
                    booking.can_afford = False
    
    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'training_type_id', 'additional_participants', 'is_group_training')
    def _compute_has_min_participants(self):
        """Проверяет, достигнуто ли минимальное количество участников"""
        for booking in self:
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок проверяем участников группы
                total_participants = len(booking.group_id.participant_ids)
                if booking.training_type_id:
                    booking.has_min_participants = total_participants >= booking.training_type_id.min_participants
                else:
                    booking.has_min_participants = total_participants > 0
            elif booking.training_type_id and booking.training_type_id.min_participants > 1:
                # Считаем только участников с заполненным participant_id
                filled_participants = len(booking.additional_participants.filtered('participant_id'))
                # Основной клиент всегда считается (если он выбран)
                has_main_customer = 1 if booking.customer_id else 0
                total_participants = has_main_customer + filled_participants
                booking.has_min_participants = total_participants >= booking.training_type_id.min_participants
            else:
                # Для индивидуальных тренировок всегда достаточно участников (если есть основной клиент)
                booking.has_min_participants = bool(booking.customer_id)
    
    @api.depends('can_afford', 'has_min_participants', 'state')
    def _compute_can_confirm(self):
        """Проверяет, можно ли подтвердить запись"""
        for booking in self:
            booking.can_confirm = (
                booking.state == 'draft' and
                booking.can_afford and
                booking.has_min_participants
            )
    
    @api.depends('customer_id', 'training_type_id', 'training_type_id.max_participants', 'additional_participants', 'additional_participants.participant_id', 'participant_count', 'is_group_training', 'group_id')
    def _compute_can_add_participants(self):
        """Проверяет, можно ли добавить еще участников"""
        for booking in self:
            # Для групповых тренировок участники уже определены в группе, нельзя добавлять дополнительных
            if booking.is_group_training and booking.group_id:
                booking.can_add_participants = False
                continue
                
            if not booking.training_type_id:
                booking.can_add_participants = True
                continue
                
            if booking.training_type_id.max_participants > 0:
                # Используем participant_count для более точного подсчета
                current_count = booking.participant_count
                # Проверяем, не достигнут ли максимум (строго меньше)
                booking.can_add_participants = current_count < booking.training_type_id.max_participants
            else:
                # Если максимум не задан, можно добавлять
                booking.can_add_participants = True
    
    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'additional_participants', 'additional_participants.participant_id', 'is_group_training')
    def _compute_selected_participant_ids(self):
        """Вычисляет список уже выбранных участников для исключения из домена"""
        for booking in self:
            selected = self.env['res.partner']
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок добавляем всех участников группы
                selected |= booking.group_id.participant_ids
            else:
                # Добавляем основного клиента
                if booking.customer_id:
                    selected |= booking.customer_id
                # Добавляем всех дополнительных участников
                if booking.additional_participants:
                    selected |= booking.additional_participants.mapped('participant_id')
            booking.selected_participant_ids = selected
    
    @api.onchange('additional_participants', 'customer_id', 'training_type_id')
    def _onchange_participants(self):
        """Обновляет вычисляемые поля при изменении участников"""
        # Не вызываем вычисляемые поля вручную - они автоматически пересчитываются через @api.depends
        # Это предотвращает циклические зависимости и зависания
        pass
    
    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'additional_participants', 'additional_participants.participant_id', 'is_group_training')
    def _compute_excluded_participant_ids(self):
        """Вычисляет строку с ID исключенных участников для использования в домене"""
        for booking in self:
            excluded_ids = []
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок добавляем всех участников группы
                excluded_ids.extend(booking.group_id.participant_ids.ids)
            else:
                # Добавляем ID основного клиента
                if booking.customer_id:
                    excluded_ids.append(booking.customer_id.id)
                # Добавляем ID всех дополнительных участников
                if booking.additional_participants:
                    excluded_ids.extend(booking.additional_participants.mapped('participant_id').ids)
            # Преобразуем в строку для использования в домене
            booking.excluded_participant_ids = ','.join(map(str, excluded_ids)) if excluded_ids else ''
    
    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'additional_participants', 'additional_participants.participant_id', 'is_group_training')
    def _compute_excluded_participant_ids_list(self):
        """Вычисляет список ID исключенных участников в формате для домена"""
        for booking in self:
            excluded_ids = []
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок добавляем всех участников группы
                excluded_ids.extend(booking.group_id.participant_ids.ids)
            else:
                # Добавляем ID всех дополнительных участников
                if booking.additional_participants:
                    excluded_ids.extend(booking.additional_participants.mapped('participant_id').ids)
            # Преобразуем в строку формата [1, 2, 3] для использования в домене
            # Если список пустой, возвращаем пустую строку, которая будет правильно обработана
            booking.excluded_participant_ids_list = str(excluded_ids) if excluded_ids else '[]'
    
    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'additional_participants', 'additional_participants.participant_id', 'is_group_training')
    def _compute_excluded_participant_ids_for_domain(self):
        """Вычисляет список исключенных участников для использования в домене"""
        for booking in self:
            excluded = self.env['res.partner']
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок добавляем всех участников группы
                excluded |= booking.group_id.participant_ids
            else:
                # Добавляем всех дополнительных участников (основной клиент не добавляем, так как он уже выбран в customer_id)
                if booking.additional_participants:
                    excluded |= booking.additional_participants.mapped('participant_id')
            booking.excluded_participant_ids_for_domain = excluded
    
    @api.depends()
    def _compute_user_sports_center_id(self):
        """Вычисляет спортивный центр текущего пользователя"""
        user = self.env.user
        # Проверяем, является ли пользователь директором
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        
        # Если директор - не ограничиваем (поле будет пустым, что означает все центры)
        if is_director:
            for booking in self:
                booking.user_sports_center_id = False
            return
        
        # Получаем сотрудника пользователя
        employee = user.employee_id
        if not employee:
            # Пробуем найти сотрудника по user_id
            employee = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
        
        # Если сотрудник найден и у него есть спортивный центр
        if employee and employee.sports_center_id:
            for booking in self:
                booking.user_sports_center_id = employee.sports_center_id.id
        else:
            for booking in self:
                booking.user_sports_center_id = False
    
    @api.depends('court_id', 'booking_date', 'trainer_id', 'sports_center_id')
    def _compute_available_times(self):
        """Вычисляет доступное время для корта на дату, с учётом доступности тренера"""
        for booking in self:
            if booking.court_id and booking.booking_date:
                times = self.get_available_times(booking.court_id.id, booking.booking_date, booking.trainer_id.id, booking.sports_center_id.id)
                booking.available_times = ', '.join([time['label'] for time in times]) if times else ''
            else:
                booking.available_times = ''
    
    @api.depends('start_time', 'end_time')
    def _compute_time_display(self):
        """Вычисляет отображаемое время"""
        for booking in self:
            # Время начала
            start_hour = int(booking.start_time)
            start_min = int((booking.start_time - start_hour) * 60)
            booking.start_time_display = f"{start_hour:02d}:{start_min:02d}"
            
            # Время окончания
            end_hour = int(booking.end_time)
            end_min = int((booking.end_time - end_hour) * 60)
            booking.end_time_display = f"{end_hour:02d}:{end_min:02d}"
    
    @api.depends('booking_date', 'start_time', 'state')
    @api.depends('booking_date', 'start_time', 'state')
    def _compute_time_until_start(self):
        """Вычисляет время до начала тренировки"""
        now = datetime.now()
        today = fields.Date.today()
        
        for booking in self:
            if not booking.booking_date or booking.start_time is None or booking.state != 'confirmed':
                booking.time_until_start = ''
                continue
            
            # Создаем datetime для начала тренировки
            start_hour = int(booking.start_time)
            start_min = int((booking.start_time - start_hour) * 60)
            start_datetime = datetime.combine(booking.booking_date, datetime.min.time()).replace(
                hour=start_hour, minute=start_min, second=0
            )
            
            # Вычисляем разницу
            if start_datetime > now:
                delta = start_datetime - now
                total_seconds = int(delta.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                # Формат: ЧЧ:ММ:СС
                booking.time_until_start = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                # Время начала уже прошло, но статус еще не изменен
                booking.time_until_start = '00:00:00'
    
    @api.depends('booking_date', 'end_time', 'state')
    def _compute_time_until_end(self):
        """Вычисляет время до окончания тренировки"""
        now = datetime.now()
        
        for booking in self:
            if not booking.booking_date or booking.end_time is None or booking.state != 'in_progress':
                booking.time_until_end = ''
                continue
            
            # Создаем datetime для окончания тренировки
            end_hour = int(booking.end_time)
            end_min = int((booking.end_time - end_hour) * 60)
            end_datetime = datetime.combine(booking.booking_date, datetime.min.time()).replace(
                hour=end_hour, minute=end_min, second=0
            )
            
            # Вычисляем разницу
            if end_datetime > now:
                delta = end_datetime - now
                total_seconds = int(delta.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                # Формат: ЧЧ:ММ:СС
                booking.time_until_end = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                # Время окончания уже прошло, но статус еще не изменен
                booking.time_until_end = '00:00:00'
    
    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'additional_participants', 'additional_participants.participant_id', 'is_group_training')
    def _compute_all_participants_display(self):
        """Вычисляет строку со всеми участниками тренировки"""
        for booking in self:
            participants = []
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок добавляем всех участников группы
                participants = booking.group_id.participant_ids.mapped('name')
            else:
                # Добавляем основного клиента
                if booking.customer_id:
                    participants.append(booking.customer_id.name)
                # Добавляем дополнительных участников
                if booking.additional_participants:
                    for participant in booking.additional_participants:
                        if participant.participant_id:
                            participants.append(participant.participant_id.name)
            # Формируем строку
            booking.all_participants_display = ', '.join(participants) if participants else ''

    @api.onchange('start_time', 'end_time', 'is_recurring')
    def _onchange_fill_recur_times(self):
        if self.is_recurring:
            self.recur_start_time = self.start_time
            self.recur_end_time = self.end_time

    def _compute_recurrence_totals(self):
        for booking in self:
            if not booking.is_recurring or booking.recur_months <= 0:
                booking.recur_total_sessions = 1
                booking.overall_total_price = booking.total_price
                continue
            # Собираем даты по выбранным дням недели
            start_date = booking.booking_date
            if not start_date:
                booking.recur_total_sessions = 1
                booking.overall_total_price = booking.total_price
                continue
            end_date = start_date + relativedelta(months=booking.recur_months)
            weekday_codes = [d.code for d in booking.recur_weekday_ids] or [start_date.weekday()]
            # Генерация дней
            count = 0
            current = start_date
            while current < end_date:
                if current.weekday() in weekday_codes:
                    count += 1
                current += timedelta(days=1)
            # Учёт ограничителя «раз в неделю»
            if booking.recur_times_per_week > 0:
                # приблизительная неделя = 7 дней
                weeks = max(1, (end_date - start_date).days // 7)
                count = min(count, weeks * booking.recur_times_per_week)
            booking.recur_total_sessions = max(1, count)
            # Итоговая сумма = цена за одно занятие * количество занятий
            price_one = booking.total_price if booking.total_price else (booking.price_per_hour * max(0.0, (booking.end_time or 0) - (booking.start_time or 0)))
            booking.overall_total_price = price_one * booking.recur_total_sessions

    @api.depends('customer_id', 'group_id', 'group_id.participant_ids', 'additional_participants', 'additional_participants.participant_id', 'is_group_training')
    def _compute_participant_count(self):
        """Вычисляет общее количество участников (основной клиент + дополнительные или участники группы)"""
        for booking in self:
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок считаем участников группы
                booking.participant_count = len(booking.group_id.participant_ids)
            else:
                # Основной клиент всегда считается (если он выбран)
                main_customer = 1 if booking.customer_id else 0
                # Считаем только участников с заполненным participant_id
                additional = len(booking.additional_participants.filtered('participant_id'))
                booking.participant_count = main_customer + additional
    
    @api.constrains('training_type_id', 'additional_participants', 'group_id', 'is_group_training')
    def _check_min_participants(self):
        """Проверяет, что достигнуто минимальное количество участников"""
        for booking in self:
            # Для групповых тренировок участники уже определены в группе, группа сама проверяет лимиты
            if booking.is_group_training and booking.group_id:
                continue
                
            if booking.training_type_id and booking.training_type_id.min_participants > 1:
                main_customer = 1 if booking.customer_id else 0
                filled_participants = len(booking.additional_participants.filtered('participant_id'))
                total_participants = main_customer + filled_participants
                if total_participants < booking.training_type_id.min_participants:
                    raise ValidationError(
                        _('Для типа тренировки "%s" требуется минимум %d участников. '
                          'Текущее количество: %d. Пожалуйста, добавьте еще участников.') % (
                            booking.training_type_id.name,
                            booking.training_type_id.min_participants,
                            total_participants
                        )
                    )
    
    @api.constrains('training_type_id', 'additional_participants', 'customer_id', 'group_id', 'is_group_training')
    def _check_max_participants(self):
        """Проверяет, что не превышено максимальное количество участников и нет дубликатов"""
        for booking in self:
            # Для групповых тренировок участники уже определены в группе, группа сама проверяет лимиты
            if booking.is_group_training and booking.group_id:
                continue
                
            if booking.training_type_id and booking.training_type_id.max_participants > 0:
                main_customer = 1 if booking.customer_id else 0
                filled_participants = len(booking.additional_participants.filtered('participant_id'))
                total_participants = main_customer + filled_participants
                
                if total_participants > booking.training_type_id.max_participants:
                    raise ValidationError(
                        _('Превышен лимит участников для типа тренировки "%s". '
                          'Максимум: %d, указано: %d. '
                          'Пожалуйста, удалите лишних участников.') % (
                            booking.training_type_id.name,
                            booking.training_type_id.max_participants,
                            total_participants
                        )
                    )
                
                # Проверяем дубликаты
                participant_ids = booking.additional_participants.mapped('participant_id').ids
                if len(participant_ids) != len(set(participant_ids)):
                    # Есть дубликаты
                    from collections import Counter
                    duplicates = [pid for pid, count in Counter(participant_ids).items() if count > 1]
                    if duplicates:
                        duplicate_names = self.env['res.partner'].browse(duplicates).mapped('name')
                        raise ValidationError(
                            _('Обнаружены дубликаты участников: %s. Каждый участник может быть добавлен только один раз.') % ', '.join(duplicate_names)
                        )
                
                # Проверяем, что основной клиент не указан как дополнительный участник
                if booking.customer_id:
                    customer_in_additional = booking.customer_id.id in participant_ids
                    if customer_in_additional:
                        raise ValidationError(
                            _('Основной клиент "%s" не может быть указан как дополнительный участник') % booking.customer_id.name
                        )
    
    @api.constrains('training_type_id', 'customer_id', 'group_id', 'is_group_training')
    def _check_customer_or_group(self):
        """Проверяет, что для группового типа выбрана группа, а для негруппового - клиент"""
        for booking in self:
            if not booking.training_type_id:
                continue
            
            # Определяем, является ли тип групповым
            is_group = False
            category = booking.training_type_id.category
            if category == 'group':
                is_group = True
            else:
                # Fallback: проверяем код и название
                code = (booking.training_type_id.code or '').strip().upper()
                name = (booking.training_type_id.name or '').strip().lower()
                if code in ('GROUP', 'GRP') or 'груп' in name or 'group' in name:
                    is_group = True
            
            if is_group:
                # Для группового типа должна быть выбрана группа
                if not booking.group_id:
                    raise ValidationError(
                        _('Для группового типа тренировки "%s" необходимо выбрать группу') % booking.training_type_id.name
                    )
                # Очищаем customer_id, если он был выбран
                if booking.customer_id:
                    booking.customer_id = False
            else:
                # Для негруппового типа должен быть выбран клиент
                if not booking.customer_id:
                    raise ValidationError(
                        _('Для типа тренировки "%s" необходимо выбрать клиента') % booking.training_type_id.name
                    )
                # Очищаем group_id, если он был выбран
                if booking.group_id:
                    booking.group_id = False
    
    @api.depends('create_uid', 'trainer_id')
    def _compute_is_trainer_self_booking(self):
        """Определяет, записал ли тренер сам себе тренировку"""
        for booking in self:
            if not booking.trainer_id or not booking.create_uid:
                booking.is_trainer_self_booking = False
                continue
            
            # Проверяем, является ли создатель записи тренером
            creator = booking.create_uid
            trainer_user = booking.trainer_id.user_id
            
            # Если создатель - это пользователь тренера, то это запись тренера самому себе
            if trainer_user and creator.id == trainer_user.id:
                booking.is_trainer_self_booking = True
            else:
                booking.is_trainer_self_booking = False
    
    @api.model_create_multi
    def create(self, vals_list):
        """Создает записи с автоматической генерацией номера"""
        # Обрабатываем available_booking_date_selection перед созданием
        for vals in vals_list:
            # Если передано available_booking_date_selection, но не booking_date, устанавливаем booking_date
            if 'available_booking_date_selection' in vals and 'booking_date' not in vals:
                if vals.get('available_booking_date_selection'):
                    try:
                        vals['booking_date'] = fields.Date.from_string(vals['available_booking_date_selection'])
                    except (ValueError, TypeError):
                        pass
            # Аналогично для времени
            if 'available_start_time_selection' in vals and 'start_time' not in vals:
                if vals.get('available_start_time_selection'):
                    try:
                        vals['start_time'] = float(vals['available_start_time_selection'])
                    except (ValueError, TypeError):
                        pass
            
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('training.booking') or _('New')
            # Если тренер записывает сам себе, устанавливаем статус draft
            if vals.get('trainer_id'):
                trainer = self.env['hr.employee'].browse(vals['trainer_id'])
                current_user = self.env.user
                if trainer.user_id and trainer.user_id.id == current_user.id:
                    # Это запись тренера самому себе - только статус draft
                    if 'state' not in vals or vals.get('state') not in ['draft', 'cancelled']:
                        vals['state'] = 'draft'
        
        bookings = super().create(vals_list)
        
        # После создания, если нужно, добавляем пустые записи для участников
        # НЕ создаем записи для групповых тренировок - участники определяются в группе
        for booking in bookings:
            # Пропускаем групповые тренировки
            if booking.is_group_training and booking.group_id:
                continue
                
            if booking.training_type_id and booking.training_type_id.min_participants > 1:
                current_count = len(booking.additional_participants.filtered('participant_id'))
                required_count = booking.training_type_id.min_participants - 1
                
                if current_count < required_count:
                    Participant = self.env['training.booking.participant']
                    for i in range(current_count, required_count):
                        Participant.create({
                            'booking_id': booking.id,
                            'sequence': (i + 1) * 10,
                        })
        
        return bookings
    
    def _auto_set_first_available_slot(self):
        """Заполняет первый доступный слот для текущих выбора тренера/даты/центра/корта"""
        if self.court_id and self.booking_date:
            times = self.get_available_times(self.court_id.id, self.booking_date, self.trainer_id.id, self.sports_center_id.id)
            if times:
                first = times[0]['value']
                self.start_time = first
                # если задана продолжительность — выставим окончание автоматически
                duration = self.duration_hours or 1.0
                self.end_time = first + duration
            else:
                # очистим, если нет доступности
                self.start_time = False
                self.end_time = False

    @api.onchange('court_id')
    def _onchange_court_id(self):
        """Автоматически заполняет спортивный центр при выборе корта"""
        if self.court_id and self.court_id.sports_center_id:
            self.sports_center_id = self.court_id.sports_center_id
        self._auto_set_first_available_slot()
    
    @api.onchange('sports_center_id', 'training_type_id')
    def _onchange_price(self):
        """Обновляет цену при изменении спортивного центра или типа тренировки"""
        # Триггерим пересчет цены
        self._compute_price_per_hour()
    
    @api.onchange('training_type_id')
    def _onchange_training_type_participants(self):
        """Очищает список участников при изменении типа тренировки на индивидуальную"""
        # Если тип тренировки изменился на индивидуальную (min_participants == 1), очищаем участников
        if self.training_type_id and self.training_type_id.min_participants == 1:
            self.additional_participants = [(5, 0, 0)]  # Удаляем все записи

    @api.onchange('trainer_id', 'sports_center_id', 'booking_date')
    def _onchange_trainer_center_date(self):
        """При смене тренера/центра/даты сразу подставляем ближайший допустимый слот"""
        self._auto_set_first_available_slot()
    
    @api.constrains('booking_date', 'start_time', 'end_time', 'court_id')
    def _check_booking_conflicts(self):
        """Проверяет конфликты в расписании"""
        for booking in self:
            if booking.state in ['cancelled']:
                continue
                
            # Проверяем пересечения с другими записями на том же корте
            conflicting_bookings = self.search([
                ('court_id', '=', booking.court_id.id),
                ('booking_date', '=', booking.booking_date),
                ('state', 'in', ['confirmed', 'in_progress']),
                ('id', '!=', booking.id),
                '|',
                '&', ('start_time', '<', booking.end_time),
                     ('end_time', '>', booking.start_time),
                '&', ('start_time', '=', booking.start_time),
                     ('end_time', '=', booking.end_time)
            ])
            
            if conflicting_bookings:
                raise ValidationError(
                    _('Время %s-%s уже занято на корте %s') % (
                        booking.start_time_display,
                        booking.end_time_display,
                        booking.court_id.name
                    )
                )
    
    @api.constrains('booking_date', 'start_time', 'court_id')
    def _check_court_availability(self):
        """Проверяет доступность корта в указанное время"""
        for booking in self:
            # Проверяем, что корт работает в это время
            if booking.court_id.state != 'available':
                raise ValidationError(
                    _('Корт %s недоступен') % booking.court_id.name
                )
            
            # Проверяем время работы корта
            if (booking.start_time < booking.court_id.work_start_time or 
                booking.end_time > booking.court_id.work_end_time):
                raise ValidationError(
                    _('Время тренировки выходит за рамки рабочего времени корта (%s)') % 
                    booking.court_id.work_hours
                )
    
    @api.constrains('customer_id', 'total_price')
    def _check_customer_balance(self):
        """Проверяет достаточность средств у клиента"""
        for booking in self:
            if booking.state == 'confirmed' and not booking.can_afford:
                raise ValidationError(
                    _('Недостаточно средств на балансе клиента. Требуется: %s руб., доступно: %s руб.') % 
                    (booking.total_price, booking.customer_balance)
                )
    
    def action_confirm(self):
        """Подтверждает запись и списывает средства"""
        for booking in self:
            # Проверка минимального количества участников
            if not booking.has_min_participants:
                if booking.is_group_training and booking.group_id:
                    participant_count = len(booking.group_id.participant_ids)
                    raise UserError(
                        _('Недостаточно участников для подтверждения записи. '
                          'Для типа тренировки "%s" требуется минимум %d участников. '
                          'Текущее количество в группе: %d. Пожалуйста, добавьте еще участников в группу.') % (
                            booking.training_type_id.name,
                            booking.training_type_id.min_participants,
                            participant_count
                        )
                    )
                else:
                    raise UserError(
                        _('Недостаточно участников для подтверждения записи. '
                          'Для типа тренировки "%s" требуется минимум %d участников. '
                          'Текущее количество: %d. Пожалуйста, добавьте еще участников.') % (
                            booking.training_type_id.name,
                            booking.training_type_id.min_participants,
                            1 + len(booking.additional_participants.filtered('participant_id'))
                        )
                    )

            # Определяем, является ли тренировка сплит или групповой
            is_split_or_group = False
            if booking.training_type_id:
                category = booking.training_type_id.category
                if category in ('split', 'group'):
                    is_split_or_group = True
                elif category not in ('individual',):
                    # Fallback: проверяем по коду и названию
                    code = (booking.training_type_id.code or '').strip().upper()
                    name = (booking.training_type_id.name or '').strip().lower()
                    if code in ('SPLIT', 'PAIR', 'GROUP', 'GRP') or \
                       'сплит' in name or 'split' in name or 'парн' in name or \
                       'груп' in name or 'group' in name:
                        is_split_or_group = True
                # Также проверяем по количеству участников
                if booking.participant_count > 1:
                    is_split_or_group = True

            # Собираем всех участников
            all_participants = []
            if booking.is_group_training and booking.group_id:
                # Для групповых тренировок берем участников из группы
                all_participants = list(booking.group_id.participant_ids)
            else:
                # Для негрупповых тренировок берем основного клиента и дополнительных участников
                if booking.customer_id:
                    all_participants.append(booking.customer_id)
                
                # Добавляем дополнительных участников
                for participant in booking.additional_participants:
                    if participant.participant_id:
                        all_participants.append(participant.participant_id)
            
            if not all_participants:
                raise UserError(_('Не указаны участники тренировки'))

            # Для групповых тренировок каждый участник платит полную стоимость
            if booking.is_group_training and booking.group_id:
                # Проверяем, достаточно ли средств у всех участников группы (каждый должен иметь полную стоимость)
                insufficient_balance_participants = []
                for participant in all_participants:
                    if participant.balance < booking.total_price:
                        insufficient_balance_participants.append(
                            f"{participant.name} (требуется: {booking.total_price:.2f} руб., доступно: {participant.balance:.2f} руб.)"
                        )
                
                if insufficient_balance_participants:
                    raise UserError(
                        _('Недостаточно средств на балансе у следующих участников группы:\n%s') % 
                        '\n'.join(insufficient_balance_participants)
                    )
                
                # Списываем полную стоимость с каждого участника группы
                for participant in all_participants:
                    new_balance = participant.balance - booking.total_price
                    participant.with_context(skip_balance_notification=True).write({'balance': new_balance})
                    participant._notify_balance_change(-booking.total_price)
                    
                    _logger.info(
                        f"Запись {booking.name} подтверждена. "
                        f"Списано {booking.total_price:.2f} руб. с баланса участника группы {participant.name}"
                    )
            # Для сплит тренировок делим стоимость между участниками
            elif is_split_or_group and len(all_participants) > 1:
                # Цена за одного участника
                price_per_participant = booking.total_price / len(all_participants)
                
                # Проверяем, достаточно ли средств у всех участников
                insufficient_balance_participants = []
                for participant in all_participants:
                    if participant.balance < price_per_participant:
                        insufficient_balance_participants.append(
                            f"{participant.name} (требуется: {price_per_participant:.2f} руб., доступно: {participant.balance:.2f} руб.)"
                        )
                
                if insufficient_balance_participants:
                    raise UserError(
                        _('Недостаточно средств на балансе у следующих участников:\n%s') % 
                        '\n'.join(insufficient_balance_participants)
                    )
                
                # Списываем средства с каждого участника
                for participant in all_participants:
                    new_balance = participant.balance - price_per_participant
                    participant.with_context(skip_balance_notification=True).write({'balance': new_balance})
                    participant._notify_balance_change(-price_per_participant)
                    
                    _logger.info(
                        f"Запись {booking.name} подтверждена. "
                        f"Списано {price_per_participant:.2f} руб. с баланса участника {participant.name}"
                    )
            else:
                # Для индивидуальных тренировок списываем с основного клиента всю сумму
                main_customer = booking.customer_id
                if main_customer.balance < booking.total_price:
                    raise UserError(
                        _('Недостаточно средств на балансе клиента. Требуется: %s руб., доступно: %s руб.') % 
                        (booking.total_price, main_customer.balance)
                    )
                
                new_balance = main_customer.balance - booking.total_price
                main_customer.with_context(skip_balance_notification=True).write({'balance': new_balance})
                main_customer._notify_balance_change(-booking.total_price)
                
                _logger.info(
                    f"Запись {booking.name} подтверждена. "
                    f"Списано {booking.total_price} руб. с баланса клиента {main_customer.name}"
                )

            # Подтверждаем запись
            booking.state = 'confirmed'

            # Отправляем клиенту уведомления
            booking._send_booking_confirmation_message()
            
            # Возвращаем действие для закрытия модального окна
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }

    def action_generate_recurrences(self):
        """Создаёт будущие записи по правилам повторов, не создавая дубликат текущей"""
        Booking = self.env['training.booking']
        created = self.browse()
        for booking in self:
            if not booking.is_recurring or not booking.booking_date:
                continue
            start_date = booking.booking_date
            end_date = start_date + relativedelta(months=max(1, booking.recur_months))
            weekday_codes = [d.code for d in booking.recur_weekday_ids] or [start_date.weekday()]
            # используем времена повторов если заданы, иначе текущие
            st = booking.recur_start_time or booking.start_time
            en = booking.recur_end_time or booking.end_time
            # генерация по дням
            week_count = {}
            current = start_date
            while current < end_date:
                if current == start_date:
                    current += timedelta(days=1)
                    continue
                if current.weekday() in weekday_codes:
                    # ограничение по количеству раз в неделю
                    iso_year, iso_week, iso_weekday = current.isocalendar()
                    key = (iso_year, iso_week)
                    week_count[key] = week_count.get(key, 0) + 1
                    if booking.recur_times_per_week and week_count[key] > booking.recur_times_per_week:
                        current += timedelta(days=1)
                        continue
                    vals = {
                        'name': _('New'),
                        'customer_id': booking.customer_id.id,
                        'trainer_id': booking.trainer_id.id,
                        'court_id': booking.court_id.id,
                        'training_type_id': booking.training_type_id.id,
                        'booking_date': current,
                        'start_time': st,
                        'end_time': en,
                        'sports_center_id': booking.sports_center_id.id,
                        'state': 'draft',
                    }
                    created |= Booking.create([vals])
                current += timedelta(days=1)
        return created
    
    def action_start(self):
        """Начинает тренировку"""
        self.state = 'in_progress'
    
    def action_complete(self):
        """Завершает тренировку"""
        self.state = 'completed'
    
    def action_cancel(self):
        """Отменяет запись"""
        # Проверяем права тренера
        user = self.env.user
        is_trainer = user.has_group('tennis_club_management.group_tennis_trainer')
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        is_manager = user.has_group('tennis_club_management.group_tennis_manager')
        
        if is_trainer and not is_director and not is_manager:
            # Тренер может отменить только свои записи со статусом draft
            if self.state != 'draft':
                raise ValidationError(_('Тренер может отменить только записи со статусом "Черновик"'))
        
        if self.state == 'confirmed':
            # Определяем, является ли тренировка сплит или групповой
            is_split_or_group = False
            if self.training_type_id:
                category = self.training_type_id.category
                if category in ('split', 'group'):
                    is_split_or_group = True
                elif category not in ('individual',):
                    # Fallback: проверяем по коду и названию
                    code = (self.training_type_id.code or '').strip().upper()
                    name = (self.training_type_id.name or '').strip().lower()
                    if code in ('SPLIT', 'PAIR', 'GROUP', 'GRP') or \
                       'сплит' in name or 'split' in name or 'парн' in name or \
                       'груп' in name or 'group' in name:
                        is_split_or_group = True
                # Также проверяем по количеству участников
                if self.participant_count > 1:
                    is_split_or_group = True
            
            # Собираем всех участников
            all_participants = []
            if self.is_group_training and self.group_id:
                # Для групповых тренировок берем участников из группы
                all_participants = list(self.group_id.participant_ids)
            else:
                # Для негрупповых тренировок берем основного клиента и дополнительных участников
                if self.customer_id:
                    all_participants.append(self.customer_id)
                
                # Добавляем дополнительных участников
                for participant in self.additional_participants:
                    if participant.participant_id:
                        all_participants.append(participant.participant_id)
            
            # Для групповых тренировок возвращаем полную стоимость каждому участнику
            if self.is_group_training and self.group_id:
                # Возвращаем полную стоимость каждому участнику группы
                for participant in all_participants:
                    participant.balance += self.total_price
                    participant._notify_balance_change(self.total_price)
                    
                    _logger.info(
                        f"Запись {self.name} отменена. "
                        f"Возвращено {self.total_price:.2f} руб. на баланс участника группы {participant.name}"
                    )
            # Для сплит тренировок возвращаем долю каждому участнику
            elif is_split_or_group and len(all_participants) > 1:
                # Цена за одного участника
                price_per_participant = self.total_price / len(all_participants)
                
                # Возвращаем средства каждому участнику
                for participant in all_participants:
                    participant.balance += price_per_participant
                    participant._notify_balance_change(price_per_participant)
                    
                    _logger.info(
                        f"Запись {self.name} отменена. "
                        f"Возвращено {price_per_participant:.2f} руб. на баланс участника {participant.name}"
                    )
            else:
                # Для индивидуальных тренировок возвращаем всю сумму основному клиенту
                if self.customer_id:
                    self.customer_id.balance += self.total_price
                    self.customer_id._notify_balance_change(self.total_price)
                
                _logger.info(
                    f"Запись {self.name} отменена. "
                    f"Возвращено {self.total_price} руб. на баланс клиента {self.customer_id.name}"
                )
        
        self.state = 'cancelled'
    
    def write(self, vals):
        """Переопределяем write для проверки прав на изменение статуса"""
        # Если тренер пытается изменить статус, ограничиваем доступные статусы
        user = self.env.user
        is_trainer = user.has_group('tennis_club_management.group_tennis_trainer')
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        is_manager = user.has_group('tennis_club_management.group_tennis_manager')
        
        if 'state' in vals and is_trainer and not is_director and not is_manager:
            # Тренер может установить только draft или cancelled
            if vals['state'] not in ['draft', 'cancelled']:
                raise ValidationError(_('Тренер может установить только статус "Черновик" или "Отменена". Подтверждение записей доступно только менеджеру.'))
        
        # Сбрасываем флаги напоминаний при изменении даты или времени тренировки
        if 'booking_date' in vals or 'start_time' in vals or 'state' in vals:
            for booking in self:
                # Если дата изменилась или тренировка отменена/завершена, сбрасываем флаги
                if 'booking_date' in vals or (vals.get('state') in ['cancelled', 'completed']):
                    if booking.reminder_1day_sent or booking.reminder_2hours_sent:
                        vals.setdefault('reminder_1day_sent', False)
                        vals.setdefault('reminder_2hours_sent', False)
        
        result = super().write(vals)
        
        # После изменения типа тренировки, если нужно, добавляем пустые записи для участников
        # НЕ создаем записи для групповых тренировок - участники определяются в группе
        if 'training_type_id' in vals or 'group_id' in vals:
            for booking in self:
                # Если тренировка стала групповой, удаляем все пустые записи участников
                if booking.is_group_training and booking.group_id:
                    # Удаляем все записи участников без participant_id
                    empty_participants = booking.additional_participants.filtered(lambda p: not p.participant_id)
                    if empty_participants:
                        empty_participants.unlink()
                    continue
                    
                if booking.training_type_id and booking.training_type_id.min_participants > 1:
                    current_count = len(booking.additional_participants.filtered('participant_id'))
                    required_count = booking.training_type_id.min_participants - 1
                    
                    if current_count < required_count:
                        Participant = self.env['training.booking.participant']
                        for i in range(current_count, required_count):
                            Participant.create({
                                'booking_id': booking.id,
                                'sequence': (i + 1) * 10,
                            })
        
        # Проверяем участников после сохранения (на случай, если изменения были сделаны в списке)
        for booking in self:
            if booking.training_type_id and booking.training_type_id.max_participants > 0:
                # Проверяем лимит
                main_customer = 1 if booking.customer_id else 0
                filled_participants = len(booking.additional_participants.filtered('participant_id'))
                total_participants = main_customer + filled_participants
                
                if total_participants > booking.training_type_id.max_participants:
                    raise ValidationError(
                        _('Превышен лимит участников для типа тренировки "%s". '
                          'Максимум: %d, указано: %d. '
                          'Пожалуйста, удалите лишних участников.') % (
                            booking.training_type_id.name,
                            booking.training_type_id.max_participants,
                            total_participants
                        )
                    )
                
                # Проверяем дубликаты
                participant_ids = booking.additional_participants.mapped('participant_id').ids
                if len(participant_ids) != len(set(participant_ids)):
                    # Есть дубликаты
                    from collections import Counter
                    duplicates = [pid for pid, count in Counter(participant_ids).items() if count > 1]
                    if duplicates:
                        duplicate_names = self.env['res.partner'].browse(duplicates).mapped('name')
                        raise ValidationError(
                            _('Обнаружены дубликаты участников: %s. Каждый участник может быть добавлен только один раз.') % ', '.join(duplicate_names)
                        )
        
        return result
    
    def action_reset_to_draft(self):
        """Возвращает запись в статус черновика"""
        self.state = 'draft'
    
    def action_view_participants(self):
        """Открывает участников тренировки"""
        return {
            'name': _('Участники тренировки'),
            'type': 'ir.actions.act_window',
            'res_model': 'training.booking.participant',
            'view_mode': 'list,form',
            'domain': [('booking_id', '=', self.id)],
            'context': {'default_booking_id': self.id},
        }
    
    def action_group(self):
        """Открывает список записей с группировкой"""
        return {
            'name': _('Записи на тренировки'),
            'type': 'ir.actions.act_window',
            'res_model': 'training.booking',
            'view_mode': 'list,form,calendar',
            'context': {'group_by': 'training_type_id'},
        }

    def _format_time_value(self, value: float) -> str:
        """Форматирует время из float в строку HH:MM."""
        total_minutes = int(round(value * 60))
        hours, minutes = divmod(total_minutes, 60)
        if minutes == 60:
            hours += 1
            minutes = 0
        return f"{hours:02d}:{minutes:02d}"

    def _send_booking_confirmation_message(self):
        """Отправляет клиенту уведомление о подтверждённой тренировке."""
        for booking in self:
            date_str = booking.booking_date.strftime('%d.%m.%Y') if booking.booking_date else '-'
            start = self._format_time_value(booking.start_time) if booking.start_time is not None else '--:--'
            end = self._format_time_value(booking.end_time) if booking.end_time is not None else '--:--'
            training_type = booking.training_type_id.name or 'Тренировка'
            trainer = booking.trainer_id.name or '-'
            center = booking.sports_center_id.name or '-'
            
            # Формируем базовое сообщение
            base_message = (
                "Вы записаны на тренировку!\n"
                f"Дата: {date_str}\n"
                f"Тип: {training_type}\n"
                f"Время: {start} — {end}\n"
                f"Тренер: {trainer}\n"
                f"Спортивный центр: {center}"
            )
            
            # Для групповых тренировок отправляем уведомления всем участникам группы
            if booking.is_group_training and booking.group_id:
                # Добавляем информацию о группе
                group_message = base_message + f"\nГруппа: {booking.group_id.name}"
                
                # Каждый участник платит полную стоимость
                group_message += f"\nСумма к списанию: {booking.total_price:.2f} руб."
                
                # Отправляем уведомления всем участникам группы
                for participant in booking.group_id.participant_ids:
                    if participant.telegram_chat_id:
                        try:
                            participant._send_telegram_message(group_message)
                            _logger.info(
                                f"Отправлено уведомление о подтверждении записи {booking.name} участнику группы {participant.name}"
                            )
                        except Exception as e:
                            _logger.exception(
                                f"Ошибка при отправке уведомления участнику группы {participant.name}: {e}"
                            )
            else:
                # Для негрупповых тренировок отправляем уведомление основному клиенту
                partner = booking.customer_id
                if partner and partner.telegram_chat_id:
                    try:
                        partner._send_telegram_message(base_message)
                        _logger.info(
                            f"Отправлено уведомление о подтверждении записи {booking.name} клиенту {partner.name}"
                        )
                    except Exception as e:
                        _logger.exception(
                            f"Ошибка при отправке уведомления клиенту {partner.name}: {e}"
                        )
    
    def _send_training_reminder(self, reminder_type='1day'):
        """Отправляет напоминание о предстоящей тренировке клиенту.
        
        :param reminder_type: тип напоминания - '1day' (за день) или '2hours' (за 2 часа)
        """
        for booking in self:
            partner = booking.customer_id
            if not partner or not partner.telegram_chat_id:
                _logger.debug(
                    "Пропуск напоминания для записи %s: у клиента %s нет telegram_chat_id",
                    booking.name,
                    partner.name if partner else 'N/A'
                )
                continue
            
            if booking.state not in ['confirmed', 'in_progress']:
                _logger.debug(
                    "Пропуск напоминания для записи %s: статус %s не подходит для напоминания",
                    booking.name,
                    booking.state
                )
                continue

            date_str = booking.booking_date.strftime('%d.%m.%Y') if booking.booking_date else '-'
            start = self._format_time_value(booking.start_time) if booking.start_time is not None else '--:--'
            end = self._format_time_value(booking.end_time) if booking.end_time is not None else '--:--'
            center = booking.sports_center_id.name or '-'

            if reminder_type == '1day':
                message = (
                    "🔔 Напоминание о тренировке\n\n"
                    f"Завтра у вас тренировка в спортивном центре {center}\n"
                    f"Время: {start} — {end}\n"
                    f"Дата: {date_str}"
                )
            elif reminder_type == '2hours':
                message = (
                    "🔔 Напоминание о тренировке\n\n"
                    f"Через 2 часа у вас тренировка в спортивном центре {center}\n"
                    f"Время: {start} — {end}\n"
                    f"Дата: {date_str}"
                )
            else:
                _logger.warning("Неизвестный тип напоминания: %s", reminder_type)
                continue

            try:
                partner._send_telegram_message(message)
                _logger.info(
                    "Отправлено напоминание %s для записи %s клиенту %s",
                    reminder_type,
                    booking.name,
                    partner.name
                )
                
                # Отмечаем, что напоминание отправлено
                vals = {}
                if reminder_type == '1day':
                    vals['reminder_1day_sent'] = True
                elif reminder_type == '2hours':
                    vals['reminder_2hours_sent'] = True
                
                if vals:
                    booking.write(vals)
                    
            except Exception as e:
                _logger.exception(
                    "Ошибка при отправке напоминания %s для записи %s: %s",
                    reminder_type,
                    booking.name,
                    e
                )
    
    @api.model
    def send_training_reminders(self):
        """Отправляет напоминания о предстоящих тренировках.
        Вызывается cron job'ом периодически.
        """
        today = fields.Date.today()
        tomorrow = today + timedelta(days=1)
        now = datetime.now()
        
        # Напоминания за день до тренировки
        bookings_1day = self.search([
            ('booking_date', '=', tomorrow),
            ('state', 'in', ['confirmed', 'in_progress']),
            ('reminder_1day_sent', '=', False),
        ])
        
        if bookings_1day:
            _logger.info("Найдено %d тренировок для напоминания за день", len(bookings_1day))
            bookings_1day._send_training_reminder('1day')
        
        # Напоминания за 2 часа до тренировки
        # Ищем тренировки на сегодня, где start_time примерно через 2 часа от текущего времени
        current_hour = now.hour + now.minute / 60.0
        target_hour_min = current_hour + 2.0  # Через 2 часа
        target_hour_max = current_hour + 2.5  # Небольшой запас (30 минут)
        
        bookings_2hours = self.search([
            ('booking_date', '=', today),
            ('state', 'in', ['confirmed', 'in_progress']),
            ('reminder_2hours_sent', '=', False),
            ('start_time', '>=', target_hour_min),
            ('start_time', '<=', target_hour_max),
        ])
        
        if bookings_2hours:
            _logger.info("Найдено %d тренировок для напоминания за 2 часа", len(bookings_2hours))
            bookings_2hours._send_training_reminder('2hours')
        
        return True
    
    @api.model
    def auto_update_training_states(self):
        """Автоматически обновляет статусы тренировок на основе текущего времени"""
        now = datetime.now()
        today = fields.Date.today()
        
        # Находим подтвержденные тренировки, которые должны начаться
        confirmed_bookings = self.search([
            ('state', '=', 'confirmed'),
            ('booking_date', '=', today),
        ])
        
        for booking in confirmed_bookings:
            if booking.start_time is not None:
                start_hour = int(booking.start_time)
                start_min = int((booking.start_time - start_hour) * 60)
                start_datetime = datetime.combine(booking.booking_date, datetime.min.time()).replace(
                    hour=start_hour, minute=start_min, second=0
                )
                
                # Если время начала наступило или прошло, меняем статус на "в процессе"
                if now >= start_datetime:
                    booking.state = 'in_progress'
                    _logger.info(f"Автоматически изменен статус тренировки {booking.name} на 'в процессе'")
        
        # Находим тренировки в процессе, которые должны завершиться
        in_progress_bookings = self.search([
            ('state', '=', 'in_progress'),
            ('booking_date', '=', today),
        ])
        
        for booking in in_progress_bookings:
            if booking.end_time is not None:
                end_hour = int(booking.end_time)
                end_min = int((booking.end_time - end_hour) * 60)
                end_datetime = datetime.combine(booking.booking_date, datetime.min.time()).replace(
                    hour=end_hour, minute=end_min, second=0
                )
                
                # Если время окончания наступило или прошло, меняем статус на "завершена"
                if now >= end_datetime:
                    booking.state = 'completed'
                    _logger.info(f"Автоматически изменен статус тренировки {booking.name} на 'завершена'")
        
        return True
    
    @api.model
    def get_available_times(self, court_id, booking_date, trainer_id=False, sports_center_id=False):
        """Возвращает список доступного времени для корта на дату с учётом доступности тренера.
        Возвращаются часовые интервалы.
        """
        if not court_id or not booking_date:
            return []
        # XML-RPC может передавать дату строкой; конвертируем в date
        if isinstance(booking_date, str):
            try:
                booking_date = fields.Date.from_string(booking_date)
            except Exception:
                try:
                    booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
                except Exception:
                    return []
        
        # Получаем корт
        court = self.env['tennis.court'].browse(court_id)
        if not court.exists():
            return []
        
        # Получаем время работы корта
        start_hour = int(court.work_start_time)
        end_hour = int(court.work_end_time)
        
        # Создаем список всех возможных часов (только целые часы)
        available_times = []
        today = fields.Date.today()
        current_hour = None
        
        # Если выбранная дата - сегодня, получаем текущий час
        if booking_date == today:
            now = datetime.now()
            current_hour = now.hour
        
        for hour in range(start_hour, end_hour):
            # Пропускаем прошедшие часы для сегодняшней даты
            if current_hour is not None and hour < current_hour:
                continue
            available_times.append({
                'value': hour,
                'label': f"{hour:02d}:00"
            })
        
        # Получаем занятые времена
        occupied_bookings = self.search([
            ('court_id', '=', court_id),
            ('booking_date', '=', booking_date),
            ('state', 'in', ['confirmed', 'in_progress'])
        ])
        
        occupied_times = set()
        for booking in occupied_bookings:
            # Добавляем все занятые времена (шаг 1 час)
            current_time = int(booking.start_time)  # Округляем до целого часа
            end_time_int = int(booking.end_time) if booking.end_time else current_time + 1
            while current_time < end_time_int:
                occupied_times.add(float(current_time))
                current_time += 1  # 1 час
        
        # Базовые свободные времена (только по занятости корта)
        free_times = [time for time in available_times if time['value'] not in occupied_times]

        # Если указан тренер и спортцентр — пересекаем с его доступностью на этот день
        if trainer_id and sports_center_id:
            Avail = self.env['trainer.availability']
            # Берём доступности, которые пересекаются с выбранным днём
            day_start = datetime.combine(booking_date, datetime.min.time())
            day_end = datetime.combine(booking_date, datetime.max.time())
            availabilities = Avail.search([
                ('employee_id', '=', trainer_id),
                ('sports_center_id', '=', sports_center_id),
                ('start_datetime', '<=', day_end),
                ('end_datetime', '>=', day_start),
            ])

            if not availabilities:
                return []

            allowed_values = set()
            for av in availabilities:
                start_dt = max(av.start_datetime, day_start)
                end_dt = min(av.end_datetime, day_end)
                # Переведём в шаг 1 час как float-значения часов
                current = start_dt
                while current < end_dt:
                    hour_float = current.hour  # Только целые часы
                    allowed_values.add(float(hour_float))
                    current += timedelta(hours=1)  # Шаг 1 час

            free_times = [t for t in free_times if t['value'] in allowed_values]
        
        return free_times

    @api.constrains('booking_date', 'start_time', 'end_time', 'trainer_id', 'sports_center_id')
    def _check_trainer_availability(self):
        """Запретить запись вне интервалов доступности тренера"""
        Avail = self.env['trainer.availability']
        for booking in self:
            if not booking.trainer_id or not booking.sports_center_id:
                continue
            # Построим datetime начала/окончания из даты и float-часов
            start_hour = int(booking.start_time)
            start_min = int((booking.start_time - start_hour) * 60)
            end_hour = int(booking.end_time)
            end_min = int((booking.end_time - end_hour) * 60)
            start_dt = datetime.combine(booking.booking_date, datetime.min.time()).replace(hour=start_hour, minute=start_min, second=0)
            end_dt = datetime.combine(booking.booking_date, datetime.min.time()).replace(hour=end_hour, minute=end_min, second=0)

            avail = Avail.search_count([
                ('employee_id', '=', booking.trainer_id.id),
                ('sports_center_id', '=', booking.sports_center_id.id),
                ('start_datetime', '<=', start_dt),
                ('end_datetime', '>=', end_dt),
            ])
            if avail == 0:
                raise ValidationError(_(
                    'Выбранное время не входит в доступность тренера. Выберите время внутри зелёных интервалов.'
                ))

    
    @api.onchange('trainer_id', 'sports_center_id')
    def _onchange_trainer_for_dates(self):
        """Обновляет опции доступных дат при изменении тренера или центра"""
        if self.trainer_id and self.sports_center_id:
            # Получаем доступные даты
            dates = self.get_trainer_available_dates(
                trainer_id=self.trainer_id.id,
                sports_center_id=self.sports_center_id.id
            )
            
            # Обновляем опции Selection поля через изменение fields_get
            # Это будет обработано через JavaScript патч
            
            # Очищаем выбор, если текущая дата не входит в доступные
            if self.booking_date:
                date_str = fields.Date.to_string(self.booking_date)
                if date_str not in dates:
                    self.booking_date = False
                    self.available_booking_date_selection = False
                elif date_str in dates:
                    # Синхронизируем available_booking_date_selection с booking_date
                    self.available_booking_date_selection = date_str
            else:
                self.available_booking_date_selection = False
        else:
            self.available_booking_date_selection = False
    
    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Переопределяем fields_get для динамического изменения домена полей"""
        res = super().fields_get(allfields=allfields, attributes=attributes)
        
        # Обновляем опции для available_booking_date_selection на основе trainer_id и sports_center_id
        if 'available_booking_date_selection' in res:
            # Пытаемся получить trainer_id и sports_center_id из активной записи
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')
            
            trainer_id = None
            sports_center_id = None
            
            if active_model == 'training.booking' and active_id:
                booking = self.browse(active_id)
                if booking.exists():
                    trainer_id = booking.trainer_id.id if booking.trainer_id else None
                    sports_center_id = booking.sports_center_id.id if booking.sports_center_id else None
            
            # Если не нашли в активной записи, пробуем из контекста
            if not trainer_id:
                trainer_id = self.env.context.get('default_trainer_id')
            if not sports_center_id:
                sports_center_id = self.env.context.get('default_sports_center_id')
            
            if trainer_id and sports_center_id:
                dates = self.get_trainer_available_dates(
                    trainer_id=trainer_id,
                    sports_center_id=sports_center_id
                )
                options = []
                today = fields.Date.today()
                for date_str in dates:
                    date_obj = fields.Date.from_string(date_str)
                    # Пропускаем прошедшие даты
                    if date_obj < today:
                        continue
                    label = date_obj.strftime('%d.%m.%Y')
                    # Добавляем день недели
                    weekday = date_obj.strftime('%A')
                    weekdays = {
                        'Monday': 'Пн',
                        'Tuesday': 'Вт',
                        'Wednesday': 'Ср',
                        'Thursday': 'Чт',
                        'Friday': 'Пт',
                        'Saturday': 'Сб',
                        'Sunday': 'Вс'
                    }
                    weekday_ru = weekdays.get(weekday, weekday)
                    label = f"{label} ({weekday_ru})"
                    options.append((date_str, label))
                
                res['available_booking_date_selection']['selection'] = options
            else:
                res['available_booking_date_selection']['selection'] = []
        
        # Обновляем опции для available_start_time_selection на основе trainer_id, sports_center_id, booking_date и court_id
        if 'available_start_time_selection' in res:
            # Пытаемся получить данные из активной записи
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')
            
            trainer_id = None
            sports_center_id = None
            booking_date = None
            court_id = None
            
            if active_model == 'training.booking' and active_id:
                booking = self.browse(active_id)
                if booking.exists():
                    trainer_id = booking.trainer_id.id if booking.trainer_id else None
                    sports_center_id = booking.sports_center_id.id if booking.sports_center_id else None
                    # Используем booking_date или available_booking_date_selection
                    booking_date = booking.booking_date
                    if not booking_date and booking.available_booking_date_selection:
                        try:
                            booking_date = fields.Date.from_string(booking.available_booking_date_selection)
                        except Exception:
                            booking_date = None
                    court_id = booking.court_id.id if booking.court_id else None
            
            # Если не нашли в активной записи, пробуем из контекста
            if not trainer_id:
                trainer_id = self.env.context.get('default_trainer_id')
            if not sports_center_id:
                sports_center_id = self.env.context.get('default_sports_center_id')
            if not booking_date:
                booking_date = self.env.context.get('default_booking_date')
            if not court_id:
                court_id = self.env.context.get('default_court_id')
            
            if trainer_id and sports_center_id and booking_date and court_id:
                # Конвертируем booking_date если это строка
                if isinstance(booking_date, str):
                    booking_date = fields.Date.from_string(booking_date)
                
                options = self.get_available_start_times(
                    trainer_id=trainer_id,
                    sports_center_id=sports_center_id,
                    booking_date=booking_date,
                    court_id=court_id
                )
                res['available_start_time_selection']['selection'] = options
            else:
                res['available_start_time_selection']['selection'] = []
        
        # Получаем текущего пользователя
        user = self.env.user
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        
        # Если директор - не ограничиваем домен (видит все центры)
        if is_director:
            # Но все равно нужно обновить домен для customer_id, чтобы исключить участников
            self._update_customer_id_domain(res)
            return res
        
        # Для менеджеров и других пользователей ограничиваем домен их спортивным центром
        # Получаем сотрудника пользователя
        employee = user.employee_id
        if not employee:
            employee = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
        
        # Если сотрудник найден и у него есть спортивный центр
        if employee and employee.sports_center_id:
            # Ограничиваем домен только его спортивным центром
            if 'sports_center_id' in res:
                # Сохраняем существующий домен, если он есть, и добавляем наш
                existing_domain = res['sports_center_id'].get('domain', [])
                if existing_domain:
                    # Объединяем домены через AND
                    res['sports_center_id']['domain'] = ['&'] + existing_domain + [('id', '=', employee.sports_center_id.id)]
                else:
                    res['sports_center_id']['domain'] = [('id', '=', employee.sports_center_id.id)]
        
        # Обновляем домен для customer_id, чтобы исключить уже выбранных участников
        self._update_customer_id_domain(res)
        
        return res
    
    @api.model
    def _update_customer_id_domain(self, res):
        """Обновляет домен для customer_id, исключая уже выбранных участников"""
        if 'customer_id' not in res:
            return
        
        # Получаем ID текущей записи из контекста
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        
        # Если это форма записи на тренировку
        if active_model == 'training.booking' and active_id:
            booking = self.browse(active_id)
            if booking.exists():
                # Собираем ID уже выбранных участников
                excluded_ids = []
                # Добавляем ID всех дополнительных участников
                if booking.additional_participants:
                    excluded_ids.extend(booking.additional_participants.mapped('participant_id').ids)
                
                # Обновляем домен, добавляя исключение уже выбранных участников
                if excluded_ids:
                    existing_domain = res['customer_id'].get('domain', [])
                    if existing_domain:
                        # Добавляем исключение к существующему домену
                        # Используем '&' для объединения условий
                        if len(existing_domain) > 0 and existing_domain[0] not in ['&', '|', '!']:
                            # Если домен простой, оборачиваем его
                            new_domain = ['&'] + existing_domain + [('id', 'not in', excluded_ids)]
                        else:
                            # Если домен уже сложный, добавляем условие
                            new_domain = existing_domain + [('id', 'not in', excluded_ids)]
                        res['customer_id']['domain'] = new_domain
                    else:
                        res['customer_id']['domain'] = [('id', 'not in', excluded_ids)]
    
    @api.model
    def get_trainer_unavailable_dates(self, trainer_id=False, sports_center_id=False, start_date=False, end_date=False):
        """Возвращает список дат, когда тренер не работает (нет доступности).
        
        :param trainer_id: ID тренера
        :param sports_center_id: ID спортивного центра
        :param start_date: Начальная дата для проверки (по умолчанию - текущая дата)
        :param end_date: Конечная дата для проверки (по умолчанию - через 3 месяца)
        :return: Список дат в формате строк 'YYYY-MM-DD'
        """
        if not trainer_id or not sports_center_id:
            return []
        
        # Устанавливаем диапазон дат по умолчанию
        if not start_date:
            start_date = fields.Date.today()
        if not end_date:
            end_date = start_date + relativedelta(months=3)
        
        # Конвертируем строки в date объекты, если нужно
        if isinstance(start_date, str):
            start_date = fields.Date.from_string(start_date)
        if isinstance(end_date, str):
            end_date = fields.Date.from_string(end_date)
        
        # Получаем все доступности тренера в указанном диапазоне
        Avail = self.env['trainer.availability']
        availabilities = Avail.search([
            ('employee_id', '=', trainer_id),
            ('sports_center_id', '=', sports_center_id),
            ('start_datetime', '<=', datetime.combine(end_date, datetime.max.time())),
            ('end_datetime', '>=', datetime.combine(start_date, datetime.min.time())),
        ])
        
        # Собираем все даты, когда тренер работает
        working_dates = set()
        for avail in availabilities:
            # Извлекаем все даты из интервала доступности
            current_date = avail.start_datetime.date()
            end_avail_date = avail.end_datetime.date()
            while current_date <= end_avail_date:
                if start_date <= current_date <= end_date:
                    working_dates.add(current_date)
                current_date += timedelta(days=1)
        
        # Генерируем все даты в диапазоне
        all_dates = set()
        current = start_date
        while current <= end_date:
            all_dates.add(current)
            current += timedelta(days=1)
        
        # Находим даты, когда тренер НЕ работает
        unavailable_dates = all_dates - working_dates
        
        # Возвращаем список дат в формате строк
        return [fields.Date.to_string(date) for date in sorted(unavailable_dates)]
    
    @api.model
    def get_trainer_available_dates(self, trainer_id=False, sports_center_id=False, start_date=False, end_date=False):
        """Возвращает список дат, когда тренер работает (есть доступность).
        
        :param trainer_id: ID тренера
        :param sports_center_id: ID спортивного центра
        :param start_date: Начальная дата для проверки (по умолчанию - текущая дата)
        :param end_date: Конечная дата для проверки (по умолчанию - через 3 месяца)
        :return: Список дат в формате строк 'YYYY-MM-DD'
        """
        if not trainer_id or not sports_center_id:
            return []
        
        # Устанавливаем диапазон дат по умолчанию
        if not start_date:
            start_date = fields.Date.today()
        if not end_date:
            end_date = start_date + relativedelta(months=3)
        
        # Конвертируем строки в date объекты, если нужно
        if isinstance(start_date, str):
            start_date = fields.Date.from_string(start_date)
        if isinstance(end_date, str):
            end_date = fields.Date.from_string(end_date)
        
        # Получаем все доступности тренера в указанном диапазоне
        Avail = self.env['trainer.availability']
        availabilities = Avail.search([
            ('employee_id', '=', trainer_id),
            ('sports_center_id', '=', sports_center_id),
            ('start_datetime', '<=', datetime.combine(end_date, datetime.max.time())),
            ('end_datetime', '>=', datetime.combine(start_date, datetime.min.time())),
        ])
        
        # Собираем все даты, когда тренер работает
        working_dates = set()
        for avail in availabilities:
            # Извлекаем все даты из интервала доступности
            current_date = avail.start_datetime.date()
            end_avail_date = avail.end_datetime.date()
            while current_date <= end_avail_date:
                if start_date <= current_date <= end_date:
                    working_dates.add(current_date)
                current_date += timedelta(days=1)
        
        # Возвращаем список дат в формате строк
        return [fields.Date.to_string(date) for date in sorted(working_dates)]
    
    @api.model
    def _get_available_dates_selection(self):
        """Возвращает список опций для выбора даты из доступных дат тренера"""
        # Этот метод вызывается для получения опций Selection поля
        # Реальные опции будут обновляться через fields_get на основе trainer_id и sports_center_id
        return []
    
    @api.model
    def _get_available_times_selection(self):
        """Возвращает список опций для выбора времени начала из доступных часов тренера"""
        # Этот метод вызывается для получения опций Selection поля
        # Реальные опции будут обновляться через fields_get на основе trainer_id, sports_center_id, booking_date и court_id
        return []
    
    @api.model
    def get_available_start_times(self, trainer_id=False, sports_center_id=False, booking_date=False, court_id=False):
        """Возвращает список доступных часов начала тренировки для тренера на дату"""
        if not trainer_id or not sports_center_id or not booking_date or not court_id:
            return []
        
        # Конвертируем booking_date если это строка
        if isinstance(booking_date, str):
            try:
                booking_date = fields.Date.from_string(booking_date)
            except Exception:
                try:
                    booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
                except Exception:
                    return []
        
        # Используем существующий метод get_available_times
        available_times = self.get_available_times(
            court_id=court_id,
            booking_date=booking_date,
            trainer_id=trainer_id,
            sports_center_id=sports_center_id
        )
        
        # Формируем список опций для Selection поля
        options = []
        for time_data in available_times:
            time_value = time_data['value']
            time_label = time_data['label']
            options.append((str(time_value), time_label))
        
        return options
    
    @api.depends('trainer_id', 'sports_center_id', 'booking_date', 'available_booking_date_selection', 'court_id')
    def _compute_available_start_time_selection(self):
        """Вычисляет значение available_start_time_selection на основе start_time"""
        # Пропускаем compute, если значение устанавливается через inverse
        if self.env.context.get('skip_time_selection_compute'):
            return
            
        for booking in self:
            # Для сохраненных записей (с ID) не очищаем значения, если они уже установлены
            # Это предотвращает потерю данных при пересчете
            if booking.id and booking.start_time is not None:
                # Для сохраненных записей только синхронизируем, если available_start_time_selection пусто
                if not booking.available_start_time_selection:
                    time_str = str(booking.start_time)
                    booking.available_start_time_selection = time_str
                # Не очищаем start_time для сохраненных записей
                continue
            
            # Используем booking_date или дату из available_booking_date_selection
            booking_date = booking.booking_date
            if not booking_date and booking.available_booking_date_selection:
                try:
                    booking_date = fields.Date.from_string(booking.available_booking_date_selection)
                except Exception:
                    booking_date = None
            
            # Если значение уже установлено пользователем через выпадающий список, не перезаписываем его
            # Синхронизируем только если значение еще не установлено
            if booking.start_time is not None and booking.trainer_id and booking.sports_center_id and booking_date and booking.court_id:
                time_str = str(booking.start_time)
                # Проверяем, что время входит в доступные времена тренера
                available_times = self.get_available_start_times(
                    trainer_id=booking.trainer_id.id,
                    sports_center_id=booking.sports_center_id.id,
                    booking_date=booking_date,
                    court_id=booking.court_id.id
                )
                available_values = [opt[0] for opt in available_times]
                # Синхронизируем только если значение еще не установлено
                if not booking.available_start_time_selection:
                    if time_str in available_values:
                        booking.available_start_time_selection = time_str
                    else:
                        # Для новых записей можем очистить, если значение невалидно
                        booking.available_start_time_selection = False
                # Если значение уже установлено, проверяем только валидность при изменении зависимых полей
                elif booking.available_start_time_selection not in available_values:
                    # Если выбранное значение больше не доступно (изменился тренер/дата/корт), очищаем только для новых записей
                    if not booking.id:
                        booking.available_start_time_selection = False
            elif not booking.trainer_id or not booking.sports_center_id or not booking_date or not booking.court_id:
                # Если не все поля заполнены, очищаем только если start_time тоже пусто и это новая запись
                if booking.start_time is None and not booking.id:
                    booking.available_start_time_selection = False
    
    def _inverse_available_start_time_selection(self):
        """Устанавливает start_time из available_start_time_selection"""
        for booking in self:
            if booking.available_start_time_selection:
                try:
                    # Устанавливаем start_time с контекстом, чтобы compute не перезаписывал значение
                    booking.with_context(skip_time_selection_compute=True).start_time = float(booking.available_start_time_selection)
                except (ValueError, TypeError) as e:
                    _logger.error(f"Ошибка при установке start_time из available_start_time_selection: {e}")
                    booking.start_time = False
    
    @api.onchange('available_start_time_selection')
    def _onchange_available_start_time_selection(self):
        """Обновляет start_time при изменении available_start_time_selection"""
        if self.available_start_time_selection:
            try:
                self.start_time = float(self.available_start_time_selection)
                # НЕ заполняем end_time автоматически - пользователь должен выбрать его сам
            except (ValueError, TypeError):
                self.start_time = False
    
    @api.depends('trainer_id', 'sports_center_id', 'booking_date')
    def _compute_available_booking_date_selection(self):
        """Вычисляет значение available_booking_date_selection на основе booking_date"""
        for booking in self:
            if booking.booking_date and booking.trainer_id and booking.sports_center_id:
                date_str = fields.Date.to_string(booking.booking_date)
                # Проверяем, что дата входит в доступные даты тренера
                dates = self.get_trainer_available_dates(
                    trainer_id=booking.trainer_id.id,
                    sports_center_id=booking.sports_center_id.id
                )
                if date_str in dates:
                    booking.available_booking_date_selection = date_str
                else:
                    booking.available_booking_date_selection = False
            else:
                booking.available_booking_date_selection = False
    
    def _inverse_available_booking_date_selection(self):
        """Устанавливает booking_date из available_booking_date_selection"""
        for booking in self:
            if booking.available_booking_date_selection:
                try:
                    booking.booking_date = fields.Date.from_string(booking.available_booking_date_selection)
                except (ValueError, TypeError) as e:
                    _logger.error(f"Ошибка при установке booking_date из available_booking_date_selection: {e}")
                    booking.booking_date = False
    
    @api.onchange('available_booking_date_selection')
    def _onchange_available_booking_date_selection(self):
        """Обновляет booking_date при изменении available_booking_date_selection"""
        if self.available_booking_date_selection:
            try:
                self.booking_date = fields.Date.from_string(self.available_booking_date_selection)
            except (ValueError, TypeError):
                self.booking_date = False
    
    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Переопределяем fields_get для динамического изменения опций Selection поля"""
        res = super().fields_get(allfields=allfields, attributes=attributes)
        
        # Обновляем опции для available_booking_date на основе контекста
        if 'available_booking_date' in res:
            # Получаем trainer_id и sports_center_id из контекста или активной записи
            trainer_id = self.env.context.get('default_trainer_id') or self.env.context.get('trainer_id')
            sports_center_id = self.env.context.get('default_sports_center_id') or self.env.context.get('sports_center_id')
            
            if trainer_id and sports_center_id:
                dates = self.get_trainer_available_dates(
                    trainer_id=trainer_id,
                    sports_center_id=sports_center_id
                )
                options = []
                today = fields.Date.today()
                for date_str in dates:
                    date_obj = fields.Date.from_string(date_str)
                    # Пропускаем прошедшие даты
                    if date_obj < today:
                        continue
                    label = date_obj.strftime('%d.%m.%Y')
                    # Добавляем день недели
                    weekday = date_obj.strftime('%A')
                    weekdays = {
                        'Monday': 'Пн',
                        'Tuesday': 'Вт',
                        'Wednesday': 'Ср',
                        'Thursday': 'Чт',
                        'Friday': 'Пт',
                        'Saturday': 'Сб',
                        'Sunday': 'Вс'
                    }
                    weekday_ru = weekdays.get(weekday, weekday)
                    label = f"{label} ({weekday_ru})"
                    options.append((date_str, label))
                
                res['available_booking_date']['selection'] = options
        
        # Получаем текущего пользователя
        user = self.env.user
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        
        # Если директор - не ограничиваем домен (видит все центры)
        if is_director:
            # Но все равно нужно обновить домен для customer_id, чтобы исключить участников
            self._update_customer_id_domain(res)
            return res
        
        # Для менеджеров и других пользователей ограничиваем домен их спортивным центром
        # Получаем сотрудника пользователя
        employee = user.employee_id
        if not employee:
            employee = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)
        
        # Если сотрудник найден и у него есть спортивный центр
        if employee and employee.sports_center_id:
            # Ограничиваем домен только его спортивным центром
            if 'sports_center_id' in res:
                # Сохраняем существующий домен, если он есть, и добавляем наш
                existing_domain = res['sports_center_id'].get('domain', [])
                if existing_domain:
                    # Объединяем домены через AND
                    res['sports_center_id']['domain'] = ['&'] + existing_domain + [('id', '=', employee.sports_center_id.id)]
                else:
                    res['sports_center_id']['domain'] = [('id', '=', employee.sports_center_id.id)]
        
        # Обновляем домен для customer_id, чтобы исключить уже выбранных участников
        self._update_customer_id_domain(res)
        
        return res
    
    @api.model
    def action_open_calendar(self):
        """Возвращает действие календаря в зависимости от группы пользователя"""
        user = self.env.user
        is_manager = user.has_group('tennis_club_management.group_tennis_manager')
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        
        if is_manager or is_director:
            # Для менеджеров и директоров используем календарь с отображением по часам
            return {
                'name': _('Календарь тренировок'),
                'type': 'ir.actions.act_window',
                'res_model': 'training.booking',
                'view_mode': 'calendar',
                'view_id': self.env.ref('tennis_club_management.training_booking_view_calendar_manager').id,
                'target': 'current',
                'context': {'default_state': 'draft', 'default_sports_center_id': 1},
            }
        else:
            # Для тренеров используем обычный календарь
            return {
                'name': _('Календарь тренировок'),
                'type': 'ir.actions.act_window',
                'res_model': 'training.booking',
                'view_mode': 'calendar',
                'view_id': self.env.ref('tennis_club_management.training_booking_view_calendar_main').id,
                'target': 'current',
                'context': {'default_state': 'draft', 'default_sports_center_id': 1},
            }
