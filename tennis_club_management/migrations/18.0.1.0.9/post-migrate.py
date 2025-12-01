from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    director_group = env.ref('tennis_club_management.group_tennis_director', raise_if_not_found=False)
    if not director_group:
        return

    employee_model = env['hr.employee'].sudo()

    trainers = employee_model.search([('position', '=', 'trainer'), ('user_id', '!=', False)])
    managers = employee_model.search([('position', '=', 'manager'), ('user_id', '!=', False)])

    trainer_user_ids = trainers.mapped('user_id').ids
    manager_user_ids = managers.mapped('user_id').ids

    users_to_add = set(trainer_user_ids + manager_user_ids)
    if users_to_add:
        env['res.users'].sudo().browse(list(users_to_add)).write({'groups_id': [(4, director_group.id)]})

