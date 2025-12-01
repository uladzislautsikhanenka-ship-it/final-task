# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import date, timedelta
from datetime import datetime


def _month_bounds(today: date):
    start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


class TrainerRevenueReportWizard(models.TransientModel):
    _name = 'trainer.revenue.report.wizard'
    _description = 'Отчёт по доходу тренера'

    employee_id = fields.Many2one('hr.employee', string='Тренер', required=True)
    date_start = fields.Date(string='Дата с', required=True, default=lambda self: _month_bounds(date.today())[0])
    date_end = fields.Date(string='Дата по (вкл.)', required=True, default=lambda self: (_month_bounds(date.today())[1] - timedelta(days=1)))

    # Режим быстрый/подробный
    is_simple = fields.Boolean(string='Упрощённый вид', default=lambda self: bool(self.env.context.get('simple_view')))

    total_hours = fields.Float(string='Отработано часов', compute='_compute_totals', store=False)
    total_trainings = fields.Integer(string='Всего тренировок', compute='_compute_totals', store=False)
    total_extra_amount = fields.Float(string='Наценка тренера', compute='_compute_totals', store=False)
    total_center_amount = fields.Float(string='Доход спортивного центра', compute='_compute_totals', store=False, 
                                       help='Доход спортивного центра = Цена занятий - Наценка тренера')
    total_amount = fields.Float(string='Общая сумма тренировок', compute='_compute_totals', store=False)
    count_individual = fields.Integer(string='Индивидуальные', compute='_compute_totals', store=False)
    count_split = fields.Integer(string='Сплит', compute='_compute_totals', store=False)
    count_group = fields.Integer(string='Групповые', compute='_compute_totals', store=False)
    types_summary = fields.Char(string='Виды тренировок', compute='_compute_totals', store=False)
    
    # Новые поля для детализации заработка тренера
    hourly_salary_amount = fields.Float(
        string='Заработано за почасовую ставку', 
        compute='_compute_totals', 
        store=False,
        help='Заработано по почасовой ставке за период'
    )
    training_extra_amount = fields.Float(
        string='Заработано за тренировки (наценки)', 
        compute='_compute_totals', 
        store=False,
        help='Заработано за наценки тренера на тренировки'
    )
    total_earned = fields.Float(
        string='Итого заработано', 
        compute='_compute_totals', 
        store=False,
        help='Итоговая сумма: почасовая ставка + наценки за тренировки'
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.with_context(force_compute=True)._compute_totals()
        return records
    
    def write(self, vals):
        result = super().write(vals)
        if any(field in vals for field in ['employee_id', 'date_start', 'date_end']):
            self._compute_totals()
        return result
    
    @api.onchange('employee_id', 'date_start', 'date_end')
    def _onchange_compute_totals(self):
        self._compute_totals()
    
    @api.depends('employee_id', 'date_start', 'date_end')
    def _compute_totals(self):
        Booking = self.env['training.booking']
        for wiz in self:
            if not wiz.employee_id or not wiz.date_start or not wiz.date_end:
                wiz.total_hours = 0.0
                wiz.total_trainings = 0
                wiz.total_extra_amount = 0.0
                wiz.hourly_salary_amount = 0.0
                wiz.training_extra_amount = 0.0
                wiz.total_earned = 0.0
                continue
            domain = [
                ('trainer_id', '=', wiz.employee_id.id),
                ('booking_date', '>=', wiz.date_start),
                ('booking_date', '<=', wiz.date_end),
                ('state', 'in', ['confirmed', 'in_progress', 'completed']),
            ]
            bookings = Booking.search(domain)
            hours = 0.0
            extra_amount = 0.0
            center_amount = 0.0
            total_amount = 0.0
            c_ind, c_split, c_group = 0, 0, 0
            for b in bookings:
                duration = max(0.0, (b.end_time or 0.0) - (b.start_time or 0.0))
                hours += duration
                extra_amount += (b.trainer_extra_per_hour or 0.0) * duration
                center_amount += (b.price_per_hour or 0.0) * duration
                total_amount += ((b.final_price_per_hour or 0.0)) * duration
                if b.training_type_id:
            
                    category = b.training_type_id.category
                    if category == 'individual':
                        c_ind += 1
                    elif category == 'split':
                        c_split += 1
                    elif category == 'group':
                        c_group += 1
                    else:
                        code = (b.training_type_id.code or '').strip().upper()
                        name = (b.training_type_id.name or '').strip().lower()
                        if code in ('INDIVIDUAL', 'IND'):
                            c_ind += 1
                        elif code in ('SPLIT', 'PAIR'):
                            c_split += 1
                        elif code in ('GROUP', 'GRP'):
                            c_group += 1
                        else:
                            if 'инд' in name or 'individual' in name:
                                c_ind += 1
                            elif 'сплит' in name or 'split' in name or 'парн' in name:
                                c_split += 1
                            elif 'груп' in name or 'group' in name:
                                c_group += 1
            wiz.total_hours = hours
            wiz.total_trainings = len(bookings)
            wiz.total_extra_amount = extra_amount
            wiz.total_center_amount = total_amount - extra_amount if total_amount > 0 else center_amount
            wiz.total_amount = total_amount
            wiz.count_individual = c_ind
            wiz.count_split = c_split
            wiz.count_group = c_group
            wiz.types_summary = (
                f"Индивидуальные: {c_ind}; Сплит: {c_split}; Групповые: {c_group}"
            )
            
            # Расчет заработка тренера
            employee = wiz.employee_id
            if employee:
          
                
                # Границы периода в datetime
                start_dt = datetime.combine(wiz.date_start, datetime.min.time())
                end_dt = datetime.combine(wiz.date_end, datetime.max.time())
                
                # Получаем доступности тренера за период
                availabilities = self.env['trainer.availability'].search([
                    ('employee_id', '=', employee.id),
                    ('start_datetime', '<=', end_dt),
                    ('end_datetime', '>=', start_dt),
                ])
                
                total_hours_in_period = 0.0
                for avail in availabilities:
                    s = max(avail.start_datetime, start_dt)
                    e = min(avail.end_datetime, end_dt)
                    
                    if not s or not e or e <= s:
                        continue
                    daily_hours = (e.time().hour + e.time().minute / 60.0) - (s.time().hour + s.time().minute / 60.0)
                    if daily_hours < 0:
                        daily_hours = 0.0
                    days_count = (e.date() - s.date()).days + 1
                    total_hours_in_period += daily_hours * days_count
                
                hourly_rate = employee.hourly_rate or 1.0
                
                wiz.hourly_salary_amount = total_hours_in_period * hourly_rate
                wiz.training_extra_amount = extra_amount
                wiz.total_earned = wiz.hourly_salary_amount + wiz.training_extra_amount
            else:
                wiz.hourly_salary_amount = 0.0
                wiz.training_extra_amount = 0.0
                wiz.total_earned = 0.0

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('tennis_club_management.report_trainer_revenue_pdf').report_action(self)

    def action_open_detailed(self):
        self.ensure_one()
        self._compute_totals()
        action = self.env.ref('tennis_club_management.action_trainer_revenue_report_wizard').read()[0]
        action['context'] = {
            'default_employee_id': self.employee_id.id,
            'default_date_start': self.date_start,
            'default_date_end': self.date_end,
            'simple_view': False,
        }
        return action
    
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        result = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        return result


