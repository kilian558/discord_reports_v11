# helpers.py
"""
Helper functions for the Discord Bot.
Provides utilities for text processing, translation, and Discord interaction handling.
"""

import re
import json
from datetime import datetime
import time
import logging
import tempfile
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import discord

# Setup logger
logger = logging.getLogger(__name__)

# Load the language file
try:
    with open('languages.json', 'r', encoding="utf8") as file:
        languages = json.load(file)
except FileNotFoundError:
    logger.error("languages.json not found!")
    languages = {}


@dataclass
class ReportContext:
    """
    Context object for report handling to avoid global variables.
    
    Attributes:
        author_name: Name of the report author
        author_id: Steam ID of the report author
        player_id: Steam ID of the reported player
        player_name: Name of the reported player
    """
    author_name: Optional[str] = None
    author_id: Optional[str] = None
    player_id: Optional[str] = None
    player_name: Optional[str] = None


def remove_markdown(content: str) -> str:
    """
    Removes Discord markdown formatting from text.
    
    Args:
        content: Text with Discord markdown
        
    Returns:
        Cleaned lowercase text without markdown
    """
    patterns = [r'\*\*', r'__', r'\*', r'~~', r'\`']
    for pattern in patterns:
        content = re.sub(pattern, '', content)
    return content.lower()


def remove_bracketed_content(text: str) -> str:
    """
    Removes all content within square brackets.
    
    Args:
        text: Input text
        
    Returns:
        Text without bracketed content
    """
    return re.sub(r"\[.*?\]", "", text)


def find_player_names(text: str, excluded_words: List[str]) -> List[str]:
    """
    Identifies potential player names in text, excluding certain words.
    
    Args:
        text: Text to search for player names
        excluded_words: List of words to exclude from results
        
    Returns:
        List of potential player names (single and two-word combinations)
    """
    words = text.split()
    potential_names = []
    
    for i in range(len(words)):
        # Single words as potential names if not excluded
        if words[i].lower() not in excluded_words:
            potential_names.append(words[i])

        # Combination of two words if both not excluded
        if i < len(words) - 1:
            if words[i].lower() not in excluded_words and words[i + 1].lower() not in excluded_words:
                potential_names.append(words[i] + " " + words[i + 1])
                
    return potential_names


def get_translation(lang: str, key: str) -> str:
    """
    Fetches the translation for a specific key and language.
    
    Args:
        lang: Language code (e.g., 'en', 'de')
        key: Translation key
        
    Returns:
        Translated string or empty string if not found
    """
    translation = languages.get(lang, {}).get(key, "")
    if not translation:
        logger.warning(f"Translation not found: {lang}.{key}")
    return translation


# Legacy global variable support (deprecated - use ReportContext instead)
_author_name: Optional[str] = None


def set_author_name(name: str) -> None:
    """
    Sets the global author name.
    
    DEPRECATED: Use ReportContext instead. This function uses global state
    which is not thread-safe and should be avoided.
    
    Args:
        name: Author name to set
    """
    global _author_name
    _author_name = name


def get_author_name() -> Optional[str]:
    """
    Gets the global author name.
    
    DEPRECATED: Use ReportContext instead. This function uses global state
    which is not thread-safe and should be avoided.
    
    Returns:
        Current author name or None
    """
    return _author_name


def load_excluded_words(file_path: str) -> List[str]:
    """
    Loads list of words to exclude from player name detection.
    
    Args:
        file_path: Path to JSON file with excluded words
        
    Returns:
        List of excluded words
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data.get("exclude", [])
    except FileNotFoundError:
        logger.error(f"Excluded words file not found: {file_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing excluded words file: {e}")
        return []


def load_autorespond_tigger(file_path: str) -> Dict[str, Any]:
    """
    Loads autorespond trigger configuration.
    
    Args:
        file_path: Path to JSON file with autorespond triggers
        
    Returns:
        Dictionary with autorespond configuration
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        logger.error(f"Autorespond trigger file not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing autorespond trigger file: {e}")
        return {}

