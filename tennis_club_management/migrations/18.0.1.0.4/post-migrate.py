from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    dashboard_action = env.ref('tennis_club_management.action_tennis_role_dashboard', raise_if_not_found=False)
    if dashboard_action:
        env['res.users'].sudo().search([('action_id', '=', dashboard_action.id)]).write({'action_id': False})
        dashboard_action.unlink()

    dashboard_view = env.ref('tennis_club_management.role_dashboard_page', raise_if_not_found=False)
    if dashboard_view:
        dashboard_view.unlink()

    employees = env['hr.employee'].sudo().search([('position', 'in', ('manager', 'trainer'))])
    if employees:
        employees._sync_role_user_accounts()

