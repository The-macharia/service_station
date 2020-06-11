# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StationSales(models.Model):
    _name = 'station.sales'
    _description = 'Manage sales at a service station'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'pump'
    _order = 'id desc'

    # DELETE THIS FUNCTION WHEN YOU ARE DONE, THIS IS A TESTING FXN
    def test(self):
        pass

    def reset_to_draft(self):
        self.write({'state': 'draft'})

    @api.constrains('fuel_sales')
    def approve_fuel_Sales(self):
        for rec in self.nozzle_record_line:
            for record in self.env['station.nozzles'].search([]):
                record.write({'current_reading': rec.eclose}
                             ) if record.id == rec.nozzle_id.id else None
        if (self.fuel_sales == 0):
            raise ValidationError('You cannot approve zero sales!')
        else:
            self.write({'state': 'approved'})

    def generate_sale_invoices(self):
        payment_lines = ['visa_line', 'loyalty_cards_line',
                         'shell_pos_line', 'mpesa_line', 'drop_line']

        for rec in self.env['station.csa'].search([]):
            lines = []
            vals = {
                'date': self.date,
                'description': 'short' if self.short_or_excess < 0 else 'excess',
                'amount': self.short_or_excess,
            }
            lines.append((0, 0, vals))
            rec.short_line = lines if self.csa_id.id == rec.id else None

        for record in payment_lines:
            if record == 'drop_line':
                for line in self.drop_line:
                    invoice_vals = {
                        'partner_id': '',
                        'type': 'out_invoice',
                        'invoice_user_id': self.csa_id and self.csa_id.id,
                        'state': 'draft',
                        'source_id': self.id,
                        'invoice_date': self.date,
                        'invoice_payment_term_id': 1,
                        'invoice_line_ids': [5, 0, 0, {
                            'name': line.code,
                            'account_id': 2,
                            'analytic_account_id': 1,
                            'quantity': 1,
                            'price_unit': line.amount,
                        }]
                    }
                    invoice = self.env['account.move'].sudo().create(
                        invoice_vals)

            else:
                for line in self[record]:
                    invoice_vals = {
                        'partner_id': line.partner_id.id,
                        'type': 'out_invoice',
                        'invoice_user_id': self.csa_id and self.csa_id.id,
                        'source_id': self.id,
                        'state': 'draft',
                        'invoice_date': self.date,
                        'invoice_payment_term_id': 1,
                        'invoice_line_ids': [5, 0, 0, {
                            'name': line.code,
                            'account_id': 2,
                            'analytic_account_id': 1,
                            'quantity': 1,
                            'price_unit': line.amount,
                        }]
                    }
                    invoice = self.env['account.move'].sudo().create(
                        invoice_vals)

        self.write({'state': 'invoiced'})

    def open_station_invoices(self):
        return {
            'name': _('Invoices'),
            'domain': [],
            'view_type': 'form',
            'res.model': 'station.csa',
            'view_id': False,
            'view_mode': 'tree,form',
            'type': 'ir.actions.act_window'
        }

    def get_invoices_count(self):
        count = self.env['account.move'].search_count(
            [])
        self.invoices_count = count

    @api.depends('nozzle_record_line.amount')
    def _compute_fuel_sales(self):
        for record in self:
            fuel_sales = 0.0
            for line in record.nozzle_record_line:
                fuel_sales += line.amount
            record.update({'fuel_sales': fuel_sales})
        return fuel_sales

    @api.depends('amount_tax', 'amount_untaxed')
    def _compute_taxes(self):
        for rec in self:
            amount = rec.amount_untaxed + \
                (rec.amount_tax/100 * rec.amount_untaxed)
            rec.update({'amount_total': amount})

    @api.depends('amount_untaxed', 'amount_tax', 'visa_line.amount', 'shell_pos_line.amount',
                 'loyalty_cards_line.amount', 'mpesa_line.amount', 'drop_line.amount',
                 'invoices_line.amount')
    def _compute_total_amount(self):
        for record in self:
            visa_total = 0.0
            shell_pos_total = 0.0
            mpesa_total = 0.0
            loyalty_cards_total = 0.0
            invoices_total = 0.0
            drop_total = 0.0
            fuel_sales = record.fuel_sales
            total_credits = 0.0
            cash_required = 0.0
            short_or_excess = 0.0

            for line in record.visa_line:
                visa_total += line.amount

            for line in record.shell_pos_line:
                shell_pos_total += line.amount

            for line in record.mpesa_line:
                mpesa_total += line.amount

            for line in record.loyalty_cards_line:
                loyalty_cards_total += line.amount

            for line in record.invoices_line:
                invoices_total += line.amount

            for line in record.drop_line:
                drop_total += line.amount

            total_credits = visa_total + invoices_total + mpesa_total + shell_pos_total
            cash_required = fuel_sales - total_credits
            short_or_excess = drop_total - cash_required
            amount_untaxed = total_credits + loyalty_cards_total + drop_total

            short_or_excess_display = '{:+}'.format(short_or_excess)

            record.update({
                'visa_total': visa_total,
                'shell_pos_total': shell_pos_total,
                'loyalty_cards_total': loyalty_cards_total,
                'mpesa_total': mpesa_total,
                'invoices_total': invoices_total,
                'drop_total': drop_total,
                'amount_untaxed': amount_untaxed,
                'total_credits': total_credits,
                'cash_required': cash_required,
                'short_or_excess': short_or_excess,
                'short_or_excess_display': short_or_excess_display,
            })
        print(short_or_excess_display)

    @api.onchange('pump')
    def _onchange_pump_create_nozzles(self):
        for rec in self:
            lines = [(5, 0, 0)]
            for nozzle in self.pump.nozzle_line:
                val = {
                    'nozzle_id': nozzle,
                    'price': nozzle.price,
                    'eopen': nozzle['current_reading']
                }
                lines.append((0, 0, val))
            rec.nozzle_record_line = lines

    @api.onchange('csa_id')
    def _onchange_csa_id_filter_pump(self):
        for rec in self:
            return {'domain':
                    {'pump': [('station_id', '=', rec.csa_id.station_id.id)]}}

    @api.onchange('csa_id')
    def _onchange_csa_id_update_dropby(self):
        for rec in self:
            lines = [(5, 0, 0)]
            for line in self.csa_id:
                rec.station_id = self.csa_id.station_id
                val = {
                    'code': '0000',
                    'drop_by': self.csa_id
                }
                lines.append((0, 0, val))
            rec.drop_line = lines

    station_id = fields.Many2one(
        'station.stations', string='Station')
    csa_id = fields.Many2one('station.csa', string='CSA', required=True)
    pump = fields.Many2one('station.pump', string='Pump', required=True)
    date = fields.Date(
        string='Date', default=fields.Datetime.now, required=True)
    amount_untaxed = fields.Monetary(string='Untaxed Amount', readonly=True)
    amount_tax = fields.Monetary(string='Tax Amount')
    currency_id = fields.Many2one('res.currency')
    amount_total = fields.Monetary(
        string='Total Amount', compute='_compute_taxes', readonly=True)
    fuel_sales = fields.Monetary(string='Fuel Sales', track_visibility='onchange',
                                 compute='_compute_fuel_sales')
    total_credits = fields.Monetary(string='Total Credits', readonly=True)
    cash_required = fields.Monetary(
        string='Cash Required', track_visibility='onchange', readonly=True)
    short_or_excess = fields.Monetary(string='Short/ Excess', readonly=True)
    short_or_excess_display = fields.Char(
        string='Short/ Excess', readonly=True)

    visa_line = fields.One2many('visa.line', 'visa_id', string='Visa Line')
    shell_pos_line = fields.One2many(
        'shell.pos.line', 'shell_pos_id', string='Shell Pos Line')
    loyalty_cards_line = fields.One2many(
        'loyalty.cards.line', 'loyalty_cards_id', string='Loyalty Cards Line')
    mpesa_line = fields.One2many('mpesa.line', 'mpesa_id', string='Mpesa Line')
    invoices_line = fields.One2many(
        'invoices.line', 'invoices_id', string='Invoices Line')
    drop_line = fields.One2many('drop.line', 'drop_id', string='Drop Line')
    nozzle_record_line = fields.One2many(
        'nozzle.record.line', 'nozzle_record_id', string='Nozzle Record Line')
    visa_total = fields.Monetary(string='Visa Total', compute='_compute_total_amount',
                                 track_visibility='onchange', store=True, readonly=True)
    shell_pos_total = fields.Monetary(
        string='Shell Pos Total', compute='_compute_total_amount', readonly=True, store=True)
    loyalty_cards_total = fields.Monetary(
        string='Loyalty Cards Total', compute='_compute_total_amount', readonly=True, store=True)
    mpesa_total = fields.Monetary(
        string='Mpesa Total', compute='_compute_total_amount', readonly=True, store=True)
    invoices_total = fields.Monetary(
        string='Invoices Total', compute='_compute_total_amount', readonly=True, store=True)
    drop_total = fields.Monetary(
        string='Cash Drop Total', compute='_compute_total_amount', readonly=True, store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'To Be Invoiced'),
        ('invoiced', 'Invoiced'),
    ], string='Status', readonly=True, index=True, copy=False, default='draft', track_visibility='onchange')
    shift_id = fields.Selection([
        ('morning', 'Morning'),
        ('night', 'Night')
    ], string='Shift', required=True)
    invoices_count = fields.Integer(
        string='Invoices', compute="get_invoices_count")
