import json

from werkzeug.urls import url_encode

from odoo import http
from odoo.http import request
from odoo import fields
from datetime import date


class TennisRoleDashboard(http.Controller):
    @http.route('/tennis_club/dashboard', type='http', auth='user', website=False)
    def role_dashboard(self):
        return request.redirect('/web')

    @http.route('/tennis_club/my_work', type='http', auth='user', website=False)
    def my_work(self):
        user = request.env.user
        Employee = request.env['hr.employee']

        employee = user.employee_id
        if not employee:
            employee = Employee.search([('user_id', '=', user.id)], limit=1)
        if not employee and user.email:
            employee = Employee.search([('work_email', '=', user.email)], limit=1)

        if employee:
            employee._sync_role_user_accounts()

        action_ref = request.env.ref('tennis_club_management.action_hr_employee_all', raise_if_not_found=False)
        menu_ref = request.env.ref('tennis_club_management.menu_tennis_club_management_my_work', raise_if_not_found=False)

        if employee:
            params = {
                'id': employee.id,
                'model': 'hr.employee',
                'view_type': 'form',
                'view_mode': 'form',
            }
            if action_ref:
                params['action'] = action_ref.id
            if menu_ref:
                params['menu_id'] = menu_ref.id

            return request.redirect(f"/web#{url_encode(params)}")

        if action_ref:
            params = {'action': action_ref.id}
            if menu_ref:
                params['menu_id'] = menu_ref.id
            return request.redirect(f"/web#{url_encode(params)}")

        return request.redirect('/web')

    @http.route('/tennis_club/trainer_calendar', type='http', auth='user', website=False)
    def trainer_calendar(self):
        user = request.env.user
        Employee = request.env['hr.employee']

        employee = user.employee_id
        if not employee:
            employee = Employee.search([('user_id', '=', user.id)], limit=1)
        if not employee and user.email:
            employee = Employee.search([('work_email', '=', user.email)], limit=1)

        if employee:
            employee._sync_role_user_accounts()

        action_ref = request.env.ref('tennis_club_management.action_trainer_availability_calendar', raise_if_not_found=False)
        menu_ref = request.env.ref('tennis_club_management.menu_sports_center_trainer', raise_if_not_found=False)

        if not action_ref:
            return request.redirect('/web')

        params = {
            'action': action_ref.id,
        }
        if menu_ref:
            params['menu_id'] = menu_ref.id

        if employee:
            params.update({
                'active_id': employee.id,
                'model': 'trainer.availability',
                'view_type': 'calendar',
                'view_mode': 'calendar',
                'context': json.dumps({
                    'search_default_employee_id': employee.id,
                    'default_employee_id': employee.id,
                }),
            })

        return request.redirect(f"/web#{url_encode(params)}")

    @http.route('/tennis_club/get_upcoming_trainings_count', type='json', auth='user', website=False)
    def get_upcoming_trainings_count(self):
        """Возвращает количество будущих тренировок для текущего тренера
        Виджет доступен ТОЛЬКО тренерам, НЕ директорам и НЕ менеджерам
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        user = request.env.user.sudo()
        Employee = request.env['hr.employee'].sudo()
        TrainingBooking = request.env['training.booking'].sudo()
        
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        is_manager = user.has_group('tennis_club_management.group_tennis_manager')
        is_trainer = user.has_group('tennis_club_management.group_tennis_trainer')
        
        _logger.info(f"[TrainerWidget] Проверка доступа для пользователя {user.name} (ID: {user.id}): director={is_director}, manager={is_manager}, trainer={is_trainer}")
        if is_director:
            _logger.info(f"[TrainerWidget] Доступ запрещен: пользователь {user.name} является директором (даже если у него есть группа тренера)")
            return {'count': 0, 'error': 'access_denied', 'reason': 'director'}
        
        # Если пользователь является менеджером - возвращаем ошибку доступа
        if is_manager:
            _logger.info(f"[TrainerWidget] Доступ запрещен: пользователь {user.name} является менеджером (даже если у него есть группа тренера)")
            return {'count': 0, 'error': 'access_denied', 'reason': 'manager'}
        
        # Если пользователь не является тренером - возвращаем ошибку доступа
        if not is_trainer:
            _logger.info(f"[TrainerWidget] Доступ запрещен: пользователь {user.name} не является тренером")
            return {'count': 0, 'error': 'access_denied', 'reason': 'not_trainer'}
        
        # Пользователь является ТОЛЬКО тренером (не директор, не менеджер)
        _logger.info(f"[TrainerWidget] Доступ разрешен: пользователь {user.name} является ТОЛЬКО тренером (не директор, не менеджер)")
        
        # Ищем employee для пользователя
        employee = user.employee_id
        if not employee:
            _logger.info(f"[TrainerWidget] employee_id не найден, ищем по user_id")
            employee = Employee.search([('user_id', '=', user.id)], limit=1)
        if not employee and user.email:
            _logger.info(f"[TrainerWidget] Ищем employee по email: {user.email}")
            employee = Employee.search([('work_email', '=', user.email)], limit=1)
        
        if not employee:
            _logger.warning(f"[TrainerWidget] Employee не найден для пользователя {user.name}")
            return {'count': 0, 'error': 'employee_not_found'}
        
        _logger.info(f"[TrainerWidget] Employee найден: {employee.name} (ID: {employee.id})")
        
        # Получаем количество тренировок
       
        today = fields.Date.today()
        
        _logger.info(f"[TrainerWidget] Сегодня: {today}")
        _logger.info(f"[TrainerWidget] Employee ID: {employee.id}, Employee Name: {employee.name}")
        
        # Проверяем все тренировки для этого тренера для отладки
        all_trainings = TrainingBooking.search([('trainer_id', '=', employee.id)], limit=20)
        _logger.info(f"[TrainerWidget] Всего тренировок у тренера (первые 20): {len(all_trainings)}")
        for training in all_trainings:
            _logger.info(f"[TrainerWidget] Тренировка: {training.name}, дата: {training.booking_date}, статус: {training.state}, тренер ID: {training.trainer_id.id if training.trainer_id else None}")
        
        # Ищем все будущие тренировки для этого тренера со статусами "подтверждено" и "в процессе"
        # Важно: используем фильтр по статусам, а не по дате
        domain = [
            ('trainer_id', '=', employee.id),
            ('state', 'in', ['confirmed', 'in_progress'])
        ]
        
        _logger.info(f"[TrainerWidget] Домен поиска будущих тренировок: {domain}")
        
        bookings = TrainingBooking.search(domain)
        count = len(bookings)
        
        _logger.info(f"[TrainerWidget] Найдено будущих тренировок: {count}")
        
        # Выводим детали найденных тренировок
        if bookings:
            _logger.info(f"[TrainerWidget] Детали найденных будущих тренировок:")
            for booking in bookings:
                _logger.info(f"[TrainerWidget] - Тренировка: {booking.name}, дата: {booking.booking_date}, статус: {booking.state}, тренер: {booking.trainer_id.name if booking.trainer_id else 'None'}")
        else:
            _logger.warning(f"[TrainerWidget] Будущие тренировки не найдены. Проверяем тренировки с будущими датами:")
            # Проверяем тренировки с будущими датами (любой статус)
            future_trainings = TrainingBooking.search([
                ('trainer_id', '=', employee.id),
                ('booking_date', '>=', today)
            ])
            _logger.info(f"[TrainerWidget] Найдено тренировок с будущими датами (любой статус): {len(future_trainings)}")
            for training in future_trainings:
                _logger.info(f"[TrainerWidget] - Тренировка: {training.name}, дата: {training.booking_date}, статус: {training.state}")
        
        return {'count': count, 'employee_id': employee.id, 'employee_name': employee.name}

    @http.route('/tennis_club/get_trainer_trainings', type='json', auth='user', website=False)
    def get_trainer_trainings(self):
        """Возвращает тренировки тренера для виджета календаря
        Использует ту же логику получения employee, что и get_upcoming_trainings_count
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        user = request.env.user.sudo()
        Employee = request.env['hr.employee'].sudo()
        
        # Ищем employee для пользователя (та же логика, что и в get_upcoming_trainings_count)
        employee = user.employee_id
        if not employee:
            _logger.info(f"[TrainerTrainings] employee_id не найден, ищем по user_id")
            employee = Employee.search([('user_id', '=', user.id)], limit=1)
        if not employee and user.email:
            _logger.info(f"[TrainerTrainings] Ищем employee по email: {user.email}")
            employee = Employee.search([('work_email', '=', user.email)], limit=1)
        
        if not employee:
            _logger.warning(f"[TrainerTrainings] Employee не найден для пользователя {user.name}")
            return {'today': [], 'upcoming': [], 'training_dates': []}
        
        _logger.info(f"[TrainerTrainings] Employee найден: {employee.name} (ID: {employee.id})")
        
        # Вызываем метод модели для получения тренировок
        TrainerAvailability = request.env['trainer.availability'].sudo()
        result = TrainerAvailability.get_trainer_trainings(employee.id)
        
        today_count = len(result.get('today', []))
        upcoming_count = len(result.get('upcoming', []))
        _logger.info(f"[TrainerTrainings] Возвращаем {today_count} сегодняшних и {upcoming_count} будущих тренировок")
        
        # Убеждаемся, что все необходимые ключи присутствуют
        if 'training_dates' not in result:
            result['training_dates'] = []
        
        _logger.info(f"[TrainerTrainings] Формат ответа: today={today_count}, upcoming={upcoming_count}, training_dates={len(result.get('training_dates', []))}")
        
        return result

