# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import date, timedelta


class FullAnalyticsWizard(models.TransientModel):
	_name = 'full.analytics.wizard'
	_description = 'Полная аналитика по всем центрам'

	# Входные параметры
	sports_center_id = fields.Many2one('sports.center', string='Спортивный центр')
	all_centers = fields.Boolean(string='Все центры')
	date_from = fields.Date(string='Дата с', required=True)
	date_to = fields.Date(string='Дата по', required=True)
	chart_granularity = fields.Selection([
		('day', 'День'),
		('week', 'Неделя'),
		('month', 'Месяц'),
	], string='Гранулярность графика', default='week', required=True)

	# KPI
	total_bookings = fields.Integer(string='Всего тренировок', readonly=True)
	# Под прибылью понимаем доход центра = цена центра (без надбавки тренера) * длительность
	total_revenue = fields.Float(string='Общая прибыль', readonly=True)
	total_expenses = fields.Float(string='Расходы (надбавки тренеров)', readonly=True)
	total_net_profit = fields.Float(string='Чистая прибыль', readonly=True)
	total_employees = fields.Integer(string='Сотрудников', readonly=True)
	total_customers = fields.Integer(string='Клиентов', readonly=True)
	most_frequent_customer_id = fields.Many2one('res.partner', string='Самый частый клиент', readonly=True)
	most_visited_training_type_id = fields.Many2one('training.type', string='Самый посещаемый тип', readonly=True)
	top_employee_id = fields.Many2one('hr.employee', string='Самый востребованный тренер', readonly=True)

	# Линии графика
	line_ids = fields.One2many('full.analytics.line', 'wizard_id', string='Динамика прибыли', readonly=True)

	# Рейтинги
	rank_center_ids = fields.One2many('full.analytics.rank.center', 'wizard_id', string='Выручка по центрам', readonly=True)
	rank_employee_ids = fields.One2many('full.analytics.rank.employee', 'wizard_id', string='Выручка по сотрудникам', readonly=True)
	rank_customer_ids = fields.One2many('full.analytics.rank.customer', 'wizard_id', string='Частые клиенты', readonly=True)
	rank_type_ids = fields.One2many('full.analytics.rank.type', 'wizard_id', string='Популярные типы', readonly=True)
	expense_center_ids = fields.One2many('full.analytics.expense.center', 'wizard_id', string='Расходы по центрам', readonly=True)

	@api.model
	def default_get(self, fields_list):
		vals = super().default_get(fields_list)
		# По умолчанию текущий месяц
		today = date.today()
		first_day = today.replace(day=1)
		next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
		last_day = next_month - timedelta(days=1)
		vals.setdefault('date_from', first_day)
		vals.setdefault('date_to', last_day)
		return vals

	def _booking_profit(self, booking):
		"""Прибыль центра с брони = цена за час (центра) * длительность"""
		duration = 0.0
		if booking.start_time and booking.end_time:
			duration = max(0.0, booking.end_time - booking.start_time)
		price_per_hour = booking.price_per_hour or 0.0
		return price_per_hour * duration
	
	def _booking_expense(self, booking):
		"""Расходы = надбавка тренера * длительность"""
		duration = 0.0
		if booking.start_time and booking.end_time:
			duration = max(0.0, booking.end_time - booking.start_time)
		extra = booking.trainer_extra_per_hour or 0.0
		return extra * duration

	def action_recompute(self):
		self.ensure_one()
		Booking = self.env['training.booking']
		Employee = self.env['hr.employee']
		centers_domain = []
		# Если отмечено "Все центры" или центр не выбран — домен не ограничиваем
		if not self.all_centers and self.sports_center_id:
			centers_domain = [('sports_center_id', '=', self.sports_center_id.id)]
		domain = [('booking_date', '>=', self.date_from),
		          ('booking_date', '<=', self.date_to),
		          ('state', 'in', ['confirmed', 'completed'])]
		if centers_domain:
			domain.extend(centers_domain)
		bookings = Booking.search(domain)

		self.total_bookings = len(bookings)
		total_revenue = 0.0
		total_expenses = 0.0
		center_rev = {}
		center_exp_trainer = {}
		employee_rev = {}
		customer_count = {}
		type_count = {}
		unique_customers = set()
		bmap = {}
		gran = self.chart_granularity or 'week'

		for b in bookings:
			profit = self._booking_profit(b)
			expense = self._booking_expense(b)
			total_revenue += profit
			total_expenses += expense
			if b.sports_center_id:
				center_rev[b.sports_center_id.id] = center_rev.get(b.sports_center_id.id, 0.0) + profit
			if b.trainer_id:
				employee_rev[b.trainer_id.id] = employee_rev.get(b.trainer_id.id, 0.0) + profit
				if b.sports_center_id:
					center_exp_trainer[b.sports_center_id.id] = center_exp_trainer.get(b.sports_center_id.id, 0.0) + expense
			if b.is_group_training and b.group_id:
				for participant in b.group_id.participant_ids:
					if participant.id:
						customer_count[participant.id] = customer_count.get(participant.id, 0) + 1
						unique_customers.add(participant.id)
			else:
				if b.customer_id:
					customer_count[b.customer_id.id] = customer_count.get(b.customer_id.id, 0) + 1
					unique_customers.add(b.customer_id.id)
				for additional in b.additional_participants:
					if additional.participant_id:
						customer_count[additional.participant_id.id] = customer_count.get(additional.participant_id.id, 0) + 1
						unique_customers.add(additional.participant_id.id)
			if b.training_type_id:
				type_count[b.training_type_id.id] = type_count.get(b.training_type_id.id, 0) + 1
			if b.booking_date:
				k = b.booking_date
				if gran == 'week':
					k = k - timedelta(days=k.weekday())
				elif gran == 'month':
					k = k.replace(day=1)
				bmap[k] = bmap.get(k, 0.0) + profit

		self.total_revenue = total_revenue
		self.total_expenses = total_expenses
		self.total_net_profit = total_revenue - total_expenses
		self.line_ids.unlink()
		if bmap:
			lines = [{
				'wizard_id': self.id,
				'period_start': k,
				'amount': v,
			} for k, v in sorted(bmap.items())]
			self.env['full.analytics.line'].create(lines)

		# Рейтинги
		self.rank_center_ids.unlink()
		if center_rev:
			center_lines = [{
				'wizard_id': self.id,
				'sports_center_id': cid,
				'revenue': amt,
			} for cid, amt in center_rev.items()]
			self.env['full.analytics.rank.center'].create(sorted(center_lines, key=lambda x: x['revenue'], reverse=True))

		self.rank_employee_ids.unlink()
		if employee_rev:
			emp_lines = [{
				'wizard_id': self.id,
				'employee_id': eid,
				'revenue': amt,
			} for eid, amt in employee_rev.items()]
			emp_sorted = sorted(emp_lines, key=lambda x: x['revenue'], reverse=True)
			self.env['full.analytics.rank.employee'].create(emp_sorted)
			if emp_sorted:
				self.top_employee_id = emp_sorted[0]['employee_id']
			else:
				self.top_employee_id = False

		self.rank_customer_ids.unlink()
		if customer_count:
			cust_lines = [{
				'wizard_id': self.id,
				'customer_id': pid,
				'bookings_count': cnt,
			} for pid, cnt in customer_count.items()]
			self.env['full.analytics.rank.customer'].create(sorted(cust_lines, key=lambda x: x['bookings_count'], reverse=True))
			# Самый частый клиент
			top_cust_id = max(customer_count, key=customer_count.get)
			self.most_frequent_customer_id = top_cust_id
		else:
			self.most_frequent_customer_id = False

		self.rank_type_ids.unlink()
		if type_count:
			type_lines = [{
				'wizard_id': self.id,
				'training_type_id': tid,
				'bookings_count': cnt,
			} for tid, cnt in type_count.items()]
			self.env['full.analytics.rank.type'].create(sorted(type_lines, key=lambda x: x['bookings_count'], reverse=True))
			# Самый посещаемый тип
			top_type_id = max(type_count, key=type_count.get)
			self.most_visited_training_type_id = top_type_id
		else:
			self.most_visited_training_type_id = False

		# Расчет расходов по зарплатам сотрудников
		self.expense_center_ids.unlink()
		emp_domain = []
		if centers_domain:
			emp_domain = centers_domain
		employees = Employee.search(emp_domain)
		days = (self.date_to - self.date_from).days + 1
		salary_by_center = {}
		for emp in employees:
			if not emp.sports_center_id:
				continue
			month_factor = days / 30.0
			base_month_salary = (emp.work_hours_per_month or 0.0) * (emp.hourly_rate or 0.0)
			if not base_month_salary:
				base_month_salary = emp.monthly_salary or 0.0
			salary = base_month_salary * month_factor
			cid = emp.sports_center_id.id
			salary_by_center[cid] = salary_by_center.get(cid, 0.0) + salary
		all_center_ids = set(list(center_rev.keys()) + list(center_exp_trainer.keys()) + list(salary_by_center.keys()))
		expense_lines = []
		for cid in all_center_ids:
			trainer_extra = center_exp_trainer.get(cid, 0.0)
			salary_exp = salary_by_center.get(cid, 0.0)
			expense_lines.append({
				'wizard_id': self.id,
				'sports_center_id': cid,
				'salary_expense': salary_exp,
				'trainer_extra_expense': trainer_extra,
				'total_expense': salary_exp + trainer_extra,
			})
		if expense_lines:
			self.env['full.analytics.expense.center'].create(expense_lines)
		total_salary_expense = sum(salary_by_center.values()) if salary_by_center else 0.0
		self.total_expenses = (self.total_expenses or 0.0) + total_salary_expense
		self.total_net_profit = (self.total_revenue or 0.0) - (self.total_expenses or 0.0)
		self.total_employees = Employee.search_count(emp_domain + [('active', '=', True)]) if emp_domain else Employee.search_count([('active', '=', True)])
		Partner = self.env['res.partner']
		# Домен для клиентов: не компании, не сотрудники, с telegram_chat_id
		client_domain = [
			('is_company', '=', False),
			('is_employee', '=', False),
			('telegram_chat_id', '!=', False)
		]
		self.total_customers = Partner.search_count(client_domain)

		return {
			'type': 'ir.actions.act_window',
			'res_model': 'full.analytics.wizard',
			'view_mode': 'form',
			'res_id': self.id,
		}

	def action_open(self):
		self.ensure_one()
		self.action_recompute()
		return {
			'type': 'ir.actions.act_window',
			'res_model': 'full.analytics.wizard',
			'view_mode': 'form',
			'res_id': self.id,
		}

	def action_print_pdf(self):
		self.ensure_one()
		Report = self.env['ir.actions.report'].sudo()
		try:
			action = self.env.ref('tennis_club_management.report_full_analytics_pdf')
		except Exception:
			# Если отчёт ещё не зарегистрирован (например, модуль не перезагружен) — создаём определение на лету
			action = Report.search([
				('report_name', '=', 'tennis_club_management.report_full_analytics_template'),
				('model', '=', 'full.analytics.wizard'),
				('report_type', '=', 'qweb-pdf'),
			], limit=1)
			if not action:
				action = Report.create({
					'name': 'Полная аналитика',
					'model': 'full.analytics.wizard',
					'report_type': 'qweb-pdf',
					'report_name': 'tennis_club_management.report_full_analytics_template',
					'report_file': 'tennis_club_management.report_full_analytics_template',
					'print_report_name': "'Полная аналитика - %s' % (object.date_from or '')",
				})
		return action.report_action(self)


