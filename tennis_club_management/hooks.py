from odoo import api, SUPERUSER_ID


def post_init_hook(*args, **kwargs):
    if args and isinstance(args[0], api.Environment):
        env = args[0]
    elif args:
        env = api.Environment(args[0], SUPERUSER_ID, {})
    else:
        env = kwargs.get('env')
        if env is None:
            cr = kwargs.get('cr')
            if cr is None:
                raise ValueError('post_init_hook requires env or cr')
            env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env['hr.employee'].sudo().search([('position', 'in', ('manager', 'trainer'))])
    employees._sync_role_user_accounts()
