# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

ROLE_PASSWORDS = {
    'manager': 'manager',
    'trainer': 'trainer',
}

SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY = 'skip_employee_role_sync'


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Связь со спортивным центром
    sports_center_id = fields.Many2one(
        'sports.center',
        string='Спортивный центр',
        help='Спортивный центр, в котором работает сотрудник'
    )
    
    # Дополнительные поля для спортивного центра
    work_hours_per_month = fields.Float(
        string='Часы в месяц',
        default=0.0,
        help='Количество рабочих часов в месяц'
    )
    
    hourly_rate = fields.Float(
        string='Почасовая ставка',
        help='Почасовая ставка оплаты',
        default=1.0
    )
    
    # Вычисляемые поля
    monthly_salary = fields.Float(
        string='Зарплата в месяц',
        compute='_compute_monthly_salary',
        store=True,
        help='Зарплата за месяц'
    )
    
    is_manager = fields.Boolean(
        string='Менеджер',
        compute='_compute_is_manager',
        store=True,
        help='Является ли сотрудник менеджером'
    )

    # Доступность тренера (календарь)
    availability_ids = fields.One2many(
        'trainer.availability',
        'employee_id',
        string='Доступность',
        help='Дни и интервалы, когда тренер доступен для работы'
    )

    # Надбавки тренера к цене центра (руб/час) по типам тренировок
    price_extra_individual = fields.Float(string='Надбавка (индивидуальная), руб/час', default=0.0)
    price_extra_split = fields.Float(string='Надбавка (сплит), руб/час', default=0.0)
    price_extra_group = fields.Float(string='Надбавка (групповая), руб/час', default=0.0)
    
    # Кастомное поле должности с ограниченным выбором
    position = fields.Selection([
        ('manager', 'Менеджер'),
        ('trainer', 'Тренер')
    ], string='Должность', required=True, default='trainer',
       help='Должность сотрудника в теннисном клубе')

    @api.depends('work_hours_per_month', 'hourly_rate')
    def _compute_monthly_salary(self):
        """Вычисляет зарплату за месяц"""
        for employee in self:
            employee.monthly_salary = employee.work_hours_per_month * employee.hourly_rate

    def recompute_hours_from_availability(self, target_date=None):
        """Пересчитывает поле work_hours_per_month на основе доступностей тренера за месяц target_date.
        Если target_date не задана — используется текущий месяц."""
        from datetime import date as dt_date, datetime, timedelta
        for emp in self:
            # только для тренеров
            if hasattr(emp, 'position') and emp.position != 'trainer':
                continue
            today = target_date or dt_date.today()
            month_start = today.replace(day=1)
            # конец месяца
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(days=1)
            # границы datetime
            start_dt = datetime.combine(month_start, datetime.min.time())
            end_dt = datetime.combine(month_end, datetime.max.time())
            avails = self.env['trainer.availability'].search([
                ('employee_id', '=', emp.id),
                ('start_datetime', '<=', end_dt),
                ('end_datetime', '>=', start_dt),
            ])
            total_hours = 0.0
            for av in avails:
                # вычисляем часы "в день" и умножаем на количество дней интервала
                s = max(av.start_datetime, start_dt)
                e = min(av.end_datetime, end_dt)
                if not s or not e or e <= s:
                    continue
                # Часы в день считаем по времени начала и окончания (одинаково для всех дней)
                daily_hours = (s.time().hour + s.time().minute / 60.0) - 0.0  # просто заготовка
                daily_hours = (e.time().hour + e.time().minute / 60.0) - (s.time().hour + s.time().minute / 60.0)
                if daily_hours < 0:
                    # На случай, если интервал переходит через полночь — игнорируем
                    daily_hours = 0.0
                # Количество дней
                days_count = (e.date() - s.date()).days + 1
                total_hours += daily_hours * days_count
            emp.work_hours_per_month = total_hours

    def action_recompute_hours(self):
        """Кнопка на форме: пересчитать часы из доступностей текущего месяца"""
        self.recompute_hours_from_availability()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.depends('position')
    def _compute_is_manager(self):
        """Определяет, является ли сотрудник менеджером"""
        for employee in self:
            employee.is_manager = employee.position == 'manager'

    @api.constrains('sports_center_id', 'position')
    def _check_single_manager_per_center(self):
        """Проверяет, что у спортивного центра может быть только один менеджер"""
        for employee in self:
            if employee.position == 'manager' and employee.sports_center_id:
                # Ищем других менеджеров в том же спортивном центре
                other_managers = self.search([
                    ('sports_center_id', '=', employee.sports_center_id.id),
                    ('position', '=', 'manager'),
                    ('id', '!=', employee.id),
                    ('active', '=', True)
                ])
                if other_managers:
                    raise ValidationError(
                        _('У спортивного центра "%s" уже есть менеджер "%s". '
                          'У одного спортивного центра может быть только один менеджер.') % (
                            employee.sports_center_id.name,
                            other_managers[0].name
                        )
                    )
    
    @api.model_create_multi
    def create(self, vals_list):
        """Автоматически заполняет менеджеров при создании сотрудников"""
        # Обрабатываем каждую запись в списке
        employees = super().create(vals_list)
        
        # Проверяем ограничение на одного менеджера
        for employee in employees:
            if employee.position == 'manager' and employee.sports_center_id:
                employee._check_single_manager_per_center()
            
            # Если указан спортивный центр, но не указан менеджер, 
            # автоматически устанавливаем менеджера центра
            if employee.sports_center_id and not employee.parent_id:
                sports_center = employee.sports_center_id
                if sports_center.manager_id:
                    employee.parent_id = sports_center.manager_id
        
        if not self.env.context.get(SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY):
            employees._sync_role_user_accounts()
        
        # Обновляем поле is_employee у связанных партнеров
        employees._update_partner_is_employee()
        
        return employees
    
    def write(self, vals):
        """Обновляет сотрудников и проверяет ограничения"""
        result = super().write(vals)
        
        # Для тренеров фиксируем почасовую ставку = 1
        for employee in self:
            try:
                # position поле есть в этом модуле
                if (vals.get('position') or employee.position) == 'trainer':
                    if employee.hourly_rate != 1.0:
                        super(HrEmployee, employee).write({'hourly_rate': 1.0})
            except Exception:
                # На случай отсутствия поля position в отдельных БД
                pass

        # Проверяем ограничение при изменении позиции или спортивного центра
        if 'position' in vals or 'sports_center_id' in vals:
            for employee in self:
                if employee.position == 'manager' and employee.sports_center_id:
                    employee._check_single_manager_per_center()
        
        if not self.env.context.get(SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY):
            self._sync_role_user_accounts()
        
        # Обновляем поле is_employee у связанных партнеров при изменении user_id или address_home_id
        if 'user_id' in vals or 'address_home_id' in vals or 'home_address_id' in vals:
            self._update_partner_is_employee()
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        # При создании тренеров — ставка = 1
        for emp, vals in zip(employees, vals_list):
            position = vals.get('position') or emp.position
            if position == 'trainer' and emp.hourly_rate != 1.0:
                super(HrEmployee, emp).write({'hourly_rate': 1.0})
        return employees
    
    def unlink(self):
        """Безопасное удаление сотрудников с проверкой ссылок"""
        employees_to_archive = []
        employees_to_delete_ids = []
        
        # Разделяем сотрудников на тех, кого можно удалить и кого нужно заархивировать
        for employee in self:
            # Если сотрудник уже архивирован, можно удалить
            if not employee.active:
                employees_to_delete_ids.append(employee.id)
                continue
            
            # Проверяем, есть ли ссылки на сотрудника в записях на тренировки
            bookings_count = self.env['training.booking'].search_count([
                ('trainer_id', '=', employee.id)
            ])
            
            # Проверяем, является ли сотрудник менеджером спортивного центра
            sports_centers = self.env['sports.center'].search([
                ('manager_id', '=', employee.id)
            ])
            
            if bookings_count > 0 or sports_centers:
                # Формируем список причин
                reasons = []
                if bookings_count > 0:
                    reasons.append(_('- %d записей на тренировки') % bookings_count)
                if sports_centers:
                    for center in sports_centers:
                        reasons.append(_('- Является менеджером спортивного центра "%s"') % center.name)
                
                employees_to_archive.append((employee, reasons))
            else:
                # Нет ссылок, можно удалить
                employees_to_delete_ids.append(employee.id)
        
        # Архивируем сотрудников с ссылками
        if employees_to_archive:
            archive_messages = []
            
            # Собираем информацию для архивации
            archive_ids = []
            for employee, reasons in employees_to_archive:
                archive_ids.append(employee.id)
                archive_messages.append(_('Сотрудник "%s":\n%s') % (employee.name, '\n'.join(reasons)))
            
            # Архивируем всех сотрудников с ссылками через прямой SQL и commit,
            # чтобы изменения сохранились даже если основная транзакция откатится из-за UserError
            if archive_ids:
                self.env.cr.execute(
                    "UPDATE hr_employee SET active = FALSE WHERE id IN %s",
                    (tuple(archive_ids),)
                )
                self.env.cr.commit()
            
            # Удаляем тех, кого можно удалить (если есть такие) через прямой SQL
            if employees_to_delete_ids:
                self.env.cr.execute(
                    "DELETE FROM hr_employee WHERE id IN %s",
                    (tuple(employees_to_delete_ids),)
                )
                self.env.cr.commit()
            
            # Инвалидируем кэш
            self.env.invalidate_all()
            
            # Формируем сообщение об архивации
            message = _('Следующие сотрудники не могут быть удалены, так как на них есть ссылки:\n\n%s\n\n'
                       'Они были заархивированы вместо удаления. '
                       'Вы можете восстановить их позже через фильтр "Неактивные" или удалить после очистки всех ссылок.') % \
                     '\n\n'.join(archive_messages)
            
            # Логируем информацию для отладки
            archived_names = [emp.name for emp, _ in employees_to_archive]
            _logger.info("Сотрудники заархивированы вместо удаления: %s", archived_names)
            
            # Показываем предупреждение через UserWarning (менее критично, чем UserError)
            # Изменения уже сохранены через commit, так что они не откатятся
            raise UserWarning(message)
        
        # Обновляем поле is_employee у связанных партнеров перед удалением
        self._update_partner_is_employee()
        
        # Если нет ссылок, удаляем всех через родительский метод
        return super().unlink()

    @api.model
    def ensure_employee_for_user(self, user, position='trainer'):
        """Создает сотрудника и связывает с пользователем, если его еще нет"""
        self = self.sudo()
        user = user.sudo()
        employee = self.search([('user_id', '=', user.id)], limit=1)
        if employee:
            return employee

        company = user.company_id or (user.company_ids[:1] if user.company_ids else self.env.company)
        partner = user.partner_id
        email = (user.email or '').strip() or False

        vals = {
            'name': user.name or user.login,
            'user_id': user.id,
            'position': position if position in dict(self._fields['position'].selection) else 'trainer',
        }
        if email:
            vals['work_email'] = email.lower()
        if company:
            vals['company_id'] = company.id
        home_field = None
        if 'address_home_id' in self._fields:
            home_field = 'address_home_id'
        elif 'home_address_id' in self._fields:
            home_field = 'home_address_id'
        if partner and home_field:
            vals[home_field] = partner.id

        employee = self.create(vals)
        employee._sync_role_user_accounts()
        return employee

    def _ensure_user_partner_link(self, user):
        """Гарантирует, что у пользователя есть партнер и он привязан к сотруднику"""
        self.ensure_one()
        user_sudo = user.sudo().with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True})
        Partner = self.env['res.partner'].sudo()

        partner = user_sudo.partner_id
        email = (self.work_email or '').strip() or False
        partner_vals = {'name': self.name}
        if email:
            partner_vals['email'] = email
        if self.company_id:
            partner_vals['company_id'] = self.company_id.id

        if not partner:
            partner = Partner.create(partner_vals)
            user_sudo.write({'partner_id': partner.id, 'name': self.name})
        else:
            partner.sudo().write(partner_vals)

        home_update = {}
        home_field = None
        if 'address_home_id' in self._fields:
            home_field = 'address_home_id'
        elif 'home_address_id' in self._fields:
            home_field = 'home_address_id'

        if home_field and self[home_field] != partner:
            home_update[home_field] = partner.id
        if self.company_id:
            if user_sudo.company_id != self.company_id:
                user_sudo.write({'company_id': self.company_id.id})
            if self.company_id not in user_sudo.company_ids:
                user_sudo.write({'company_ids': [(4, self.company_id.id)]})
        if home_update:
            self.with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True}).sudo().write(home_update)
        
        # Обновляем is_employee у партнера после создания/обновления связи
        if partner:
            partner._compute_is_employee()

        return partner

    def _sync_role_user_accounts(self):
        """Создает или обновляет учетные записи пользователей для менеджеров и тренеров"""
        Users = self.env['res.users'].sudo().with_context(
            no_reset_password=True,
            **{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True},
        )
        manager_group = self.env.ref('tennis_club_management.group_tennis_manager')
        trainer_group = self.env.ref('tennis_club_management.group_tennis_trainer')
        director_group = self.env.ref('tennis_club_management.group_tennis_director')
        internal_group = self.env.ref('base.group_user')
        settings_group = self.env.ref('tennis_club_management.group_tennis_settings_access', raise_if_not_found=False)
        dashboard_action = self.env.ref('tennis_club_management.action_tennis_role_dashboard', raise_if_not_found=False)

        affected_user_ids = set()

        for employee in self.sudo():
            if employee.position not in ('manager', 'trainer'):
                user = employee.user_id
                if user:
                    user_ctx = user.with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True})
                    group_commands = []
                    if manager_group and user.has_group('tennis_club_management.group_tennis_manager'):
                        group_commands.append((3, manager_group.id))
                    if trainer_group and user.has_group('tennis_club_management.group_tennis_trainer'):
                        group_commands.append((3, trainer_group.id))
                    if group_commands:
                        user_ctx.write({'groups_id': group_commands})
                    if dashboard_action and user_ctx.action_id and user_ctx.action_id.id == dashboard_action.id:
                        user_ctx.write({'action_id': False})
                    affected_user_ids.add(user.id)
                continue


            user = employee.user_id
            email = (employee.work_email or '').strip()
            login = email.lower() if email else False

            if not user and login:
                user = Users.search([('login', '=', login)], limit=1)

            if not user:
                if not login:
                    continue
                user = Users.create({
                    'name': employee.name,
                    'login': login,
                    'email': email,
                    'notification_type': 'email',
                })

            user_ctx = user.with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True})
            if internal_group and not user_ctx.has_group('base.group_user'):
                user_ctx.write({'groups_id': [(4, internal_group.id)]})
            write_vals = {'name': employee.name}
            if login:
                write_vals.update({
                    'login': login,
                    'email': email,
                })
            user_ctx.write(write_vals)
            employee._ensure_user_partner_link(user_ctx)

            if employee.position == 'manager':
                group_commands = []
                if trainer_group:
                    group_commands.append((3, trainer_group.id))
                if manager_group:
                    group_commands.append((4, manager_group.id))
                if director_group:
                    group_commands.append((3, director_group.id))
                if settings_group and user_ctx.has_group('tennis_club_management.group_tennis_settings_access'):
                    group_commands.append((3, settings_group.id))
                if group_commands:
                    user_ctx.write({'groups_id': group_commands})
            else:
                group_commands = []
                if manager_group:
                    group_commands.append((3, manager_group.id))
                if trainer_group:
                    group_commands.append((4, trainer_group.id))
                if director_group:
                    group_commands.append((3, director_group.id))
                # Убираем группу настроек у тренеров
                if settings_group and user_ctx.has_group('tennis_club_management.group_tennis_settings_access'):
                    group_commands.append((3, settings_group.id))
                if group_commands:
                    user_ctx.write({'groups_id': group_commands})

            if dashboard_action and user_ctx.action_id and user_ctx.action_id.id == dashboard_action.id:
                user_ctx.write({'action_id': False})

            password = ROLE_PASSWORDS.get(employee.position)
            if password:
                user_ctx.write({'password': password})

            if employee.user_id != user:
                employee.with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True}).write({'user_id': user.id})
            
            # Обновляем is_employee у связанного партнера после синхронизации
            employee._update_partner_is_employee()

            affected_user_ids.add(user.id)

        # Удаляем группу настроек у всех тренеров
        if settings_group and trainer_group:
            # Находим всех пользователей с группой тренера
            trainer_users = Users.search([('groups_id', 'in', trainer_group.id)])
            
            # Удаляем группу настроек у всех тренеров
            for user in trainer_users:
                if user.exists():
                    user_ctx = user.with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True})
                    if user_ctx.has_group('tennis_club_management.group_tennis_settings_access'):
                        user_ctx.write({'groups_id': [(3, settings_group.id)]})
        
        # Добавляем группу настроек менеджерам и директорам, если её нет
        if settings_group and affected_user_ids:
            Employee = self.env['hr.employee'].sudo()
            for user in Users.browse(list(affected_user_ids)):
                user_ctx = user.with_context(**{SKIP_EMPLOYEE_ROLE_SYNC_CTX_KEY: True})
                positions = set(Employee.search([('user_id', '=', user.id)]).mapped('position'))
                group_commands = []
                # Если это менеджер или директор, добавляем группу настроек
                if 'manager' in positions or user_ctx.has_group('tennis_club_management.group_tennis_director'):
                    if not user_ctx.has_group('tennis_club_management.group_tennis_settings_access'):
                        group_commands.append((4, settings_group.id))
                if group_commands:
                    user_ctx.write({'groups_id': group_commands})

    @api.model
    def remove_settings_from_all_trainers(self):
        """Принудительно удаляет группу настроек у всех тренеров"""
        Users = self.env['res.users'].sudo()
        trainer_group = self.env.ref('tennis_club_management.group_tennis_trainer', raise_if_not_found=False)
        settings_group = self.env.ref('tennis_club_management.group_tennis_settings_access', raise_if_not_found=False)
        
        if not trainer_group or not settings_group:
            return 0
        
        trainer_users = Users.search([('groups_id', 'in', trainer_group.id)])
        removed_count = 0
        
        for user in trainer_users:
            if user.has_group('tennis_club_management.group_tennis_settings_access'):
                user.write({'groups_id': [(3, settings_group.id)]})
                removed_count += 1
        
        return removed_count

    def get_upcoming_trainings_count(self):
        """Возвращает количество будущих тренировок для тренера"""
        self.ensure_one()
        # Включаем только тренировки со статусами "подтверждено" и "в процессе"
        count = self.env['training.booking'].search_count([
            ('trainer_id', '=', self.id),
            ('state', 'in', ['confirmed', 'in_progress'])
        ])
        return count
    
    def _update_partner_is_employee(self):
        """Обновляет поле is_employee у связанных партнеров"""
        Partner = self.env['res.partner'].sudo()
        for employee in self:
            # Получаем партнеров, связанных с сотрудником
            partner_ids = []
            if employee.user_id and employee.user_id.partner_id:
                partner_ids.append(employee.user_id.partner_id.id)
            
            # Проверяем поле address_home_id или home_address_id
            home_field = None
            if 'address_home_id' in self._fields:
                home_field = 'address_home_id'
            elif 'home_address_id' in self._fields:
                home_field = 'home_address_id'
            
            if home_field and employee[home_field]:
                partner_ids.append(employee[home_field].id)
            
            # Обновляем is_employee для связанных партнеров
            if partner_ids:
                partners = Partner.browse(partner_ids)
                partners._compute_is_employee()
        
        # Также обновляем партнеров, которые больше не связаны с сотрудниками
        # (если сотрудник был удален или изменен)
        all_employee_partner_ids = []
        all_employees = self.env['hr.employee'].search([])
        for emp in all_employees:
            if emp.user_id and emp.user_id.partner_id:
                all_employee_partner_ids.append(emp.user_id.partner_id.id)
            home_field = None
            if 'address_home_id' in self._fields:
                home_field = 'address_home_id'
            elif 'home_address_id' in self._fields:
                home_field = 'home_address_id'
            if home_field and emp[home_field]:
                all_employee_partner_ids.append(emp[home_field].id)
        
        # Находим партнеров, у которых is_employee=True, но они больше не связаны с сотрудниками
        partners_to_update = Partner.search([
            ('is_employee', '=', True),
            ('id', 'not in', all_employee_partner_ids)
        ])
        if partners_to_update:
            partners_to_update._compute_is_employee()

