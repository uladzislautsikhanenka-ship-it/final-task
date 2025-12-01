# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class TrainingGroup(models.Model):
    _name = 'training.group'
    _description = 'Группа для тренировок'
    _order = 'name'

    name = fields.Char(
        string='Название группы',
        required=True,
        help='Название группы'
    )
    
    training_type_id = fields.Many2one(
        'training.type',
        string='Тип тренировки',
        required=True,
        domain=[('category', '=', 'group')],
        help='Тип групповой тренировки'
    )
    
    min_participants = fields.Integer(
        string='Минимальное количество участников',
        required=True,
        help='Минимальное количество участников в группе'
    )
    
    max_participants = fields.Integer(
        string='Максимальное количество участников',
        required=True,
        help='Максимальное количество участников в группе'
    )
    
    participant_ids = fields.Many2many(
        'res.partner',
        'training_group_participant_rel',
        'group_id',
        'partner_id',
        string='Участники',
        domain=[('is_company', '=', False), ('is_employee', '=', False), ('telegram_chat_id', '!=', False)],
        help='Участники группы'
    )
    
    participant_count = fields.Integer(
        string='Количество участников',
        compute='_compute_participant_count',
        store=True,
        help='Текущее количество участников в группе'
    )
    
    active = fields.Boolean(
        string='Активна',
        default=True,
        help='Активна ли группа'
    )
    
    @api.depends('participant_ids')
    def _compute_participant_count(self):
        """Вычисляет количество участников"""
        for group in self:
            group.participant_count = len(group.participant_ids)
    
    @api.onchange('training_type_id')
    def _onchange_training_type_id(self):
        """Обновляет min_participants и max_participants при выборе типа тренировки"""
        if self.training_type_id:
            self.min_participants = self.training_type_id.min_participants
            self.max_participants = self.training_type_id.max_participants
    
    @api.constrains('participant_ids', 'min_participants', 'max_participants')
    def _check_participants_limit(self):
        """Проверяет лимит участников (минимум и максимум)"""
        for group in self:
            participant_count = len(group.participant_ids)
            if participant_count < group.min_participants:
                raise ValidationError(
                    _('Количество участников (%d) меньше минимального (%d). Необходимо добавить еще участников.') % (
                        participant_count,
                        group.min_participants
                    )
                )
            if participant_count > group.max_participants:
                raise ValidationError(
                    _('Количество участников (%d) превышает максимальное (%d). Необходимо удалить лишних участников.') % (
                        participant_count,
                        group.max_participants
                    )
                )
    
    def write(self, vals):
        """Переопределяем write для отправки уведомлений при добавлении участников"""
        # Получаем старые участники до изменения
        old_participants = {}
        if 'participant_ids' in vals:
            for group in self:
                old_participants[group.id] = set(group.participant_ids.ids)
        
        result = super().write(vals)
        
        # Отправляем уведомления новым участникам
        if 'participant_ids' in vals:
            for group in self:
                new_participants = set(group.participant_ids.ids)
                old_participants_set = old_participants.get(group.id, set())
                
                # Находим новых участников
                added_participants = new_participants - old_participants_set
                
                if added_participants:
                    # Получаем всех участников группы для формирования списка
                    all_participants = group.participant_ids
                    
                    # Формируем список участников через дефис, каждый с новой строки
                    participants_list = '\n'.join([f'- {p.name}' for p in all_participants])
                    
                    # Формируем сообщение
                    message = f"Вас добавили в группу - {group.name}\n\nСостав группы:\n{participants_list}"
                    
                    # Отправляем сообщение каждому новому участнику
                    for partner_id in added_participants:
                        partner = self.env['res.partner'].browse(partner_id)
                        if partner.exists() and partner.telegram_chat_id:
                            try:
                                partner._send_telegram_message(message)
                                _logger.info(
                                    "Отправлено уведомление о добавлении в группу '%s' участнику %s (ID: %s)",
                                    group.name,
                                    partner.name,
                                    partner.id
                                )
                            except Exception as e:
                                _logger.exception(
                                    "Ошибка при отправке уведомления участнику %s (ID: %s) о добавлении в группу '%s': %s",
                                    partner.name,
                                    partner.id,
                                    group.name,
                                    e
                                )
        
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        """Переопределяем create для отправки уведомлений при создании группы с участниками"""
        groups = super().create(vals_list)
        
        # Отправляем уведомления участникам, если они были указаны при создании
        for group in groups:
            if group.participant_ids:
                # Формируем список участников через дефис, каждый с новой строки
                participants_list = '\n'.join([f'- {p.name}' for p in group.participant_ids])
                
                # Формируем сообщение
                message = f"Вас добавили в группу - {group.name}\n\nСостав группы:\n{participants_list}"
                
                # Отправляем сообщение каждому участнику
                for partner in group.participant_ids:
                    if partner.telegram_chat_id:
                        try:
                            partner._send_telegram_message(message)
                            _logger.info(
                                "Отправлено уведомление о добавлении в группу '%s' участнику %s (ID: %s)",
                                group.name,
                                partner.name,
                                partner.id
                            )
                        except Exception as e:
                            _logger.exception(
                                "Ошибка при отправке уведомления участнику %s (ID: %s) о добавлении в группу '%s': %s",
                                partner.name,
                                partner.id,
                                group.name,
                                e
                            )
        
        return groups
    
    def action_delete(self):
        """Удаляет группу"""
        self.ensure_one()
        self.unlink()
        return {
            'type': 'ir.actions.act_window_close',
        }

