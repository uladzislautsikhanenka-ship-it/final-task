# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, date, timedelta


class TrainerAvailability(models.Model):
    _name = 'trainer.availability'
    _description = 'Доступность тренера'
    _order = 'start_datetime'

    name = fields.Char(string='Описание', compute='_compute_name', store=True)

    employee_id = fields.Many2one(
        'hr.employee',
        string='Тренер',
        required=True,
        index=True,
        ondelete='cascade',
        help='Тренер, доступность которого настраивается'
    )

    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        required=True,
        help='Центр, в котором тренер работает в указанный промежуток'
    )

    start_datetime = fields.Datetime(
        string='Начало',
        required=True,
        help='Дата и время начала доступности'
    )

    end_datetime = fields.Datetime(
        string='Окончание',
        required=True,
        help='Дата и время окончания доступности'
    )

    # Поле для окраски записей календаря в зелёный цвет
    color = fields.Integer(string='Цвет', default=10)

    # Дата (для удобной фильтрации, если понадобится)
    availability_date = fields.Date(
        string='День',
        compute='_compute_availability_date',
        store=True
    )

    @api.depends('start_datetime', 'end_datetime', 'sports_center_id')
    def _compute_name(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime:
                start_str = fields.Datetime.to_string(rec.start_datetime)
                end_str = fields.Datetime.to_string(rec.end_datetime)
                center = rec.sports_center_id.display_name if rec.sports_center_id else ''
                rec.name = _('%s — %s (%s)') % (start_str, end_str, center)
            else:
                rec.name = _('Доступность')

    @api.depends('start_datetime')
    def _compute_availability_date(self):
        for rec in self:
            rec.availability_date = rec.start_datetime.date() if rec.start_datetime else False

    @api.constrains('start_datetime', 'end_datetime')
    def _check_time_range(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime and rec.end_datetime <= rec.start_datetime:
                raise ValidationError(_('Окончание должно быть позже начала.'))

    @api.model
    def get_trainer_trainings(self, employee_id):
        """Возвращает тренировки тренера: сегодня и будущие
        
        :param employee_id: ID тренера (hr.employee)
        :return: dict с ключами 'today' и 'upcoming'
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        if not employee_id:
            _logger.warning("[TrainerTrainings] employee_id не передан")
            return {'today': [], 'upcoming': []}
        
        # Проверяем, что employee существует
        employee = self.env['hr.employee'].browse(employee_id)
        if not employee.exists():
            _logger.warning(f"[TrainerTrainings] Employee с ID {employee_id} не найден")
            return {'today': [], 'upcoming': []}
        
        today = date.today()
        
        _logger.info(f"[TrainerTrainings] Поиск тренировок для тренера: {employee.name} (ID: {employee_id}), сегодня: {today}")
        
        # Получаем тренировки тренера
        # Используем ту же логику, что и в виджете заголовка: исключаем только cancelled и completed
        domain = [
            ('trainer_id', '=', employee_id),
            ('booking_date', '>=', today),
            ('state', 'not in', ['cancelled', 'completed'])
        ]
        
        _logger.info(f"[TrainerTrainings] Домен поиска: {domain}")
        
        bookings = self.env['training.booking'].search(domain, order='booking_date, start_time')
        
        _logger.info(f"[TrainerTrainings] Найдено тренировок: {len(bookings)}")
        for booking in bookings:
            _logger.info(f"[TrainerTrainings] - {booking.name}, дата: {booking.booking_date}, статус: {booking.state}")
        
        today_trainings = []
        upcoming_trainings = []
        
        for booking in bookings:
            # Собираем всех участников
            all_participants = []
            
            # Для групповых тренировок участники берутся только из группы
            if booking.is_group_training and booking.group_id:
                # Участники группы
                for participant in booking.group_id.participant_ids:
                    if participant.name:
                        all_participants.append(participant.name)
            else:
                # Для индивидуальных тренировок: основной клиент + дополнительные участники
                if booking.customer_id:
                    all_participants.append(booking.customer_id.name)
                
                # Добавляем дополнительных участников
                for participant in booking.additional_participants:
                    if participant.participant_id:
                        all_participants.append(participant.participant_id.name)
            
            # Формируем строку с участниками
            participants_display = ', '.join(all_participants) if all_participants else 'Не указан'
            
            booking_data = {
                'id': booking.id,
                'name': booking.name,
                'date': fields.Date.to_string(booking.booking_date),
                'date_display': booking.booking_date.strftime('%d.%m.%Y') if booking.booking_date else '',
                'start_time': booking.start_time_display or '',
                'end_time': booking.end_time_display or '',
                'sports_center': booking.sports_center_id.name if booking.sports_center_id else '',
                'court': booking.court_id.name if booking.court_id else '',
                'customer': participants_display,  # Показываем всех участников
                'participant_count': booking.participant_count,  # Количество участников
                'training_type': booking.training_type_id.name if booking.training_type_id else '',
                'state': booking.state,
                'state_display': dict(booking._fields['state'].selection).get(booking.state, ''),
                'is_group_training': booking.is_group_training,  # Флаг групповой тренировки
                'group_id': booking.group_id.id if booking.group_id else None,  # ID группы
                'group_name': booking.group_id.name if booking.group_id else None,  # Название группы
            }
            
            if booking.booking_date == today:
                today_trainings.append(booking_data)
            elif booking.booking_date > today:
                upcoming_trainings.append(booking_data)
        
        # Собираем уникальные даты с тренировками для подсветки в календаре
        training_dates = set()
        for booking in bookings:
            if booking.booking_date:
                training_dates.add(fields.Date.to_string(booking.booking_date))
        
        return {
            'today': today_trainings,
            'upcoming': upcoming_trainings,
            'training_dates': list(training_dates)  # Список дат в формате 'YYYY-MM-DD'
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        
        # Пропускаем пересчет, если установлен контекст skip_hours_recompute
        # (используется при массовом создании для оптимизации)
        if self.env.context.get('skip_hours_recompute'):
            return records
        
        # после создания пересчитываем часы тренера за соответствующий месяц
        # Оптимизация: собираем уникальные комбинации (employee_id, месяц) для избежания дублирования пересчетов
        employee_month_pairs = set()
        for rec in records:
            if rec.employee_id and rec.start_datetime:
                target_date = rec.start_datetime.date()
                # Создаем ключ (employee_id, год, месяц) для группировки
                month_key = (rec.employee_id.id, target_date.year, target_date.month)
                employee_month_pairs.add(month_key)
        
        # Вызываем пересчет один раз для каждой уникальной комбинации
        for emp_id, year, month in employee_month_pairs:
            employee = self.env['hr.employee'].browse(emp_id)
            if employee.exists():
                # Создаем дату первого числа месяца для пересчета
                target_date = date(year, month, 1)
                employee.recompute_hours_from_availability(target_date)
        
        return records

    def write(self, vals):
        res = super().write(vals)
        # пересчитываем часы после изменения
        for rec in self:
            if rec.employee_id:
                target_date = rec.start_datetime.date() if rec.start_datetime else None
                rec.employee_id.recompute_hours_from_availability(target_date)
        return res

    def unlink(self):
        employees = self.mapped('employee_id')
        dates = [r.start_datetime.date() for r in self if r.start_datetime]
        res = super().unlink()
        for emp in employees:
            emp.recompute_hours_from_availability(dates[0] if dates else None)
        return res


