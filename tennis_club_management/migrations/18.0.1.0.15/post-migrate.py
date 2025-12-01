from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Users = env['res.users'].sudo()
    manager_group = env.ref('tennis_club_management.group_tennis_manager', raise_if_not_found=False)
    director_group = env.ref('tennis_club_management.group_tennis_director', raise_if_not_found=False)
    trainer_group = env.ref('tennis_club_management.group_tennis_trainer', raise_if_not_found=False)
    settings_group = env.ref('tennis_club_management.group_tennis_settings_access', raise_if_not_found=False)
    internal_group = env.ref('base.group_user', raise_if_not_found=False)

    if not trainer_group:
        return

    trainers = Users.search([('groups_id', 'in', trainer_group.id)])

    for user in trainers:
        commands = []
        if manager_group and user.has_group('tennis_club_management.group_tennis_manager'):
            commands.append((3, manager_group.id))
        if director_group and user.has_group('tennis_club_management.group_tennis_director'):
            commands.append((3, director_group.id))
        if settings_group and user.has_group('tennis_club_management.group_tennis_settings_access'):
            commands.append((3, settings_group.id))
        if commands:
            user.write({'groups_id': commands})
        add_commands = []
        if internal_group and not user.has_group('base.group_user'):
            add_commands.append((4, internal_group.id))
        if add_commands:
            user.write({'groups_id': add_commands})
        employee = env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not employee:
            employee = env['hr.employee'].sudo().ensure_employee_for_user(user)
        if employee:
            employee._sync_role_user_accounts()

