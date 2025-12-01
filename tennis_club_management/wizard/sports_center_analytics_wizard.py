# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import date, datetime, timedelta


class SportsCenterAnalyticsWizard(models.TransientModel):
	_name = 'sports.center.analytics.wizard'
	_description = 'Аналитика по спортивному центру'

	sports_center_id = fields.Many2one(
		'sports.center',
		string='Спортивный центр',
		required=True
	)
	date_from = fields.Date(string='Дата с', required=True)
	date_to = fields.Date(string='Дата по', required=True)
	interval = fields.Selection([
		('month', 'Месяц'),
		('custom', 'Произвольный'),
	], string='Интервал', default='month', required=True)

	chart_granularity = fields.Selection([
		('day', 'День'),
		('week', 'Неделя'),
		('month', 'Месяц'),
	], string='Гранулярность графика', default='week', required=True)

	total_bookings = fields.Integer(string='Всего тренировок', readonly=True)
	total_revenue = fields.Float(string='Доход за период', readonly=True)
	most_popular_court_id = fields.Many2one('tennis.court', string='Самый популярный корт', readonly=True)
	most_frequent_customer_id = fields.Many2one('res.partner', string='Самый частый клиент', readonly=True)
	most_profitable_employee_id = fields.Many2one('hr.employee', string='Самый прибыльный сотрудник', readonly=True)
	most_visited_training_type_id = fields.Many2one('training.type', string='Самый посещаемый вид тренировки', readonly=True)
	line_ids = fields.One2many(
		'sports.center.analytics.line',
		'wizard_id',
		string='Доход по неделям',
		readonly=True
	)

	rank_employee_ids = fields.One2many(
		'sports.center.analytics.rank.employee',
		'wizard_id',
		string='Рейтинг сотрудников',
		readonly=True
	)

	rank_court_ids = fields.One2many(
		'sports.center.analytics.rank.court',
		'wizard_id',
		string='Рейтинг кортов',
		readonly=True
	)

	rank_customer_ids = fields.One2many(
		'sports.center.analytics.rank.customer',
		'wizard_id',
		string='Рейтинг клиентов',
		readonly=True
	)

	rank_type_ids = fields.One2many(
		'sports.center.analytics.rank.type',
		'wizard_id',
		string='Рейтинг типов тренировок',
		readonly=True
	)

	@api.model
	def default_get(self, fields_list):
		vals = super().default_get(fields_list)
		today = date.today()
		first_day = today.replace(day=1)
		next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
		last_day = next_month - timedelta(days=1)
		vals.setdefault('date_from', first_day)
		vals.setdefault('date_to', last_day)
		return vals

	def action_recompute(self):
		self.ensure_one()
		booking_env = self.env['training.booking']
		domain = [
			('sports_center_id', '=', self.sports_center_id.id),
			('booking_date', '>=', self.date_from),
			('booking_date', '<=', self.date_to),
			('state', 'in', ['confirmed', 'completed'])
		]
		bookings = booking_env.search(domain)
		self.total_bookings = len(bookings)
		self.total_revenue = sum(bookings.mapped('total_price'))

		# Самый популярный корт
		self.most_popular_court_id = False
		if bookings:
			court_counts = {}
			for b in bookings:
				if b.court_id:
					court_counts[b.court_id] = court_counts.get(b.court_id, 0) + 1
			if court_counts:
				self.most_popular_court_id = max(court_counts, key=court_counts.get)

		# Самый частый клиент
		self.most_frequent_customer_id = False
		if bookings:
			cust_counts = {}
			for b in bookings:
				if b.customer_id:
					cust_counts[b.customer_id] = cust_counts.get(b.customer_id, 0) + 1
			if cust_counts:
				self.most_frequent_customer_id = max(cust_counts, key=cust_counts.get)

		# Самый прибыльный сотрудник (по сумме total_price)
		self.most_profitable_employee_id = False
		if bookings:
			emp_revenue = {}
			for b in bookings:
				if b.trainer_id:
					emp_revenue[b.trainer_id] = emp_revenue.get(b.trainer_id, 0.0) + (b.total_price or 0.0)
			if emp_revenue:
				self.most_profitable_employee_id = max(emp_revenue, key=emp_revenue.get)

		# Самый посещаемый тип тренировки
		self.most_visited_training_type_id = False
		if bookings:
			type_counts = {}
			for b in bookings:
				if b.training_type_id:
					type_counts[b.training_type_id] = type_counts.get(b.training_type_id, 0) + 1
			if type_counts:
				self.most_visited_training_type_id = max(type_counts, key=type_counts.get)

		self.line_ids.unlink()
		if self.date_from and self.date_to:
			gran = self.chart_granularity or 'week'
			bmap = {}
			for b in bookings:
				if not b.booking_date:
					continue
				k = b.booking_date
				if gran == 'week':
					k = k - timedelta(days=k.weekday())
				elif gran == 'month':
					k = k.replace(day=1)
				bmap[k] = bmap.get(k, 0.0) + (b.total_price or 0.0)
			lines = [{
				'wizard_id': self.id,
				'week_start': k,
				'amount': v,
			} for k, v in sorted(bmap.items())]
			self.env['sports.center.analytics.line'].create(lines)

		# Рейтинги
		self.rank_employee_ids.unlink()
		self.rank_court_ids.unlink()
		self.rank_customer_ids.unlink()
		self.rank_type_ids.unlink()
		if bookings:
			# сотрудники
			emp = {}
			for b in bookings:
				if b.trainer_id:
					data = emp.get(b.trainer_id.id, {'employee_id': b.trainer_id.id, 'revenue': 0.0, 'bookings_count': 0})
					data['revenue'] += (b.total_price or 0.0)
					data['bookings_count'] += 1
					emp[b.trainer_id.id] = data
			emp_lines = [{'wizard_id': self.id, **vals} for vals in emp.values()]
			self.env['sports.center.analytics.rank.employee'].create(sorted(emp_lines, key=lambda x: x['revenue'], reverse=True))

			# корты
			crt = {}
			for b in bookings:
				if b.court_id:
					data = crt.get(b.court_id.id, {'court_id': b.court_id.id, 'bookings_count': 0})
					data['bookings_count'] += 1
					crt[b.court_id.id] = data
			crt_lines = [{'wizard_id': self.id, **vals} for vals in crt.values()]
			self.env['sports.center.analytics.rank.court'].create(sorted(crt_lines, key=lambda x: x['bookings_count'], reverse=True))

			# клиенты
			cust = {}
			for b in bookings:
				if b.customer_id:
					data = cust.get(b.customer_id.id, {'customer_id': b.customer_id.id, 'bookings_count': 0})
					data['bookings_count'] += 1
					cust[b.customer_id.id] = data
			cust_lines = [{'wizard_id': self.id, **vals} for vals in cust.values()]
			self.env['sports.center.analytics.rank.customer'].create(sorted(cust_lines, key=lambda x: x['bookings_count'], reverse=True))

			# типы тренировок
			typ = {}
			for b in bookings:
				if b.training_type_id:
					data = typ.get(b.training_type_id.id, {'training_type_id': b.training_type_id.id, 'bookings_count': 0})
					data['bookings_count'] += 1
					typ[b.training_type_id.id] = data
			typ_lines = [{'wizard_id': self.id, **vals} for vals in typ.values()]
			self.env['sports.center.analytics.rank.type'].create(sorted(typ_lines, key=lambda x: x['bookings_count'], reverse=True))

		return {
			'type': 'ir.actions.act_window',
			'res_model': 'sports.center.analytics.wizard',
			'view_mode': 'form',
			'res_id': self.id,
			'target': 'new',
		}

	def action_open(self):
		self.ensure_one()
		self.action_recompute()
		return {
			'type': 'ir.actions.act_window',
			'res_model': 'sports.center.analytics.wizard',
			'view_mode': 'form',
			'res_id': self.id,
			'target': 'new',
		}


