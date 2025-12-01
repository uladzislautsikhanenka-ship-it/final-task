from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env['hr.employee'].sudo().search([('position', 'in', ('manager', 'trainer'))])
    if employees:
        employees._sync_role_user_accounts()

