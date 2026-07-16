from odoo import models, fields, api
from odoo.exceptions import AccessError
from datetime import date


class VahiniAnnouncement(models.Model):
    _name        = "vahini.announcement"
    _description = "Vahini Dashboard Announcement"
    _order       = "pin_top desc, create_date desc"

    title        = fields.Char(required=True)
    message      = fields.Text(required=True)
    ann_type     = fields.Selection([
        ("scheme",   "Scheme / Offer"),
        ("launch",   "New Product Launch"),
        ("discount", "Discount"),
        ("general",  "General"),
    ], default="general", required=True)
    image        = fields.Binary(attachment=True)
    link         = fields.Char(string="URL / Link")
    expiry_date  = fields.Date()
    pin_top      = fields.Boolean(default=False)
    active       = fields.Boolean(default=True)
    created_by   = fields.Many2one("res.users", default=lambda s: s.env.uid, readonly=True)

    def _check_manager(self):
        if not (
            self.env.user.has_group("base.group_system") or
            self.env.user.has_group("sales_team.group_sale_manager") or
            self.env.user.has_group("account.group_account_manager")
        ):
            raise AccessError("Only managers can manage announcements.")

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager()
        return super().create(vals_list)

    def write(self, vals):
        self._check_manager()
        return super().write(vals)

    def unlink(self):
        self._check_manager()
        return super().unlink()

    @api.model
    def get_active_announcements(self):
        today = date.today()
        recs = self.search([
            ("active", "=", True),
            "|", ("expiry_date", "=", False),
                 ("expiry_date", ">=", today),
        ])
        return [{
            "id":          r.id,
            "title":       r.title,
            "message":     r.message,
            "ann_type":    r.ann_type,
            "link":        r.link or "",
            "expiry_date": r.expiry_date.isoformat() if r.expiry_date else "",
            "pin_top":     r.pin_top,
            "image":       f"/web/image/vahini.announcement/{r.id}/image" if r.image else "",
            "created_by":  r.created_by.name or "",
            "created_on":  r.create_date.strftime("%d %b %Y") if r.create_date else "",
            "is_manager":  (
                self.env.user.has_group("base.group_system") or
                self.env.user.has_group("sales_team.group_sale_manager") or
                self.env.user.has_group("account.group_account_manager")
            ),
        } for r in recs]

    @api.model
    def save_announcement(self, vals):
        self._check_manager()
        ann_id = vals.get("id")
        data = {
            "title":       vals.get("title", ""),
            "message":     vals.get("message", ""),
            "ann_type":    vals.get("ann_type", "general"),
            "link":        vals.get("link", ""),
            "expiry_date": vals.get("expiry_date") or False,
            "pin_top":     vals.get("pin_top", False),
        }
        if ann_id:
            rec = self.browse(ann_id)
            rec.write(data)
            return rec.id
        else:
            rec = self.create([data])
            return rec.id

    @api.model
    def delete_announcement(self, ann_id):
        self._check_manager()
        self.browse(ann_id).unlink()
        return True
