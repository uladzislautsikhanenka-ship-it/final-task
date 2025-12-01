# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging
from typing import Dict

import requests

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        index=True,
        required=False,
        help='Спортивный центр, с которым связан клиент'
    )
    
    balance = fields.Float(
        string='Баланс',
        default=0.0,
        help='Баланс клиента'
    )
    
    # Связь с заказами (тренировками)
    training_booking_ids = fields.One2many(
        'training.booking',
        'customer_id',
        string='Записи на тренировки',
        help='История записей на тренировки данного клиента'
    )

    telegram_chat_id = fields.Char(
        string='Telegram чат',
        help='Идентификатор чата в Telegram, используемый для уведомлений клиента'
    )
    
    is_employee = fields.Boolean(
        string='Является сотрудником',
        compute='_compute_is_employee',
        store=True,
        help='Проверяет, является ли партнер сотрудником (hr.employee)'
    )
    
    booking_count = fields.Integer(
        string='Количество заказов',
        compute='_compute_booking_count',
        store=False,
        help='Общее количество записей на тренировки'
    )
    
    @api.depends('training_booking_ids')
    def _compute_booking_count(self):
        """Вычисляет количество заказов клиента"""
        for partner in self:
            partner.booking_count = len(partner.training_booking_ids)
    
    def _compute_is_employee(self):
        """Проверяет, является ли партнер сотрудником.

        Аккуратно учитывает разные названия поля домашнего адреса в hr.employee:
        в одних БД это address_home_id, в других — home_address_id.
        """
        # Защита от рекурсии
        if self.env.context.get('skip_is_employee_update'):
            return
        
        Employee = self.env['hr.employee'].sudo()
        has_address_home = 'address_home_id' in Employee._fields
        has_home_address = 'home_address_id' in Employee._fields

        for partner in self:
            domain = [('user_id.partner_id', '=', partner.id)]

            # Добавляем проверку домашнего адреса только если поле реально существует
            if has_address_home:
                domain = ['|'] + domain + [('address_home_id', '=', partner.id)]
            elif has_home_address:
                domain = ['|'] + domain + [('home_address_id', '=', partner.id)]

            employee = Employee.search(domain, limit=1)
            is_emp = bool(employee)
            
            # Используем прямой SQL для обновления, чтобы избежать рекурсии
            if partner.is_employee != is_emp:
                self.env.cr.execute(
                    "UPDATE res_partner SET is_employee = %s WHERE id = %s",
                    (is_emp, partner.id)
                )
                # Инвалидируем кеш
                partner.invalidate_recordset(['is_employee'])
    
    @api.model
    def _update_is_employee_for_all(self):
        """Обновляет поле is_employee для всех партнеров"""
        partners = self.search([])
        partners._compute_is_employee()
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Переопределяем name_search для фильтрации клиентов в контексте выбора участников/клиентов тренировок"""
        args = args or []
        context = self.env.context
        
        # Проверяем домен на наличие фильтров is_employee
        has_is_employee_false = any(
            isinstance(arg, (list, tuple)) and len(arg) == 3 and 
            arg[0] == 'is_employee' and arg[1] == '=' and arg[2] is False
            for arg in args
        )
        has_is_company_false = any(
            isinstance(arg, (list, tuple)) and len(arg) == 3 and 
            arg[0] == 'is_company' and arg[1] == '=' and arg[2] is False
            for arg in args
        )
        has_employee_true = any(
            isinstance(arg, (list, tuple)) and len(arg) == 3 and 
            arg[0] == 'is_employee' and arg[1] == '=' and arg[2] is True
            for arg in args
        )
        
        # Если в домене есть фильтр is_employee=False или is_company=False - применяем фильтрацию
        # Это означает, что домен из модели передан в args
        should_filter_clients = has_is_employee_false or has_is_company_false
        
        # Не фильтруем, если явно указано, что нужны сотрудники или отключена фильтрация
        if has_employee_true or context.get('show_all_partners') or context.get('no_client_filter'):
            should_filter_clients = False
        
        # Проверяем, есть ли уже фильтры в args
        has_is_employee_filter = any(
            isinstance(arg, (list, tuple)) and len(arg) == 3 and arg[0] == 'is_employee' 
            for arg in args
        )
        has_is_company_filter = any(
            isinstance(arg, (list, tuple)) and len(arg) == 3 and arg[0] == 'is_company' 
            for arg in args
        )
        
        # Если нужно фильтровать клиентов, но фильтров нет - добавляем их
        if should_filter_clients:
            if not has_is_employee_filter:
                args.append(('is_employee', '=', False))
            if not has_is_company_filter:
                args.append(('is_company', '=', False))
        
        # Выполняем поиск с обновленными аргументами
        result = super().name_search(name, args, operator, limit)
        
        # ВСЕГДА применяем дополнительную фильтрацию результатов, если нужно фильтровать клиентов
        # Это гарантирует, что даже если домен не сработал, мы отфильтруем результаты
        # Также применяем фильтрацию, если в контексте есть указание на фильтрацию клиентов
        if should_filter_clients or context.get('filter_clients_only'):
            filtered_result = []
            
            # Получаем все ID партнеров из результата
            partner_ids = [item[0] for item in result]
            
            if partner_ids:
                # Проверяем, какие из них являются сотрудниками (прямая проверка в БД)
                Employee = self.env['hr.employee'].sudo()
                has_address_home = 'address_home_id' in Employee._fields
                has_home_address = 'home_address_id' in Employee._fields
                
                # Находим всех сотрудников, связанных с этими партнерами
                # Правильный синтаксис домена для OR: ['|', условие1, условие2]
                employee_domain = []
                if has_address_home:
                    employee_domain = [
                        '|',
                        ('user_id.partner_id', 'in', partner_ids),
                        ('address_home_id', 'in', partner_ids)
                    ]
                elif has_home_address:
                    employee_domain = [
                        '|',
                        ('user_id.partner_id', 'in', partner_ids),
                        ('home_address_id', 'in', partner_ids)
                    ]
                else:
                    employee_domain = [('user_id.partner_id', 'in', partner_ids)]
                
                employees = Employee.search(employee_domain)
                # Получаем ID партнеров, которые являются сотрудниками
                employee_partner_ids = set()
                for emp in employees:
                    if emp.user_id and emp.user_id.partner_id:
                        employee_partner_ids.add(emp.user_id.partner_id.id)
                    if has_address_home and emp.address_home_id:
                        employee_partner_ids.add(emp.address_home_id.id)
                    elif has_home_address and emp.home_address_id:
                        employee_partner_ids.add(emp.home_address_id.id)
                
                # Фильтруем результаты
                for item in result:
                    partner_id = item[0]
                    try:
                        partner = self.browse(partner_id)
                        if partner.exists():
                            # Проверяем, что партнер не является сотрудником и не является компанией
                            is_emp = partner_id in employee_partner_ids
                            is_comp = getattr(partner, 'is_company', False)
                            # Также проверяем, что у партнера есть telegram_chat_id (признак клиента)
                            has_telegram = bool(getattr(partner, 'telegram_chat_id', False))
                            
                            if not is_emp and not is_comp and has_telegram:
                                filtered_result.append(item)
                    except Exception as e:
                        # Если не удалось проверить, пропускаем запись
                        _logger.debug(f"Ошибка при фильтрации партнера {partner_id}: {e}")
                        continue
            
            return filtered_result[:limit] if limit else filtered_result
        
        return result
    
    def action_view_bookings(self):
        """Открывает историю заказов клиента"""
        self.ensure_one()
        return {
            'name': _('История заказов'),
            'type': 'ir.actions.act_window',
            'res_model': 'training.booking',
            'view_mode': 'list,form,calendar',
            'domain': [('customer_id', '=', self.id)],
            'context': {'default_customer_id': self.id, 'search_default_customer_id': self.id},
        }
    
    @api.model
    def _init_balance_field(self):
        """Инициализирует поле balance в базе данных"""
        try:
            # Проверяем, существует ли поле balance
            self.env.cr.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'res_partner' AND column_name = 'balance'
            """)
            
            if not self.env.cr.fetchone():
                _logger.info("Добавляем поле balance в таблицу res_partner...")
                
                # Добавляем поле balance
                self.env.cr.execute("""
                    ALTER TABLE res_partner 
                    ADD COLUMN balance FLOAT DEFAULT 0.0
                """)
                
                # Обновляем существующие записи
                self.env.cr.execute("""
                    UPDATE res_partner 
                    SET balance = 0.0 
                    WHERE balance IS NULL
                """)
                
                self.env.cr.commit()
                _logger.info("Поле balance успешно добавлено в таблицу res_partner")
            else:
                _logger.info("Поле balance уже существует в таблице res_partner")
                
        except Exception as e:
            _logger.error(f"Ошибка при инициализации поля balance: {e}")
            raise

    # -------------------------------------------------------------------------
    # Telegram уведомления
    # -------------------------------------------------------------------------

    def _get_telegram_bot_token(self) -> str:
        """Возвращает токен Telegram бота из настроек системы."""
        return self.env['ir.config_parameter'].sudo().get_param('tennis_club.telegram_bot_token') or ''

    def _get_telegram_api_base_url(self) -> str:
        """Возвращает базовый URL API Telegram."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('tennis_club.telegram_api_base_url')
        return (base_url or 'https://api.telegram.org').rstrip('/')

    def _send_telegram_message(self, message: str) -> None:
        """Отправляет текстовое сообщение клиентам в Telegram.

        :param message: текст сообщения
        """
        if not message:
            _logger.warning("Пустое сообщение, уведомление не отправлено")
            return

        token = self._get_telegram_bot_token()
        if not token:
            _logger.warning("Не настроен токен Telegram бота. Уведомление не отправлено.")
            return

        base_url = self._get_telegram_api_base_url()
        url = f"{base_url}/bot{token}/sendMessage"

        _logger.info("Отправка Telegram сообщения. URL: %s (токен скрыт)", base_url)

        session = requests.Session()

        for partner in self:
            chat_id = partner.telegram_chat_id
            if not chat_id:
                _logger.warning("Партнер %s (%s) не имеет telegram_chat_id, уведомление пропущено.", partner.name, partner.id)
                continue
            
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML',
            }
            
            _logger.info("Отправка сообщения в Telegram для партнера %s (ID: %s, chat_id: %s)", partner.name, partner.id, chat_id)
            
            try:
                response = session.post(url, json=payload, timeout=10)
                if response.ok:
                    _logger.info(
                        "Сообщение успешно отправлено в Telegram для партнера %s (%s). "
                        "Код: %s",
                        partner.name,
                        partner.id,
                        response.status_code,
                    )
                else:
                    _logger.warning(
                        "Не удалось отправить сообщение в Telegram для партнера %s (%s). "
                        "Код: %s, ответ: %s",
                        partner.name,
                        partner.id,
                        response.status_code,
                        response.text,
                    )
            except requests.RequestException as exc:
                _logger.exception(
                    "Ошибка при отправке сообщения в Telegram для партнера %s (%s): %s",
                    partner.name,
                    partner.id,
                    exc,
                )

    def _notify_balance_change(self, diff: float) -> None:
        """Отправляет уведомление клиенту при изменении баланса.

        :param diff: изменение баланса (положительное при пополнении, отрицательное при списании)
        """
        self.ensure_one()
        
        _logger.info(
            "Попытка отправить уведомление об изменении баланса для партнера %s (ID: %s). "
            "diff=%.2f, telegram_chat_id=%s, skip_balance_notification=%s",
            self.name,
            self.id,
            diff,
            self.telegram_chat_id,
            bool(self.env.context.get('skip_balance_notification'))
        )
        
        if not diff:
            _logger.debug("Изменение баланса равно 0, уведомление не отправляется")
            return
            
        if not self.telegram_chat_id:
            _logger.warning(
                "Партнер %s (ID: %s) не имеет telegram_chat_id, уведомление об изменении баланса не отправлено",
                self.name,
                self.id
            )
            return

        if self.env.context.get('skip_balance_notification'):
            _logger.debug("Пропуск уведомления из-за контекста skip_balance_notification")
            return

        amount = abs(diff)
        if diff < 0:
            message = (
                f"С вашего баланса списано {amount:.2f} руб.\n"
                f"Текущий баланс: {self.balance:.2f} руб."
            )
        else:
            message = (
                f"Ваш баланс пополнен на {amount:.2f} руб.\n"
                f"Текущий баланс: {self.balance:.2f} руб."
            )
        
        _logger.info("Отправка сообщения в Telegram для партнера %s (ID: %s): %s", self.name, self.id, message)
        self._send_telegram_message(message)

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)

        for partner, vals in zip(partners, vals_list):
            # Обновляем is_employee для нового партнера, используя контекст для предотвращения рекурсии
            if not self.env.context.get('skip_is_employee_update'):
                partner.with_context(skip_is_employee_update=True)._compute_is_employee()
            
            if 'balance' in vals and partner.telegram_chat_id and abs(partner.balance) >= 1e-6:
                partner._notify_balance_change(partner.balance)
        return partners

    def write(self, vals: Dict):
        # Защита от рекурсии при обновлении is_employee
        if self.env.context.get('skip_is_employee_update'):
            return super().write(vals)
        
        # Не обновляем is_employee, если изменяется само поле is_employee
        if 'is_employee' in vals:
            return super().write(vals)
        
        if self.env.context.get('skip_balance_notification'):
            result = super().write(vals)
            return result

        track_balance = 'balance' in vals
        old_balances = {}
        if track_balance:
            old_balances = {partner.id: partner.balance for partner in self}
            _logger.info(
                "Обнаружено изменение баланса для партнеров: %s. Старые балансы: %s",
                [p.id for p in self],
                old_balances
            )

        result = super().write(vals)
        
        # Обновляем is_employee при изменении партнера (если изменились связанные данные)
        # Но только если это не приведет к рекурсии
        if not self.env.context.get('skip_is_employee_update'):
            if any(key in vals for key in ['name', 'user_id', 'employee_ids']):
                # Используем контекст, чтобы избежать рекурсии
                self.with_context(skip_is_employee_update=True)._compute_is_employee()

        if track_balance:
            for partner in self:
                old_balance = old_balances.get(partner.id)
                if old_balance is None:
                    _logger.debug("Партнер %s (ID: %s) не был в списке старых балансов, пропускаем", partner.name, partner.id)
                    continue
                diff = partner.balance - old_balance
                if abs(diff) < 1e-6:
                    _logger.debug("Изменение баланса для партнера %s (ID: %s) слишком мало (%.6f), пропускаем", partner.name, partner.id, diff)
                    continue
                _logger.info(
                    "Изменение баланса для партнера %s (ID: %s): %.2f -> %.2f (diff=%.2f)",
                    partner.name,
                    partner.id,
                    old_balance,
                    partner.balance,
                    diff
                )
                partner._notify_balance_change(diff)

        return result


