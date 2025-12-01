# -*- coding: utf-8 -*-

from odoo import models, api


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _get_child_menu_ids(self, menu):
        """Рекурсивно получает все ID дочерних меню через прямой SQL запрос для избежания рекурсии"""
        child_ids = set()
        if not menu:
            return child_ids
        
        # Используем прямой SQL запрос для получения дочерних меню без применения фильтров видимости
        # Это избегает вызова _filter_visible_menus() и рекурсии
        query = """
            SELECT id FROM ir_ui_menu
            WHERE parent_id = %s
        """
        self.env.cr.execute(query, (menu.id,))
        child_menu_ids = [row[0] for row in self.env.cr.fetchall()]
        
        for child_id in child_menu_ids:
            child_ids.add(child_id)
            # Рекурсивно получаем дочерние меню дочерних меню
            child_menu = self.env['ir.ui.menu'].sudo().browse(child_id)
            child_ids.update(self._get_child_menu_ids(child_menu))
        
        return child_ids

    @api.model
    def _visible_menu_ids(self, debug=False):
        """Переопределяем метод проверки видимости меню для правильной работы с ролями"""
        # Получаем список видимых меню из родительского метода
        visible_menus = super()._visible_menu_ids(debug)
        
        # Преобразуем в set для удобной работы, если это не set
        if not isinstance(visible_menus, set):
            visible_menus = set(visible_menus)
        
        # Получаем группы текущего пользователя
        user = self.env.user
        is_director = user.has_group('tennis_club_management.group_tennis_director')
        is_manager = user.has_group('tennis_club_management.group_tennis_manager')
        is_trainer = user.has_group('tennis_club_management.group_tennis_trainer')
        
        # Получаем ID меню через sudo для избежания проблем с доступом
        management_menu = self.env.ref('tennis_club_management.menu_tennis_club_management_management', raise_if_not_found=False)
        clients_menu = self.env.ref('tennis_club_management.menu_res_partner_manager', raise_if_not_found=False)
        config_menu = self.env.ref('tennis_club_management.menu_tennis_club_management_config', raise_if_not_found=False)
        sports_center_menu = self.env.ref('tennis_club_management.menu_sports_center_manager_trainer', raise_if_not_found=False)
        training_menu = self.env.ref('tennis_club_management.menu_tennis_club_management_training', raise_if_not_found=False)
        
        # Если пользователь - менеджер (НЕ директор), скрываем меню "Управление"
        if is_manager and not is_director:
            if management_menu and management_menu.id in visible_menus:
                visible_menus.discard(management_menu.id)
                # Также скрываем все дочерние меню "Управления"
                child_ids = self._get_child_menu_ids(management_menu)
                visible_menus -= child_ids
        
        # Если пользователь - директор (НЕ менеджер), скрываем меню "Клиенты" для менеджеров и "Спортивный центр"
        if is_director and not is_manager:
            if clients_menu and clients_menu.id in visible_menus:
                visible_menus.discard(clients_menu.id)
            # Скрываем меню "Спортивный центр" для менеджеров и тренеров (у директоров есть в "Управлении")
            if sports_center_menu and sports_center_menu.id in visible_menus:
                visible_menus.discard(sports_center_menu.id)
        
        # Если пользователь - тренер, скрываем меню "Настройки", "Управление" и "Тренировки"
        # Проверяем ТОЛЬКО тренера (без директора и менеджера)
        if is_trainer and not is_director and not is_manager:
            # Скрываем меню "Настройки"
            if config_menu:
                if config_menu.id in visible_menus:
                    visible_menus.discard(config_menu.id)
                # Также скрываем все дочерние меню "Настроек"
                child_ids = self._get_child_menu_ids(config_menu)
                visible_menus -= child_ids
            
            # Скрываем меню "Управление"
            if management_menu:
                if management_menu.id in visible_menus:
                    visible_menus.discard(management_menu.id)
                # Также скрываем все дочерние меню "Управления"
                child_ids = self._get_child_menu_ids(management_menu)
                visible_menus -= child_ids
            
            # Скрываем меню "Тренировки" для тренеров
            if training_menu:
                if training_menu.id in visible_menus:
                    visible_menus.discard(training_menu.id)
                # Также скрываем все дочерние меню "Тренировок"
                child_ids = self._get_child_menu_ids(training_menu)
                visible_menus -= child_ids
        
        return visible_menus

