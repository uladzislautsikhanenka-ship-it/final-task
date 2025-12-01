from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Users = env['res.users'].sudo()
    Employee = env['hr.employee'].sudo()
    
    trainer_group = env.ref('tennis_club_management.group_tennis_trainer', raise_if_not_found=False)
    settings_group = env.ref('tennis_club_management.group_tennis_settings_access', raise_if_not_found=False)

    if not trainer_group or not settings_group:
        print("Группы не найдены, пропускаем миграцию")
        return

    # Находим всех пользователей с группой тренера
    trainer_users = Users.search([('groups_id', 'in', trainer_group.id)])
    
    # Также проверяем всех пользователей, у которых есть связанный сотрудник-тренер
    trainer_employees = Employee.search([('position', '=', 'trainer'), ('user_id', '!=', False)])
    trainer_user_ids = set(trainer_employees.mapped('user_id').ids)
    for user in trainer_users:
        trainer_user_ids.add(user.id)
    
    # Удаляем группу настроек у всех тренеров
    removed_count = 0
    for user_id in trainer_user_ids:
        user = Users.browse(user_id)
        if user.exists():
            if user.has_group('tennis_club_management.group_tennis_settings_access'):
                user.write({'groups_id': [(3, settings_group.id)]})
                removed_count += 1
                print(f"Удалена группа настроек у пользователя: {user.name} (ID: {user.id})")
    
    cr.commit()
    print(f"Миграция завершена. Удалено групп настроек у {removed_count} тренеров.")

