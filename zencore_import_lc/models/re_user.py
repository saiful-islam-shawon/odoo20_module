from odoo import models, fields, api
from odoo.fields import Command


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_approver = fields.Boolean(
        string='LC Approver (Legacy Flag)',
        default=False,
        help='Backward-compatible approver flag. New access should use the Import LC / Approver group.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        approver_group = self.env.ref('zencore_import_lc.group_lc_approver', raise_if_not_found=False)
        if approver_group:
            for user, vals in zip(users, vals_list):
                if vals.get('is_approver'):
                    user.sudo().write({'group_ids': [Command.link(approver_group.id)]})
        return users

    def write(self, vals):
        result = super().write(vals)
        if 'is_approver' in vals:
            approver_group = self.env.ref('zencore_import_lc.group_lc_approver', raise_if_not_found=False)
            if approver_group:
                command = Command.link(approver_group.id) if vals['is_approver'] else Command.unlink(approver_group.id)
                super(ResUsers, self.sudo()).write({'group_ids': [command]})
        return result
