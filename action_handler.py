"""
Action handlers for player moderation actions.
Separates action logic from UI components for better maintainability.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import discord

from helpers import get_translation, get_playername
from config import TEMPBAN_WARNING_HOURS

logger = logging.getLogger(__name__)


class ActionResult:
    """
    Result object for action execution.
    
    Attributes:
        success: Whether the action succeeded
        message: Confirmation or error message
        modlog: Log message for moderation log
    """
    
    def __init__(self, success: bool, message: str, modlog: str = ""):
        self.success = success
        self.message = message
        self.modlog = modlog


class ActionHandler:
    """
    Handles execution of moderation actions on players.
    """
    
    @staticmethod
    async def handle_message(
        player_name: str,
        player_id: str,
        message_content: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Sends a message to a player.
        
        Args:
            player_name: Name of the player
            player_id: Steam ID of the player
            message_content: Message to send
            user_lang: User's language code
            api_client: API client for server communication
            interaction: Discord interaction
            original_report_message: Original report message
            
        Returns:
            ActionResult with success status and messages
        """
        try:
            if not player_name:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "player_name_not_retrieved")
                )
            
            success = await api_client.do_message_player(player_name, player_id, message_content)
            
            if success:
                modlog = get_translation(user_lang, "log_message").format(
                    interaction.user.display_name, player_name, message_content
                )
                confirmation_message = get_translation(user_lang, "message_sent_successfully").format(
                    player_name, message_content
                )
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "error_sending_message")
                )
                
        except Exception as e:
            logger.error(f"Error handling message action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=get_translation(user_lang, "error_sending_message")
            )
    
    @staticmethod
    async def handle_punish(
        player_name: str,
        player_id: str,
        reason: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Punishes a player.
        
        Args:
            player_name: Name of the player
            player_id: Steam ID of the player
            reason: Reason for punishment
            user_lang: User's language code
            api_client: API client for server communication
            interaction: Discord interaction
            original_report_message: Original report message
            
        Returns:
            ActionResult with success status and messages
        """
        try:
            success = await api_client.do_punish(player_id, player_name, reason)
            
            if success:
                modlog = get_translation(user_lang, "log_punish").format(
                    interaction.user.display_name, player_name, reason
                )
                confirmation_message = get_translation(user_lang, "punish_confirmed")
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "error_action")
                )
                
        except Exception as e:
            logger.error(f"Error handling punish action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=get_translation(user_lang, "error_action")
            )
    
    @staticmethod
    async def handle_kick(
        player_name: str,
        player_id: str,
        reason: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        author_name: str,
        author_player_id: Optional[str],
        self_report: bool,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Kicks a player from the server.
        
        Args:
            player_name: Name of the player
            player_id: Steam ID of the player
            reason: Reason for kick
            user_lang: User's language code
            api_client: API client for server communication
            interaction: Discord interaction
            author_name: Name of the report author
            author_player_id: Steam ID of report author
            self_report: Whether this is a self-report
            original_report_message: Original report message
            
        Returns:
            ActionResult with success status and messages
        """
        try:
            if not player_name:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "player_name_not_retrieved")
                )
            
            success = await api_client.do_kick(player_name, player_id, reason)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_kicked_successfully").format(
                    player_name
                )
                modlog = get_translation(user_lang, "log_kick").format(
                    interaction.user.display_name,
                    await get_playername(player_id, api_client),
                    reason
                )
                
                # Notify report author if not self-report
                if not self_report and author_player_id:
                    message_to_author = get_translation(user_lang, "message_to_author_kicked").format(
                        player_name
                    )
                    await api_client.do_message_player(author_name, author_player_id, message_to_author)
                
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "error_kicking_player")
                )
                
        except Exception as e:
            logger.error(f"Error handling kick action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=get_translation(user_lang, "error_kicking_player")
            )
    
    @staticmethod
    async def handle_tempban(
        player_name: str,
        player_id: str,
        reason: str,
        duration: int,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        author_name: str,
        author_player_id: Optional[str],
        self_report: bool,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Temporarily bans a player.
        
        Args:
            player_name: Name of the player
            player_id: Steam ID of the player
            reason: Reason for ban
            duration: Ban duration in hours
            user_lang: User's language code
            api_client: API client for server communication
            interaction: Discord interaction
            author_name: Name of the report author
            author_player_id: Steam ID of report author
            self_report: Whether this is a self-report
            original_report_message: Original report message
            
        Returns:
            ActionResult with success status and messages
        """
        try:
            expire_time = datetime.utcnow() + timedelta(hours=duration)
            expires_at = expire_time.strftime("%Y-%m-%dT%H:%M")
            
            success = await api_client.add_blacklist_record(player_id, reason, expires_at)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_temp_banned_successfully").format(
                    player_name, duration, reason
                )
                modlog = get_translation(user_lang, "log_tempban").format(
                    interaction.user.display_name, player_name, duration, reason
                )
                
                # Notify report author if not self-report
                if not self_report and author_player_id:
                    message_to_author = get_translation(user_lang, "message_to_author_temp_banned").format(
                        player_name
                    )
                    await api_client.do_message_player(author_name, author_player_id, message_to_author)
                
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "error_temp_banning_player")
                )
                
        except Exception as e:
            logger.error(f"Error handling tempban action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=get_translation(user_lang, "error_temp_banning_player")
            )
    
    @staticmethod
    async def handle_permaban(
        player_name: str,
        player_id: str,
        reason: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        author_name: str,
        author_player_id: Optional[str],
        self_report: bool,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Permanently bans a player.
        
        Args:
            player_name: Name of the player
            player_id: Steam ID of the player
            reason: Reason for ban
            user_lang: User's language code
            api_client: API client for server communication
            interaction: Discord interaction
            author_name: Name of the report author
            author_player_id: Steam ID of report author
            self_report: Whether this is a self-report
            original_report_message: Original report message
            
        Returns:
            ActionResult with success status and messages
        """
        try:
            success = await api_client.add_blacklist_record(player_id, reason)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_perma_banned_successfully").format(
                    player_name, reason
                )
                modlog = get_translation(user_lang, "log_perma").format(
                    interaction.user.display_name,
                    await get_playername(player_id, api_client),
                    reason
                )
                
                # Notify report author if not self-report
                if not self_report and author_player_id:
                    message_to_author = get_translation(user_lang, "message_to_author_perma_banned").format(
                        player_name
                    )
                    await api_client.do_message_player(author_name, author_player_id, message_to_author)
                
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "error_perma_banning_player")
                )
                
        except Exception as e:
            logger.error(f"Error handling permaban action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=get_translation(user_lang, "error_perma_banning_player")
            )
    
    @staticmethod
    async def handle_remove_from_squad(
        player_name: str,
        player_id: str,
        reason: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Removes a player from their current squad.
        
        Args:
            player_name: Name of the player
            player_id: Steam ID of the player
            reason: Reason for removal
            user_lang: User's language code
            api_client: API client for server communication
            interaction: Discord interaction
            original_report_message: Original report message
            
        Returns:
            ActionResult with success status and messages
        """
        try:
            success = await api_client.remove_player_from_squad(player_id, reason)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_removed_from_squad_successfully").format(
                    player_name
                ) if "player_removed_from_squad_successfully" in get_translation(user_lang, "player_removed_from_squad_successfully") else f"{player_name} was removed from squad"
                
                modlog = get_translation(user_lang, "log_remove_from_squad").format(
                    interaction.user.display_name, player_name, reason
                ) if "log_remove_from_squad" in get_translation(user_lang, "log_remove_from_squad") else f"{interaction.user.display_name} removed {player_name} from squad: {reason}"
                
                # Send message to the removed player with the reason
                try:
                    player_message = get_translation(user_lang, "message_to_player_removed_from_squad").format(
                        reason
                    ) if "message_to_player_removed_from_squad" in get_translation(user_lang, "message_to_player_removed_from_squad") else f"You have been removed from your squad. Reason: {reason}"
                    
                    await api_client.do_message_player(player_name, player_id, player_message)
                except Exception as msg_error:
                    logger.warning(f"Could not send message to removed player: {msg_error}")
                    # Don't fail the whole operation if message sending fails
                
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(
                    success=False,
                    message=get_translation(user_lang, "error_removing_from_squad") if "error_removing_from_squad" in get_translation(user_lang, "error_removing_from_squad") else "Error removing player from squad"
                )
                
        except Exception as e:
            logger.error(f"Error handling remove from squad action: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=get_translation(user_lang, "error_removing_from_squad") if "error_removing_from_squad" in get_translation(user_lang, "error_removing_from_squad") else "Error removing player from squad"
            )

    @staticmethod
    async def handle_switch_team_now(
        player_name: str,
        player_id: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Switches a player to the other team immediately.
        """
        try:
            success = await api_client.switch_player_now(player_id)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_switched_team_now").format(player_name)
                modlog = get_translation(user_lang, "log_switch_team_now").format(
                    interaction.user.display_name, player_name
                )
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(success=False, message=get_translation(user_lang, "error_switching_team"))
                
        except Exception as e:
            logger.error(f"Error switching team: {e}", exc_info=True)
            return ActionResult(success=False, message=get_translation(user_lang, "error_switching_team"))

    @staticmethod
    async def handle_switch_team_on_death(
        player_name: str,
        player_id: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Switches a player to the other team on their next death.
        """
        try:
            success = await api_client.switch_player_on_death(player_id, by=interaction.user.display_name)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_switched_team_on_death").format(player_name)
                modlog = get_translation(user_lang, "log_switch_team_on_death").format(
                    interaction.user.display_name, player_name
                )
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(success=False, message=get_translation(user_lang, "error_switching_team"))
                
        except Exception as e:
            logger.error(f"Error switching team on death: {e}", exc_info=True)
            return ActionResult(success=False, message=get_translation(user_lang, "error_switching_team"))

    @staticmethod
    async def handle_watch_player(
        player_name: str,
        player_id: str,
        reason: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Adds a player to the watchlist.
        """
        try:
            success = await api_client.watch_player(
                player_id, reason, by=interaction.user.display_name, player_name=player_name
            )
            
            if success:
                confirmation_message = get_translation(user_lang, "player_added_to_watchlist").format(
                    player_name, reason
                )
                modlog = get_translation(user_lang, "log_watch_player").format(
                    interaction.user.display_name, player_name, reason
                )
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(success=False, message=get_translation(user_lang, "error_watch_player"))
                
        except Exception as e:
            logger.error(f"Error watching player: {e}", exc_info=True)
            return ActionResult(success=False, message=get_translation(user_lang, "error_watch_player"))

    @staticmethod
    async def handle_unwatch_player(
        player_name: str,
        player_id: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Removes a player from the watchlist.
        """
        try:
            success = await api_client.unwatch_player(player_id)
            
            if success:
                confirmation_message = get_translation(user_lang, "player_removed_from_watchlist").format(player_name)
                modlog = get_translation(user_lang, "log_unwatch_player").format(
                    interaction.user.display_name, player_name
                )
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(success=False, message=get_translation(user_lang, "error_unwatch_player"))
                
        except Exception as e:
            logger.error(f"Error unwatching player: {e}", exc_info=True)
            return ActionResult(success=False, message=get_translation(user_lang, "error_unwatch_player"))

    @staticmethod
    async def handle_add_comment(
        player_name: str,
        player_id: str,
        comment: str,
        user_lang: str,
        api_client,
        interaction: discord.Interaction,
        original_report_message: Optional[discord.Message] = None
    ) -> ActionResult:
        """
        Adds a comment/note about a player.
        """
        try:
            success = await api_client.post_player_comment(
                player_id, comment, by=interaction.user.display_name
            )
            
            if success:
                confirmation_message = get_translation(user_lang, "comment_added_successfully").format(
                    player_name, comment
                )
                modlog = get_translation(user_lang, "log_add_comment").format(
                    interaction.user.display_name, player_name, comment
                )
                return ActionResult(success=True, message=confirmation_message, modlog=modlog)
            else:
                return ActionResult(success=False, message=get_translation(user_lang, "error_add_comment"))
                
        except Exception as e:
            logger.error(f"Error adding comment: {e}", exc_info=True)
            return ActionResult(success=False, message=get_translation(user_lang, "error_add_comment"))

