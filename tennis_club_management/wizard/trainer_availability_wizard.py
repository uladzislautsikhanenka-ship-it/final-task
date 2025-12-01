# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, date


class TrainerAvailabilityWizard(models.TransientModel):
    _name = 'trainer.availability.wizard'
    _description = 'Массовое создание доступности тренера'

    employee_id = fields.Many2one('hr.employee', string='Тренер', required=True)
    sports_center_id = fields.Many2one('sports.center', string='Спортивный центр', required=True)
    date_start = fields.Date(string='С какого дня', required=True)
    date_end = fields.Date(string='По какой день', required=True)
    start_time = fields.Float(string='Время начала', required=True)
    end_time = fields.Float(string='Время окончания', required=True)
    weekday_ids = fields.Many2many('training.weekday', string='Дни недели (необязательно)')

    @api.onchange('employee_id')
    def _onchange_employee(self):
        if self.employee_id and self.employee_id.sports_center_id and not self.sports_center_id:
            self.sports_center_id = self.employee_id.sports_center_id

    def action_create(self):
        self.ensure_one()
        if self.date_end < self.date_start:
            raise ValidationError(_('Дата окончания раньше даты начала'))

        # Проверяем, что время окончания больше времени начала
        if self.end_time <= self.start_time:
            raise ValidationError(_('Время окончания должно быть позже времени начала'))

        weekday_filter = {d.code for d in self.weekday_ids} if self.weekday_ids else None
        start_hour = int(self.start_time)
        start_min = int((self.start_time - start_hour) * 60)
        end_hour = int(self.end_time)
        end_min = int((self.end_time - end_hour) * 60)
        vals_list = []
        day = self.date_start
        
        while day <= self.date_end:
            if weekday_filter is None or day.weekday() in weekday_filter:
                start_dt = datetime.combine(day, datetime.min.time()).replace(hour=start_hour, minute=start_min)
                end_dt = datetime.combine(day, datetime.min.time()).replace(hour=end_hour, minute=end_min)

                # Проверяем, что end_dt > start_dt
                if end_dt <= start_dt:
                    continue  # Пропускаем некорректные записи

                vals_list.append({
                    'employee_id': self.employee_id.id,
                    'sports_center_id': self.sports_center_id.id,
                    'start_datetime': start_dt,
                    'end_datetime': end_dt,
                    'color': 10,
                })
            day += timedelta(days=1)
        if vals_list:
            batch_size = 30
            employee_month_pairs = set()
            availability_env = self.env['trainer.availability'].with_context(
                skip_hours_recompute=True,
                tracking_disable=True  # Отключаем отслеживание изменений для ускорения
            )
            
            # Ограничиваем количество записей за один раз для предотвращения истечения сессии
            max_records = 500  # Максимум 500 записей за один вызов
            if len(vals_list) > max_records:
                raise ValidationError(
                    _('Слишком много записей для создания за один раз (%d). '
                      'Пожалуйста, уменьшите диапазон дат. Максимум: %d записей.') % 
                    (len(vals_list), max_records)
                )
            
            for i in range(0, len(vals_list), batch_size):
                batch = vals_list[i:i + batch_size]
                records = availability_env.create(batch)
                for rec in records:
                    if rec.employee_id and rec.start_datetime:
                        target_date = rec.start_datetime.date()
                        month_key = (rec.employee_id.id, target_date.year, target_date.month)
                        employee_month_pairs.add(month_key)
            
            # Пересчитываем часы один раз для всех уникальных комбинаций в конце
            for emp_id, year, month in employee_month_pairs:
                employee = self.env['hr.employee'].browse(emp_id)
                if employee.exists():
                    target_date = date(year, month, 1)
                    employee.recompute_hours_from_availability(target_date)

        return {
            'type': 'ir.actions.act_window_close'
        }