def remove_clantags(name: str) -> str:
    """
    Removes clan tags from player names.
    
    Removes clan tags up to 4 characters in square brackets or between | |,
    as well as the specific combination i|i. Also removes special characters and emojis.
    
    Args:
        name: Player name with potential clan tags
        
    Returns:
        Cleaned player name without clan tags
    """
    # Remove clan tags with up to 4 characters in brackets or between | |
    name_without_clantags = re.sub(r"\[.{1,4}?\]|\|.{1,4}?\||i\|i", "", name)
    # Remove special characters and emojis
    name_cleaned = re.sub(r"[^\w\s]", "", name_without_clantags, flags=re.UNICODE)
    return name_cleaned.strip()


async def add_modlog(
    interaction: discord.Interaction,
    logmessage: str,
    player_id: Optional[str],
    user_lang: str,
    api_client,
    original_message: Optional[discord.Message] = None,
    delete_buttons: bool = True,
    add_entry: bool = False
) -> None:
    """
    Adds a moderation log entry to the report embed.
    
    Args:
        interaction: Discord interaction object
        logmessage: Log message to add
        player_id: Steam ID of the player (or False/None to skip comment posting)
        user_lang: User's language code
        api_client: API client for server communication
        original_message: Original report message (fetched if not provided)
        delete_buttons: Whether to remove buttons from the message
        add_entry: Whether to append to existing log field or create new one
    """
    try:
        now = datetime.now()
        date_time = now.strftime("%d.%m.%Y %H:%M:%S:")
        logger.info(f"{date_time}{logmessage}")
        
        # Post comment to player if player_id is provided
        if player_id:
            try:
                await api_client.post_player_comment(player_id, logmessage)
            except Exception as e:
                logger.error(f"Failed to post player comment: {e}", exc_info=True)
        
        # Format log message with Discord timestamp
        actiontime = f"<t:{int(time.time())}:f>: "
        logmessage = actiontime + logmessage
        
        # Fetch original message if not provided
        if not original_message:
            original_message = await interaction.channel.fetch_message(interaction.message.id)
        
        # Update embed
        new_embed = original_message.embeds[0]
        if not add_entry:
            new_embed.add_field(
                name=get_translation(user_lang, "logbook"),
                value=logmessage,
                inline=False
            )
        else:
            value = new_embed.fields[-1].value + "\n" + logmessage
            new_embed.set_field_at(
                index=-1,
                name=new_embed.fields[-1].name,
                value=value,
                inline=False
            )
        
        # Update message
        if delete_buttons:
            await original_message.edit(view=None, embed=new_embed)
        else:
            await original_message.edit(embed=new_embed)
            
    except discord.NotFound:
        logger.error("Message not found when adding modlog")
    except Exception as e:
        logger.error(f"Error adding modlog: {e}", exc_info=True)


async def only_remove_buttons(interaction: discord.Interaction) -> None:
    """
    Removes all buttons from the interaction message.
    
    Args:
        interaction: Discord interaction object
    """
    try:
        original_message = await interaction.channel.fetch_message(interaction.message.id)
        await original_message.edit(view=None)
    except discord.NotFound:
        logger.error("Message not found when removing buttons")
    except Exception as e:
        logger.error(f"Error removing buttons: {e}", exc_info=True)


async def add_check_to_messages(
    interaction: discord.Interaction,
    original_message: Optional[discord.Message] = None
) -> None:
    """
    Adds check mark reactions to the report message and its reference.
    
    Args:
        interaction: Discord interaction object
        original_message: Original message (fetched if not provided)
    """
    try:
        if not original_message:
            original_message = await interaction.channel.fetch_message(interaction.message.id)
        
        await original_message.add_reaction('✅')
        
        if original_message.reference:
            reportmessage = await original_message.channel.fetch_message(
                original_message.reference.message_id
            )
            await reportmessage.add_reaction('✅')
    except discord.NotFound:
        logger.error("Message not found when adding check reactions")
    except Exception as e:
        logger.error(f"Error adding check reactions: {e}", exc_info=True)


