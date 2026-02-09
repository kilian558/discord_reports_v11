"""
Discord UI modals and buttons for player moderation system.
Handles user interactions for reporting, messaging, and moderating players.
"""

import discord
from discord.ui import Select, Button, View, Modal
from typing import Optional
import logging

from helpers import (
    get_translation, get_author_name, add_modlog, add_check_to_messages,
    add_emojis_to_messages, only_remove_buttons, get_logs, remove_emojis_to_messages,
    get_playername
)
from action_handler import ActionHandler
from config import (
    MAX_REASON_LENGTH, MAX_MESSAGE_LENGTH, DEFAULT_VIEW_TIMEOUT,
    EXTENDED_VIEW_TIMEOUT, TEMPBAN_WARNING_HOURS, MAX_TEMPBAN_HOURS,
    ZERO_WIDTH_SPACE, COLOR_ERROR
)
from datetime import datetime, timedelta

# Setup logger
logger = logging.getLogger(__name__)


def safe_label(label: Optional[str]) -> str:
    """
    Ensures label is not empty for Discord UI components.
    
    Args:
        label: Label text
        
    Returns:
        Label text or zero-width space if empty
    """
    if label is None or label.strip() == "":
        return ZERO_WIDTH_SPACE
    return label


async def _safe_defer(interaction: discord.Interaction, ephemeral: bool = True) -> None:
    if interaction.response.is_done():
        return
    await interaction.response.defer(ephemeral=ephemeral)


async def _safe_send(interaction: discord.Interaction, content: str, ephemeral: bool = True) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral)


def _normalize_ai_message(text: str) -> str:
    if not text:
        return text

    discord_link = "https://discord.gg/gbg-hll"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = []

    for line in lines:
        if line.lower().startswith("betreff:"):
            continue
        cleaned.append(line.replace(discord_link, "").strip())

    def _append_link(line: str) -> str:
        line = line.rstrip()
        if discord_link in line:
            return line
        return f"{line} {discord_link}".strip()

    appended = False
    for i, line in enumerate(cleaned):
        lower = line.lower()
        if "melde dich" in lower or "contact" in lower:
            cleaned[i] = _append_link(line)
            appended = True
            break

    if not appended and cleaned:
        cleaned[-1] = _append_link(cleaned[-1])

    return "\n".join(cleaned).strip()





class BaseActionButton(discord.ui.Button):
    """
    Base class for action buttons to reduce code duplication.
    
    Attributes:
        api_client: API client for server communication
        player_id: Steam ID of the target player
        user_lang: User's language code
        action: Type of action (Message/Kick/Punish/etc.)
        author_player_id: Steam ID of report author
        author_name: Name of report author
        self_report: Whether this is a self-report
    """
    
    def __init__(
        self,
        label: str,
        custom_id: str,
        style: discord.ButtonStyle,
        api_client,
        player_id: str,
        user_lang: str,
        action: str,
        author_player_id: Optional[str],
        author_name: str,
        self_report: bool
    ):
        super().__init__(style=style, label=safe_label(label), custom_id=custom_id)
        self.api_client = api_client
        self.player_id = player_id
        self.user_lang = user_lang
        self.action = action
        self.author_player_id = author_player_id
        self.author_name = author_name
        self.self_report = self_report
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = ReasonSelect(
                self.user_lang, self.api_client, self.player_id, self.action,
                self.author_player_id, self.author_name, interaction.message, self.self_report
            )
            await view.initialize_view()
            
            # Select appropriate message based on action
            message_key = {
                "Message": "message_placeholder",
                "Kick": "select_kick_reason",
                "Punish": "select_reason",
                "Temp-Ban": "select_reason",
                "Perma-Ban": "select_reason",
                "Remove-From-Squad": "select_reason"
            }.get(self.action, "select_reason")
            
            await interaction.followup.send(
                get_translation(self.user_lang, message_key),
                view=view,
                ephemeral=True
            )
        except discord.NotFound:
            logger.error(f"Interaction expired for {self.action} button")
        except Exception as e:
            logger.error(f"Error in {self.action} button callback: {e}", exc_info=True)


