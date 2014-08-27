# -*- coding: utf-8 -*-

##############################################################################
#    Copyright (C) 2012 SICLIC http://siclic.fr
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
#############################################################################

from osv import fields,osv
import re
from tools.translate import _
from datetime import datetime
import netsvc
from openbase.openbase_core import OpenbaseCore

class res_users(OpenbaseCore):
    _inherit = "res.users"
    _name = "res.users"
    
    _columns = {
        'max_po_amount':fields.float('Montant par Bon de Commande', digit=(4,2), help="Montant Max autorisé par Bon de Commande"),
        'max_total_amount':fields.float('Montant Annuel max', digit=(5,2)),
        'max_po_amount_no_market':fields.float('Seuil max par commande hors marché', digit=(4,2), help="Montant Max autorisé par commande hors marché"),
        'need_dst':fields.boolean('Need dst check ?', help='Need dst check if purchase is too expensive ?'),
        'need_elu':fields.boolean('Need elu check ?', help='Need elu check if purchase is too expensive ?'),        
        'code_user_ciril':fields.char('Ciril user code', size=8, help="this field refer to user code from Ciril instance"),
        }
    _defaults = {
        'max_po_amount_no_market':lambda *a: 0.0, 
        'need_dst': lambda *a: True,
        'need_elu': lambda *a: True,
        }
    
res_users()

class res_company(OpenbaseCore):
    _inherit = "res.company"
    _name = "res.company"
    _columns = {
        'base_seuil_po':fields.float('Seuil (Commande Hors Marché) Maximal', digit=(5,2), help='Seuil Maximal pour une Commande hors marché avec qu\'une validation d\'un Elu ne soit nécessaire.'),
        }
    _defaults = {
        'base_seuil_po':0.0}
    
res_company()


class res_partner(OpenbaseCore):
    _inherit = "res.partner"
    _name = "res.partner"
    _columns = {
        'code_tiers_ciril':fields.char('Ciril Partner Code',size=8, help="this field refer to pkey from Ciril instance"),
        }
    
res_partner()



