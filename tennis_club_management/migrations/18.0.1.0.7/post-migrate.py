from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    director_group = env.ref('tennis_club_management.group_tennis_director', raise_if_not_found=False)
    if not director_group:
        return

    trainer_group = env.ref('tennis_club_management.group_tennis_trainer', raise_if_not_found=False)
    manager_group = env.ref('tennis_club_management.group_tennis_manager', raise_if_not_found=False)

    domain = []
    if trainer_group:
        domain.append(('groups_id', 'in', trainer_group.id))
    if manager_group:
        domain.append(('groups_id', 'in', manager_group.id))

    if not domain:
        return

    users = env['res.users'].sudo().search(['|'] + domain if len(domain) == 2 else domain)
    if users:
        users.write({'groups_id': [(3, director_group.id)]})