class SportsCenterAnalyticsLine(models.TransientModel):
	_name = 'sports.center.analytics.line'
	_description = 'Строка аналитики по неделям'

	wizard_id = fields.Many2one('sports.center.analytics.wizard', string='Мастер', ondelete='cascade')
	week_start = fields.Date(string='Начало периода', index=True)
	amount = fields.Float(string='Доход')


class SportsCenterAnalyticsRankEmployee(models.TransientModel):
	_name = 'sports.center.analytics.rank.employee'
	_description = 'Рейтинг сотрудников по выручке'

	wizard_id = fields.Many2one('sports.center.analytics.wizard', string='Мастер', ondelete='cascade')
	employee_id = fields.Many2one('hr.employee', string='Сотрудник', index=True)
	revenue = fields.Float(string='Выручка')
	bookings_count = fields.Integer(string='Тренировок')


class SportsCenterAnalyticsRankCourt(models.TransientModel):
	_name = 'sports.center.analytics.rank.court'
	_description = 'Рейтинг кортов по посещаемости'

	wizard_id = fields.Many2one('sports.center.analytics.wizard', string='Мастер', ondelete='cascade')
	court_id = fields.Many2one('tennis.court', string='Корт', index=True)
	bookings_count = fields.Integer(string='Тренировок')


class SportsCenterAnalyticsRankCustomer(models.TransientModel):
	_name = 'sports.center.analytics.rank.customer'
	_description = 'Рейтинг клиентов по посещаемости'

	wizard_id = fields.Many2one('sports.center.analytics.wizard', string='Мастер', ondelete='cascade')
	customer_id = fields.Many2one('res.partner', string='Клиент', index=True)
	bookings_count = fields.Integer(string='Тренировок')


class SportsCenterAnalyticsRankType(models.TransientModel):
	_name = 'sports.center.analytics.rank.type'
	_description = 'Рейтинг типов тренировок по посещаемости'

	wizard_id = fields.Many2one('sports.center.analytics.wizard', string='Мастер', ondelete='cascade')
	training_type_id = fields.Many2one('training.type', string='Тип тренировки', index=True)
	bookings_count = fields.Integer(string='Тренировок')

