from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home


class TennisHomeRedirect(Home):
    def _login_redirect(self, uid, redirect=None):
        user = request.env['res.users'].sudo().browse(uid)
        return super()._login_redirect(uid, redirect=redirect)

    @http.route(['/web', '/odoo', '/odoo/<path:subpath>', '/scoped_app/<path:subpath>'], type='http', auth="none", readonly=Home._web_client_readonly)
    def web_client(self, s_action=None, **kw):
        return super().web_client(s_action=s_action, **kw)