class MessageReportedPlayerButton(BaseActionButton):
    """Button to send a message to the reported player."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang, 
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.secondary, api_client, player_id,
            user_lang, "Message", author_player_id, author_name, self_report
        )


class PunishButton(BaseActionButton):
    """Button to punish a player."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.primary, api_client, player_id,
            user_lang, "Punish", author_player_id, get_author_name() or "Unknown", self_report
        )


class KickButton(BaseActionButton):
    """Button to kick a player from the server."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.primary, api_client, player_id,
            user_lang, "Kick", author_player_id, author_name, self_report
        )


class TempBanButton(BaseActionButton):
    """Button to temporarily ban a player."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.primary, api_client, player_id,
            user_lang, "Temp-Ban", author_player_id, get_author_name() or "Unknown", self_report
        )


class PermaBanButton(BaseActionButton):
    """Button to permanently ban a player."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.red, api_client, player_id,
            user_lang, "Perma-Ban", author_player_id, get_author_name() or "Unknown", self_report
        )


class RemoveFromSquadButton(BaseActionButton):
    """Button to remove a player from their squad."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.primary, api_client, player_id,
            user_lang, "Remove-From-Squad", author_player_id, author_name, self_report
        )


class SwitchTeamNowButton(BaseActionButton):
    """Button to switch a player to the other team immediately."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.primary, api_client, player_id,
            user_lang, "Switch-Team-Now", author_player_id, author_name, self_report
        )


class SwitchTeamOnDeathButton(BaseActionButton):
    """Button to switch a player to the other team on their next death."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.primary, api_client, player_id,
            user_lang, "Switch-Team-On-Death", author_player_id, author_name, self_report
        )


class WatchPlayerButton(BaseActionButton):
    """Button to add a player to the watchlist."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.success, api_client, player_id,
            user_lang, "Watch-Player", author_player_id, author_name, self_report
        )


class UnwatchPlayerButton(BaseActionButton):
    """Button to remove a player from the watchlist."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.gray, api_client, player_id,
            user_lang, "Unwatch-Player", author_player_id, author_name, self_report
        )