async def remove_emojis_to_messages(
    interaction: discord.Interaction,
    emoji: str = '⚠️'
) -> None:
    """
    Removes specific emoji reactions from the report message and its reference.
    
    Args:
        interaction: Discord interaction object
        emoji: Emoji to remove (default: ⚠️)
    """
    try:
        original_message = await interaction.channel.fetch_message(interaction.message.id)
        await original_message.clear_reaction(emoji)
        
        if original_message.reference:
            reportmessage = await original_message.channel.fetch_message(
                original_message.reference.message_id
            )
            await reportmessage.clear_reaction(emoji)
    except discord.NotFound:
        logger.error("Message not found when removing emoji reactions")
    except Exception as e:
        logger.error(f"Error removing emoji reactions: {e}", exc_info=True)


async def add_emojis_to_messages(
    interaction: discord.Interaction,
    emoji: str = '⚠️',
    original_message: Optional[discord.Message] = None
) -> None:
    """
    Adds emoji reactions to the report message and its reference.
    
    Args:
        interaction: Discord interaction object
        emoji: Emoji to add (default: ⚠️)
        original_message: Original message (fetched if not provided)
    """
    try:
        if not original_message:
            original_message = await interaction.channel.fetch_message(interaction.message.id)
        
        await original_message.add_reaction(emoji)
        
        if original_message.reference:
            reportmessage = await original_message.channel.fetch_message(
                original_message.reference.message_id
            )
            await reportmessage.add_reaction(emoji)
    except discord.NotFound:
        logger.error("Message not found when adding emoji reactions")
    except Exception as e:
        logger.error(f"Error adding emoji reactions: {e}", exc_info=True)


async def get_playername(player_id: str, api_client) -> str:
    """
    Gets player name from Steam ID.
    
    Args:
        player_id: Steam ID of the player
        api_client: API client for server communication
        
    Returns:
        Player name or Steam ID if name not found
    """
    try:
        player_name = await api_client.get_player_by_steam_id(player_id)
        return player_name if player_name else player_id
    except Exception as e:
        logger.error(f"Error getting player name for {player_id}: {e}", exc_info=True)
        return player_id


async def get_logs(api_client, player_name: str) -> Optional[str]:
    """
    Retrieves and saves structured logs for a player.
    
    Args:
        api_client: API client for server communication
        player_name: Name of the player
        
    Returns:
        Path to temporary log file or False if no logs found
    """
    try:
        logs = await api_client.get_structured_logs(60, None, player_name)
        
        if not logs or not logs.get('result', {}).get('logs'):
            return False
        
        log_message = ""
        for log in logs['result']['logs']:
            timestamp = datetime.fromtimestamp(log['timestamp_ms'] / 1000)
            timestr = timestamp.strftime("%d.%m.%Y %H:%M:%S")
            log_messages = (
                f"{timestr}: {log['action']} by {log['player_name_1']} - {log['message']}"
            )
            log_message += log_messages + "\n"
        
        if log_message:
            with tempfile.NamedTemporaryFile(
                delete=False,
                mode='w',
                suffix='.txt',
                encoding='utf-8'
            ) as temp_log_file:
                temp_log_file.write(log_message)
                return temp_log_file.name
        
        return False
        
    except Exception as e:
        logger.error(f"Error getting logs for {player_name}: {e}", exc_info=True)
        return False


async def get_playerid_from_name(name: str, api_client) -> Optional[str]:
    """
    Gets Steam ID from player name.
    
    Args:
        name: Player name
        api_client: API client for server communication
        
    Returns:
        Steam ID or None if player not found
    """
    try:
        players_data = await api_client.get_players()
        
        if not players_data or 'result' not in players_data:
            return None
        
        players_list = players_data['result']
        author_player = next(
            (p for p in players_list if p['name'].lower() == name.lower()),
            None
        )
        
        if author_player:
            return author_player['player_id']
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting player ID for {name}: {e}", exc_info=True)
        return None