class ir_attachment(OpenbaseCore):
    _inherit = "ir.attachment"
    _name = "ir.attachment"
    _columns = {
        'state':fields.selection([('to_check','A Traiter'),('validated','Facture Validée'),
                                  ('refused','Facture Refusée'),('not_invoice','RAS'),('except_send_mail','Echec envoi du mail'), (('except_send_mail_is_paid','Echec envoi du mail'))], 'Etat', readonly=True),
         'action_date':fields.datetime('Date de la derniere action', readonly=True),
         'engage_done':fields.boolean('Suivi commande Clos',readonly=True),
         'attach_made_done':fields.boolean('Cette Facture Clos cette commande', readonly=True),
         
         'to_pay':fields.selection([('yes', 'Yes'), ('no', 'No')], 'To pay ?'),
         'justif_refuse':fields.text('Justificatif Refus', state={'required':[('state','=','refused')], 'invisible':[('state','!=','refused')]}),
         'send_mail_to_pay':fields.boolean('Send mail "TO PAY" ?'),
         'mail_to_pay_status':fields.selection([('sent', 'Sent'), ('failure', 'Failure')], 'mail "TOPAY" status'),
         
         'is_paid':fields.selection([('yes', 'Yes'), ('no', 'No')], 'Is it paid ?'),
         'justif_refuse_payment':fields.text('Justificatif Refus', state={'required':[('state','=','refused')], 'invisible':[('state','!=','refused')]}),
         'send_mail_is_paid':fields.boolean('Send mail "IS PAID" ?'),
         'mail_is_paid_status':fields.selection([('sent', 'Sent'), ('failure', 'Failure')], 'mail "ISPAID" status'),
         
         'is_invoice': fields.boolean('Is PDF invoice'),
        }
    
    _actions = {
        'confirm': lambda self,cr,uid,record,groups_code: record.is_invoice and record.state in ['to_check', 'except_send_mail'],
        'pay': lambda self,cr,uid,record,groups_code: record.is_invoice and record.state in ['validated', 'except_send_mail', 'except_send_mail_is_paid'],
        }
    
    _defaults = {
        'send_mail_to_pay': lambda *a: False,
        'send_mail_is_paid': lambda *a: False,
        'state':'not_invoice',
        'is_invoice': lambda *a: False,
        }
    
    _order = "create_date"
    
    def apply_state_changes(self, cr, uid, ids, context=None):
        for attach in self.browse(cr, uid, ids, context=context):
            #check here too if attach is invoice, because this method is available too throw xmlrpc call, without passing to write()
            actions = attach.actions
            if attach.is_invoice:
                if 'confirm' in actions or attach.send_mail_to_pay:
                    if attach.to_pay == 'yes':
                        attach.send_invoice_to_pay(context=context)
                    elif attach.to_pay == 'no':
                        attach.refuse_invoice_to_pay(context=context)
                elif 'pay' in actions or attach.send_mail_is_paid:
                    if attach.is_paid == 'yes':
                        pass
                    elif attach.to_pay == 'no':
                        pass
        return
    
    ## Override to evolve state of invoice-attachment
    def write(self, cr, uid, ids, vals, context=None):
        ret = super(ir_attachment, self).write(cr, uid, ids, vals, context=context)
        #retrieve attachment-invoices only and perform state changes
        ret_ids = self.search(cr, uid, [('id', 'in', ids), ('is_invoice', '=', True)], context=context)
        self.apply_state_changes(cr, uid, ret_ids, context=context)
        return ret
    
    #Override to put an attach as a pdf invoice if it responds to the pattern 
    def create(self, cr, uid, vals, context=None):
        attach_id = super(ir_attachment, self).create(cr, uid, vals, context=context)
        attach = self.browse(cr, uid, attach_id, context)
        is_invoice = attach.is_invoice
        if not is_invoice:
            #invoice : F-yyyy-MM-dd-001
            prog = re.compile('F-[1-2][0-9]{3}-[0-1][0-9]-[0-3][0-9]-[0-9]{3}')
            #if attach.res_model == 'purchase.order':
            is_invoice = prog.search(attach.datas_fname)
            attach.write({'is_invoice':is_invoice})
        if is_invoice:
            self.write(cr, uid, [attach_id], {'state':'to_check'}, context=context)
            #Envoye une notification A l'Acheteur pour lui signifier qu'il doit vérifier une facture
            #engage = self.pool.get("purchase.order").browse(cr, uid, attach.res_id, context)
            #self.log(cr, engage.user_id.id, attach_id,_('you have to check invoice %s added at %s on your engage %s') %(attach.datas_fname,fields.date.context_today(self, cr, uid, context), engage.name))
        return attach_id
    
    def send_invoice_to_pay(self, cr, uid, ids, context=None):
        #ids refer to attachment that need to be sent with mail
        #Envoie de la piece jointe en mail au service compta
        if isinstance(ids, list):
            ids = ids[0]
        attach = self.browse(cr, uid, ids, context)
        mail_status = False
        state = 'validated'
        if attach.send_mail_to_pay:
            mail_status = 'sent'
            template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','purchase.order'),('name','like','%Valid%')], context=context)
            if isinstance(template_id, list):
                template_id = template_id[0]
            msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, attach.res_id, force_send=False, context=context)
            self.pool.get("mail.message").write(cr, uid, [msg_id], {'attachment_ids':[(4, ids)]}, context=context)
            self.pool.get("mail.message").send(cr, uid, [msg_id], context)
            if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
                mail_status = 'failure'
                #state = 'except_send_mail'
        vals = {'send_mail_to_pay': False, 'state':state, 'action_date':datetime.now()}
        if mail_status:
            vals.update({'mail_to_pay_status': mail_status})
        self.write(cr, uid, [ids], vals, context)
        
        return {'res_model':'purchase.order',
                'view_mode':'form,tree',
                'target':'current',
                'res_id':attach.res_id,
                'type':'ir.actions.act_window'
                }
    
    def action_refuse_invoice_to_pay(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        return {'type':'ir.actions.act_window',
                'res_model':'openstc.open.engage.refuse.inv.wizard',
                'view_mode':'form',
                'view_type':'form',
                'target':'new',
                'context':{'attach_id':ids}
                }
    #@TODO: Refactor this, to use the same code as send_invoice_to_pay, but with new parameter: 'template_id' 
    def refuse_invoice_to_pay(self, cr, uid, ids, context=None):
        #ids refer to attachment that need to be sent with mail
        #Envoie de la piece jointe en mail au service compta
        if isinstance(ids, list):
            ids = ids[0]
        attach = self.browse(cr, uid, ids, context)
        mail_status = False
        state = 'refused'
        if attach.send_mail_to_pay:
            mail_status = 'sent'
            template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','purchase.order'),('name','like','%Refus%')], context=context)
            if isinstance(template_id, list):
                template_id = template_id[0]
            msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, attach.res_id, force_send=False, context=context)
            self.pool.get("mail.message").write(cr, uid, [msg_id], {'attachment_ids':[(4, ids)]}, context=context)
            self.pool.get("mail.message").send(cr, uid, [msg_id], context)
            if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
                mail_status = 'failure'
                #state = 'except_send_mail'
        vals = {'send_mail_to_pay': False, 'state':state, 'action_date':datetime.now()}
        if mail_status:
            vals.update({'mail_to_pay_status': mail_status})
        self.write(cr, uid, [ids], vals, context)
        
        return {'type':'ir.actions.act_window',
        'res_model':'openstc.open.engage.refuse.inv.wizard',
        'view_mode':'form',
        'view_type':'form',
        'target':'new',
        'context':{'attach_id':ids}
        }
    
    #Action du Boutton Permettant de Clore le suivi commande
    #Bloque s'il reste des factures à valider (état 'to_check' ou 'except_send_mail')
    #TOCHECK: Faut-il envoyer un mail de confirmation au service compta etc... ?
    def engage_complete(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        attach = self.browse(cr, uid, ids, context)
        attach_ids = self.search(cr, uid, [('res_id','=',attach.res_id),('res_model','=','purchase.order'),('state','=','to_check')], context=context)
        if attach_ids:
            raise osv.except_osv(_('Error'), _('you can not end this engage because some invoices attached have to be checked'))
        else:
            if self.pool.get("purchase.order").browse(cr, uid, attach.res_id, context).reception_ok:
                self.write(cr, uid, [attach.id], {'attach_made_done':True},context=context)
                self.pool.get("purchase.order").engage_done(cr, uid, [attach.res_id])
            else:
                raise osv.except_osv(_('Error'), _('you can not end this engage because some products are waiting for reception (do it in OpenERP)'))
        return {'res_model':'purchase.order',
                'view_mode':'form,tree',
                'target':'current',
                'res_id':attach.res_id,
                'type':'ir.actions.act_window'
                }
    
ir_attachment()