class AddCommentButton(BaseActionButton):
    """Button to add a comment/note about a player."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id, user_lang,
                 author_player_id, author_name, self_report):
        super().__init__(
            label, custom_id, discord.ButtonStyle.gray, api_client, player_id,
            user_lang, "Add-Comment", author_player_id, author_name, self_report
        )


class ApplyAIRecommendationButton(discord.ui.Button):
    """Button to apply the AI recommendation only after manual click."""

    def __init__(self, user_lang: str):
        label = safe_label(get_translation(user_lang, "ai_apply_recommendation_button"))
        super().__init__(style=discord.ButtonStyle.success, label=label, custom_id="ai_apply_recommendation")
        self.user_lang = user_lang
        self.disabled = True

    async def callback(self, interaction: discord.Interaction):
        try:
            await _safe_defer(interaction, ephemeral=True)

            view = self.view
            if not view or not getattr(view, "ai_recommendation", None):
                await _safe_send(
                    interaction,
                    get_translation(self.user_lang, "ai_recommendation_missing"),
                    ephemeral=True
                )
                return

            recommendation = view.ai_recommendation
            action = recommendation.get("action", "No-Action")
            reply_suggestion = recommendation.get("reply_suggestion")

            action_reason = recommendation.get("action_reason") or recommendation.get("recommendation") or "AI"
            if action == "Message-Reporter" and reply_suggestion:
                action_reason = reply_suggestion
            action_reason = _normalize_ai_message(action_reason)
            duration = recommendation.get("duration_hours")
            if isinstance(duration, str) and duration.isdigit():
                duration = int(duration)

            if action == "No-Action":
                modlog = get_translation(self.user_lang, "log_ai_recommendation_applied").format(
                    interaction.user.display_name, action, action_reason
                )
                await add_modlog(
                    interaction, modlog, None, self.user_lang, view.api_client,
                    original_message=interaction.message
                )
                await only_remove_buttons(interaction)
                await add_emojis_to_messages(interaction, 'ðŸ—‘', original_message=interaction.message)
                await _safe_send(
                    interaction,
                    get_translation(self.user_lang, "ai_recommendation_applied"),
                    ephemeral=True
                )
                return

            if action == "Temp-Ban" and not isinstance(duration, int):
                await _safe_send(
                    interaction,
                    get_translation(self.user_lang, "ai_recommendation_failed"),
                    ephemeral=True
                )
                return

            await perform_action(
                action, action_reason, view.reported_player_name, view.reported_player_id,
                view.report_author_name, view.report_author_id, interaction.message,
                self.user_lang, view.api_client, interaction, False, duration
            )
        except Exception as e:
            logger.error(f"Error applying AI recommendation: {e}", exc_info=True)
            try:
                await _safe_send(
                    interaction,
                    get_translation(self.user_lang, "ai_apply_failed"),
                    ephemeral=True
                )
            except Exception:
                pass

class MessagePlayerModal(discord.ui.Modal):
    """Modal for sending a direct message to a player."""
    
    def __init__(self, title: str, api_client, player_id: str, user_lang: str,
                 author_name: str, self_report: bool):
        super().__init__(title=get_translation(user_lang, "message_player_modal_title").format(author_name))
        self.api_client = api_client
        self.player_id = player_id
        self.user_lang = user_lang
        self.author_name = author_name
        self.self_report = self_report

        self.message = discord.ui.TextInput(
            label=get_translation(user_lang, "message_label"),
            placeholder=get_translation(user_lang, "message_placeholder"),
            style=discord.TextStyle.long,
            required=True,
            max_length=MAX_MESSAGE_LENGTH
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            message_content = self.message.value
            author_name = self.author_name
            
            players_data = await self.api_client.get_players()
            
            if not players_data or 'result' not in players_data:
                await interaction.response.send_message(
                    get_translation(self.user_lang, "error_retrieving_players"),
                    ephemeral=True
                )
                await add_emojis_to_messages(interaction)
                await only_remove_buttons(interaction)
                return
            
            players_list = players_data['result']
            author_player = next(
                (p for p in players_list if p['name'].lower() == author_name.lower()),
                None
            )
            
            if not author_player:
                await interaction.response.send_message(
                    get_translation(self.user_lang, "author_name_not_found"),
                    ephemeral=True
                )
                await add_emojis_to_messages(interaction)
                await only_remove_buttons(interaction)
                return
            
            player_id = author_player['player_id']
            success = await self.api_client.do_message_player(author_name, player_id, message_content)

            if success:
                confirmation_message = get_translation(self.user_lang, "message_sent_successfully").format(
                    author_name, message_content
                )
            else:
                confirmation_message = get_translation(self.user_lang, "error_sending_message")

            await interaction.response.send_message(confirmation_message, ephemeral=True)
            modlog = get_translation(self.user_lang, "log_message").format(
                interaction.user.display_name, author_name, message_content
            )
            await add_modlog(interaction, modlog, player_id, self.user_lang, self.api_client)
            await add_check_to_messages(interaction)
            
        except discord.NotFound:
            logger.error("Interaction expired in MessagePlayerModal")
        except Exception as e:
            logger.error(f"Error in MessagePlayerModal: {e}", exc_info=True)
            try:
                await interaction.response.send_message(
                    get_translation(self.user_lang, "error_sending_message"),
                    ephemeral=True
                )
            except:
                pass


class MessagePlayerButton(discord.ui.Button):
    """Button to open modal for messaging a player."""
    
    def __init__(self, label: str, custom_id: str, api_client, player_id: str,
                 user_lang: str, self_report: bool):
        super().__init__(style=discord.ButtonStyle.secondary, label=safe_label(label), custom_id=custom_id)
        self.api_client = api_client
        self.player_id = player_id
        self.user_lang = user_lang
        self.self_report = self_report

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        try:
            author_name = get_author_name() or "Unknown"
            modal = MessagePlayerModal(
                get_translation(self.user_lang, "message_player_modal_title"),
                self.api_client, self.player_id, self.user_lang, author_name, self.self_report
            )
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Error opening message modal: {e}", exc_info=True)

class Unjustified_Report(discord.ui.Button):
    """Button to mark a report as unjustified."""
    
    def __init__(self, author_name: str, author_id: Optional[str], user_lang: str, api_client):
        label = safe_label(get_translation(user_lang, "unjustified_report"))
        super().__init__(style=discord.ButtonStyle.secondary, label=label, custom_id="unjustified_report")
        self.author_name = author_name
        self.author_id = author_id
        self.user_lang = user_lang
        self.api_client = api_client

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        try:
            await _safe_defer(interaction, ephemeral=True)
            new_view = discord.ui.View(timeout=None)
            await interaction.message.edit(view=new_view)
            await add_emojis_to_messages(interaction, '❌')
            confirm_message = get_translation(self.user_lang, "unjustified_report_acknowledged")
            await _safe_send(interaction, confirm_message, ephemeral=True)

            if self.author_id:
                message_to_send = get_translation(self.user_lang, "report_not_granted")
                await self.api_client.do_message_player(self.author_name, self.author_id, message_to_send)
                modlog = get_translation(self.user_lang, "log_unjustified").format(interaction.user.display_name)
                await add_modlog(interaction, modlog, None, self.user_lang, self.api_client)
        except Exception as e:
            logger.error(f"Error in Unjustified_Report callback: {e}", exc_info=True)

class No_Action_Button(discord.ui.Button):
    """Button for when wrong player was reported or no action needed."""
    
    def __init__(self, user_lang: str, api_client):
        label = safe_label(get_translation(user_lang, "wrong_player_reported"))
        super().__init__(label=label, style=discord.ButtonStyle.success, custom_id="no_action")
        self.user_lang = user_lang
        self.api_client = api_client

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        try:
            await _safe_defer(interaction, ephemeral=True)
            await only_remove_buttons(interaction)
            modlog = get_translation(self.user_lang, "log_no-action").format(interaction.user.display_name)
            await add_modlog(interaction, modlog, None, self.user_lang, self.api_client)
            confirm_message = get_translation(self.user_lang, "no_action_performed")
            await _safe_send(interaction, confirm_message, ephemeral=True)
            await add_emojis_to_messages(interaction, '🗑')
        except Exception as e:
            logger.error(f"Error in No_Action_Button callback: {e}", exc_info=True)

class Show_logs_button(discord.ui.Button):
    """Button to retrieve and display player logs."""
    
    def __init__(self, view, player_name: str, custom_id: str, user_lang: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=safe_label("Logs"), emoji="📄", custom_id=custom_id)
        self.api_client = view.api_client
        self.player_name = player_name
        self.msg_view = view
        self.user_lang = user_lang

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        try:
            await _safe_defer(interaction, ephemeral=True)
            temp_log_file_path = await get_logs(self.api_client, self.player_name)
            
            if not temp_log_file_path:
                await _safe_send(
                    interaction,
                    get_translation(self.user_lang, "no_logs_found").format(self.player_name),
                    ephemeral=True
                )
            else:
                msg = get_translation(self.user_lang, "logs_for").format(self.player_name)
                await interaction.followup.send(msg, file=discord.File(temp_log_file_path))
            
            self.disabled = True
            emb = interaction.message.embeds[0]
            await interaction.message.edit(embed=emb, view=self.msg_view)
        except Exception as e:
            logger.error(f"Error in Show_logs_button callback: {e}", exc_info=True)

class Manual_process(discord.ui.Button):
    """Button to mark report for manual processing."""
    
    def __init__(self, user_lang: str, api_client):
        label = safe_label(get_translation(user_lang, "button_manual_process"))
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id="manual_process")
        self.user_lang = user_lang
        self.api_client = api_client

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        try:
            await _safe_defer(interaction, ephemeral=True)
            view = Finish_Report_Button(user_lang=self.user_lang, api_client=self.api_client)
            modlog = get_translation(self.user_lang, "log_manual").format(interaction.user.display_name)
            await interaction.message.edit(view=view)
            await add_modlog(interaction, modlog, None, self.user_lang, self.api_client, delete_buttons=False)
            confirm_message = get_translation(self.user_lang, "manual_process_respond")
            await _safe_send(interaction, confirm_message, ephemeral=True)
            await add_emojis_to_messages(interaction, '👀')
        except Exception as e:
            logger.error(f"Error in Manual_process callback: {e}", exc_info=True)

class Finish_Report_Button(discord.ui.View):
    """View with a button to mark manual processing as complete."""
    
    def __init__(self, user_lang: str, api_client):
        super().__init__(timeout=EXTENDED_VIEW_TIMEOUT)
        self.user_lang = user_lang
        self.api_client = api_client
        self.add_buttons()

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        try:
            for item in self.children:
                item.disabled = True
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except Exception as e:
            logger.error(f"Error in Finish_Report_Button timeout: {e}", exc_info=True)

    def add_buttons(self):
        """Add finish button to view."""
        button_label = safe_label(get_translation(self.user_lang, "report_finished"))
        button = Button(label=button_label, style=discord.ButtonStyle.success, custom_id="finished_processing")
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        """Handle finish button click."""
        try:
            await _safe_defer(interaction, ephemeral=True)
            await add_check_to_messages(interaction)
            await only_remove_buttons(interaction)
            await remove_emojis_to_messages(interaction, "👀")
            logmessage = get_translation(self.user_lang, "has_finished_report").format(interaction.user.display_name)
            await add_modlog(
                interaction, logmessage, player_id=None, user_lang=self.user_lang,
                api_client=self.api_client, add_entry=True
            )
        except Exception as e:
            logger.error(f"Error in Finish_Report_Button callback: {e}", exc_info=True)

class ReasonSelect(discord.ui.View):
    """View for selecting a reason for moderation action."""
    
    def __init__(self, user_lang: str, api_client, player_id: str, action: str,
                 author_player_id: Optional[str], author_name: str,
                 original_report_message: discord.Message, self_report: bool):
        super().__init__(timeout=DEFAULT_VIEW_TIMEOUT)
        self.user_lang = user_lang
        self.api_client = api_client
        self.player_id = player_id
        self.reasons = []
        self.action = action
        self.author_player_id = author_player_id
        self.author_name = author_name
        self.player_name = ""
        self.reason = ""
        self.original_report_message = original_report_message
        self.self_report = self_report

    async def initialize_view(self):
        """Initialize the view with reason options asynchronously."""
        try:
            select_label = get_translation(self.user_lang, "select_reason")
            reasons = await self.api_client.get_all_standard_message_config()
            self.reasons = reasons if reasons else []
            self.player_name = await get_playername(self.player_id, self.api_client)
            
            selectinst = Select(placeholder=safe_label(select_label))
            selectinst.min_values = 1
            selectinst.max_values = 1
            
            options = []
            # Add "own reason" option
            own_reason_label = safe_label(get_translation(self.user_lang, "own_reason"))
            options.append(discord.SelectOption(label=own_reason_label, value="empty"))
            
            # Add predefined reasons (max 24, as we already have 1)
            entries = 1
            if reasons and len(reasons) > 0:
                for x, reason in enumerate(reasons):
                    if not reason:
                        continue
                    # Truncate long reasons
                    display_reason = reason[:100] if len(reason) > 100 else reason
                    if len(display_reason) > 0 and entries < 25:
                        options.append(discord.SelectOption(label=safe_label(display_reason), value=str(x)))
                        entries += 1
            
            selectinst.options = options
            selectinst.callback = self.callback
            self.add_item(selectinst)
        except Exception as e:
            logger.error(f"Error initializing ReasonSelect view: {e}", exc_info=True)

    async def callback(self, interaction: discord.Interaction):
        """Handle reason selection."""
        try:
            value = interaction.data["values"][0]
            
            if value != "empty":
                value = int(value)
                reason = self.reasons[value]
            else:
                reason = value
            
            # Get appropriate modal title based on action
            title_key = {
                "Message": "message_player_modal_title",
                "Punish": "punish_name_player",
                "Kick": "kick_name_player",
                "Temp-Ban": "tempban_name_player",
                "Perma-Ban": "perma_name_player",
                "Remove-From-Squad": "remove_from_squad_player"
            }.get(self.action, "message_player_modal_title")
            
            # Use fallback if translation key not found
            title_translation = get_translation(self.user_lang, title_key)
            if title_key in title_translation:
                title = title_translation.format(self.player_name)
            else:
                title = f"{self.action}: {self.player_name}"
            
            await interaction.response.send_modal(
                ReasonInput(
                    reason, self.action, self.player_id, self.user_lang, self.api_client,
                    self.player_name, self.author_player_id, self.author_name,
                    self.original_report_message, self.self_report, title=title
                )
            )
        except Exception as e:
            logger.error(f"Error in ReasonSelect callback: {e}", exc_info=True)

class ReasonInput(discord.ui.Modal):
    """Modal for entering a reason for moderation action."""
    
    def __init__(self, reason: str, action: str, player_id: str, user_lang: str, api_client,
                 player_name: str, author_player_id: Optional[str], author_name: str,
                 original_report_message: discord.Message, self_report: bool, *args, **kwargs) -> None:
        super().__init__(timeout=DEFAULT_VIEW_TIMEOUT, custom_id="reason_input", *args, **kwargs)
        self.user_lang = user_lang
        self.api_client = api_client
        self.player_id = player_id
        self.player_name = player_name
        self.action = action
        self.author_player_id = author_player_id
        self.author_name = author_name
        self.original_report_message = original_report_message
        self.self_report = self_report
        
        # Add reason input field
        if reason != "empty":
            self.add_item(discord.ui.TextInput(
                label=get_translation(self.user_lang, "input_reason"),
                style=discord.TextStyle.long,
                default=reason,
                max_length=MAX_REASON_LENGTH
            ))
        else:
            self.add_item(discord.ui.TextInput(
                label=get_translation(self.user_lang, "input_reason"),
                style=discord.TextStyle.long,
                default="_",
                max_length=MAX_REASON_LENGTH
            ))
        
        # Add duration field for temp bans
        if action == "Temp-Ban":
            self.add_item(discord.ui.TextInput(
                label=get_translation(user_lang, "temp_ban_duration_label"),
                placeholder=get_translation(user_lang, "temp_ban_duration_placeholder"),
                style=discord.TextStyle.short,
                max_length=5
            ))

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            self.reason = self.children[0].value
            duration = None
            
            # Validate duration for temp bans
            if self.action == "Temp-Ban":
                duration_str = self.children[1].value
                try:
                    duration = int(duration_str)
                    if duration <= 0 or duration > MAX_TEMPBAN_HOURS:
                        await interaction.response.send_message(
                            get_translation(self.user_lang, "invalid_duration").format(1, MAX_TEMPBAN_HOURS)
                            if "invalid_duration" in get_translation(self.user_lang, "invalid_duration")
                            else f"Duration must be between 1 and {MAX_TEMPBAN_HOURS} hours.",
                            ephemeral=True
                        )
                        return
                except ValueError:
                    await interaction.response.send_message(
                        get_translation(self.user_lang, "invalid_duration_format")
                        if "invalid_duration_format" in get_translation(self.user_lang, "invalid_duration_format")
                        else "Invalid duration format. Please enter a number.",
                        ephemeral=True
                    )
                    return
            
            # Build confirmation embed
            description = get_translation(self.user_lang, "player_name").format(self.player_name) + "\n"
            description += get_translation(self.user_lang, "steam_id") + ": " + self.player_id + "\n"
            description += get_translation(self.user_lang, "action").format(self.action) + "\n"
            
            if self.action == "Temp-Ban":
                description += get_translation(self.user_lang, "temp_ban_duration_label") + ": " + str(duration) + "\n"
            
            description += get_translation(self.user_lang, "reason") + ": " + self.reason + "\n\n"
            description += get_translation(self.user_lang, "discard_hint")
            
            embed = discord.Embed(
                title=get_translation(self.user_lang, "confirm_action"),
                description=description,
                color=COLOR_ERROR
            )

            # Handle confirmation requirement for long temp bans and perma bans
            if self.action == "Temp-Ban" and duration is not None and duration > TEMPBAN_WARNING_HOURS:
                await interaction.response.send_message(
                    embeds=[embed],
                    ephemeral=True,
                    view=Confirm_Action_Button(
                        self.user_lang, self.api_client, self.player_id, self.player_name,
                        self.action, self.reason, self.author_player_id, self.author_name,
                        self.original_report_message, self.self_report, duration
                    )
                )
            elif self.action == "Perma-Ban":
                await interaction.response.send_message(
                    embeds=[embed],
                    ephemeral=True,
                    view=Confirm_Action_Button(
                        self.user_lang, self.api_client, self.player_id, self.player_name,
                        self.action, self.reason, self.author_player_id, self.author_name,
                        self.original_report_message, self.self_report
                    )
                )
            else:
                # Execute action directly
                await interaction.response.defer(ephemeral=False)
                await perform_action(
                    self.action, self.reason, self.player_name, self.player_id,
                    self.author_name, self.author_player_id, self.original_report_message,
                    self.user_lang, self.api_client, interaction, self.self_report, duration
                )
        except Exception as e:
            logger.error(f"Error in ReasonInput submission: {e}", exc_info=True)
            try:
                await interaction.response.send_message(
                    get_translation(self.user_lang, "error_action"),
                    ephemeral=True
                )
            except:
                pass

class Confirm_Action_Button(discord.ui.View):
    """View with confirmation button for critical actions."""
    
    def __init__(self, user_lang: str, api_client, player_id: str, player_name: str,
                 action: str, reason: str, author_player_id: Optional[str], author_name: str,
                 original_report_message: discord.Message, self_report: bool, duration: Optional[int] = None):
        super().__init__(timeout=EXTENDED_VIEW_TIMEOUT)
        self.user_lang = user_lang
        self.api_client = api_client
        self.player_id = player_id
        self.player_name = player_name
        self.action = action
        self.reason = reason
        self.author_player_id = author_player_id
        self.author_name = author_name
        self.duration = duration
        self.self_report = self_report
        self.original_report_message = original_report_message
        self.add_buttons()

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        try:
            for item in self.children:
                item.disabled = True
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except Exception as e:
            logger.error(f"Error in Confirm_Action_Button timeout: {e}", exc_info=True)

    def add_buttons(self):
        """Add confirm button to view."""
        button_label = safe_label(get_translation(self.user_lang, "confirm"))
        button = Button(label=button_label, style=discord.ButtonStyle.success, custom_id="confirm_action")
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        """Handle confirm button click."""
        try:
            await interaction.response.defer(ephemeral=False)
            await interaction.edit_original_response(view=None)
            await perform_action(
                self.action, self.reason, self.player_name, self.player_id,
                self.author_name, self.author_player_id, self.original_report_message,
                self.user_lang, self.api_client, interaction, self.self_report, self.duration
            )
        except Exception as e:
            logger.error(f"Error in Confirm_Action_Button callback: {e}", exc_info=True)


async def perform_action(
    action: str,
    reason: str,
    player_name: str,
    player_id: str,
    author_name: str,
    author_player_id: Optional[str],
    original_report_message: discord.Message,
    user_lang: str,
    api_client,
    interaction: discord.Interaction,
    self_report: bool,
    duration: Optional[int] = None
) -> None:
    """
    Executes a moderation action using the ActionHandler.
    
    Args:
        action: Type of action (Message/Punish/Kick/Temp-Ban/Perma-Ban)
        reason: Reason for the action
        player_name: Name of the target player
        player_id: Steam ID of the target player
        author_name: Name of the report author
        author_player_id: Steam ID of the report author
        original_report_message: Original report message
        user_lang: User's language code
        api_client: API client for server communication
        interaction: Discord interaction
        self_report: Whether this is a self-report
        duration: Ban duration in hours (for Temp-Ban only)
    """
    try:
        result = None
        
        # Route to appropriate action handler
        if action == "Message":
            result = await ActionHandler.handle_message(
                player_name, player_id, reason, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Message-Reporter":
            if not author_player_id:
                await interaction.followup.send(
                    get_translation(user_lang, "error_sending_message"),
                    ephemeral=True
                )
                return
            result = await ActionHandler.handle_message(
                author_name, author_player_id, reason, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Punish":
            result = await ActionHandler.handle_punish(
                player_name, player_id, reason, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Kick":
            result = await ActionHandler.handle_kick(
                player_name, player_id, reason, user_lang, api_client,
                interaction, author_name, author_player_id, self_report,
                original_report_message
            )
        elif action == "Temp-Ban":
            if duration is None:
                logger.error("Duration not provided for Temp-Ban action")
                await interaction.followup.send(
                    get_translation(user_lang, "error_temp_banning_player"),
                    ephemeral=True
                )
                return
            
            result = await ActionHandler.handle_tempban(
                player_name, player_id, reason, duration, user_lang, api_client,
                interaction, author_name, author_player_id, self_report,
                original_report_message
            )
        elif action == "Perma-Ban":
            result = await ActionHandler.handle_permaban(
                player_name, player_id, reason, user_lang, api_client,
                interaction, author_name, author_player_id, self_report,
                original_report_message
            )
        elif action == "Remove-From-Squad":
            result = await ActionHandler.handle_remove_from_squad(
                player_name, player_id, reason, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Switch-Team-Now":
            result = await ActionHandler.handle_switch_team_now(
                player_name, player_id, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Switch-Team-On-Death":
            result = await ActionHandler.handle_switch_team_on_death(
                player_name, player_id, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Watch-Player":
            result = await ActionHandler.handle_watch_player(
                player_name, player_id, reason, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Unwatch-Player":
            result = await ActionHandler.handle_unwatch_player(
                player_name, player_id, user_lang, api_client,
                interaction, original_report_message
            )
        elif action == "Add-Comment":
            result = await ActionHandler.handle_add_comment(
                player_name, player_id, reason, user_lang, api_client,
                interaction, original_report_message
            )
        else:
            logger.error(f"Unknown action type: {action}")
            await interaction.followup.send(
                get_translation(user_lang, "error_action"),
                ephemeral=True
            )
            return
        
        # Handle result
        if result:
            await interaction.followup.send(result.message, ephemeral=True)
            
            if result.success:
                await add_modlog(
                    interaction, result.modlog, player_id, user_lang, api_client,
                    original_message=original_report_message
                )
                await add_check_to_messages(interaction, original_report_message)
            else:
                await add_emojis_to_messages(interaction, original_message=original_report_message)
                await only_remove_buttons(interaction)
        else:
            logger.error(f"No result returned from action handler for action: {action}")
            await interaction.followup.send(
                get_translation(user_lang, "error_action"),
                ephemeral=True
            )
            
    except Exception as e:
        logger.error(f"Error performing action {action}: {e}", exc_info=True)
        try:
            await interaction.followup.send(
                get_translation(user_lang, "error_action"),
                ephemeral=True
            )
        except:
            pass