class FullAnalyticsLine(models.TransientModel):
	_name = 'full.analytics.line'
	_description = 'Строка полной аналитики (временной ряд)'

	wizard_id = fields.Many2one('full.analytics.wizard', string='Мастер', ondelete='cascade')
	period_start = fields.Date(string='Начало периода', index=True)
	amount = fields.Float(string='Прибыль')


class FullAnalyticsRankCenter(models.TransientModel):
	_name = 'full.analytics.rank.center'
	_description = 'Рейтинг центров по прибыли'

	wizard_id = fields.Many2one('full.analytics.wizard', string='Мастер', ondelete='cascade')
	sports_center_id = fields.Many2one('sports.center', string='Спортивный центр', index=True)
	revenue = fields.Float(string='Прибыль')


class FullAnalyticsRankEmployee(models.TransientModel):
	_name = 'full.analytics.rank.employee'
	_description = 'Рейтинг сотрудников по прибыли'

	wizard_id = fields.Many2one('full.analytics.wizard', string='Мастер', ondelete='cascade')
	employee_id = fields.Many2one('hr.employee', string='Сотрудник', index=True)
	revenue = fields.Float(string='Прибыль')


class FullAnalyticsRankCustomer(models.TransientModel):
	_name = 'full.analytics.rank.customer'
	_description = 'Частые клиенты'

	wizard_id = fields.Many2one('full.analytics.wizard', string='Мастер', ondelete='cascade')
	customer_id = fields.Many2one('res.partner', string='Клиент', index=True)
	bookings_count = fields.Integer(string='Тренировок')


class FullAnalyticsRankType(models.TransientModel):
	_name = 'full.analytics.rank.type'
	_description = 'Популярные типы тренировок'

	wizard_id = fields.Many2one('full.analytics.wizard', string='Мастер', ondelete='cascade')
	training_type_id = fields.Many2one('training.type', string='Тип тренировки', index=True)
	bookings_count = fields.Integer(string='Тренировок')


class FullAnalyticsExpenseCenter(models.TransientModel):
	_name = 'full.analytics.expense.center'
	_description = 'Расходы по центрам'

	wizard_id = fields.Many2one('full.analytics.wizard', string='Мастер', ondelete='cascade')
	sports_center_id = fields.Many2one('sports.center', string='Спортивный центр', index=True)
	salary_expense = fields.Float(string='Зарплаты')
	trainer_extra_expense = fields.Float(string='Доплаты тренерам')
	total_expense = fields.Float(string='Итого расходы')


