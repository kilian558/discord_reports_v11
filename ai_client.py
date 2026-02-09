import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, api_key: Optional[str], model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning")
        self.base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1/chat/completions")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def get_recommendation(
        self,
        report_text: str,
        reported_player_name: str,
        player_stats: Optional[Dict[str, Any]],
        user_lang: str,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("GROK_API_KEY is not set")

        system_prompt = (
            "You are a moderation assistant for an 18+ multiplayer game. "
            "You NEVER execute actions. You ONLY recommend. "
            "Return a single JSON object and nothing else."
        )

        detected_lang = self._detect_language(report_text)
        user_prompt = (
            "Analyze the report and recommend a moderation action.\n"
            "Allowed actions:\n"
            "- Perma-Ban\n"
            "- Temp-Ban\n"
            "- Kick\n"
            "- Punish\n"
            "- Remove-From-Squad\n"
            "- Switch-Team-Now\n"
            "- Message-Reporter\n"
            "- No-Action\n"
            "\n"
            "Rules and examples:\n"
            "- Antisemitic/racist/hate speech -> Perma-Ban.\n"
            "- Strong insults/harassment -> Temp-Ban (provide hours).\n"
            "- For Temp-Ban, pick a duration in hours that fits severity; do not default to a fixed number.\n"
            "- Mild profanity like 'fuck' in an 18+ game -> No-Action.\n"
            "- \"redet nicht\" (not communicating in squad) -> Remove-From-Squad.\n"
            "- If uncertain, choose the less severe option.\n"
            "- If the report doesn't match a listed rule, still recommend a sensible action based on severity.\n"
            "- Provide a well-written action_reason for any action. This is the ban/kick reason used in the action.\n"
            "- action_reason must include https://discord.gg/gbg-hll and must NOT include gbg-hll.com.\n"
            "- If the report is clearly 100% German, write action_reason in German.\n"
            "- If there is any uncertainty or English in the report, write action_reason in English.\n"
            "- If the report text is a question or incomplete, also provide a sensible response in the same language.\n"
            "- For light offenses suggest Kick; for medium offenses suggest Temp-Ban; for severe offenses suggest Perma-Ban.\n"
            "- Any racist or antisemitic terms -> Perma-Ban.\n"
            "- If the report is unclear or asks for help, suggest sending a message (reply_suggestion) to the reporter.\n"
            "- Always recommend actions for the reported player; if no player is reported, treat the reporter as the target.\n"
            "- Players can report other players; the action must target the reported player only.\n"
            "- For No-Action without reply_suggestion, use recommendation text \"Trash\".\n"
            "- If reply_suggestion exists, do NOT use \"Trash\"; set recommendation to a short \"Nachfrage\" note.\n"
            "- For Remove-From-Squad, use recommendation text \"Remove player from squad\".\n"
            "\n"
            "Server context:\n"
            "- The community is GBG HLL (gbg-hll.com / https://discord.gg/gbg-hll).\n"
            "- Seeding means the server is in early warmup with rules limiting full gameplay.\n"
            "- Seeding ends only when admins announce it via a message to everyone.\n"
            "- If a player asks about seeding or map release, reply_suggestion should explain this clearly.\n"
            "- If a player asks about switching servers, ask which server they want and why.\n"
            "- If a player asks to switch teams, suggest action Switch-Team-Now.\n"
            "- Use the rules below as knowledge, but explain in your own words.\n"
            "- If a report is about a rule, reference the rule content in plain language.\n"
            "\n"
            "GBG rules knowledge (DE/EN topics to recognize):\n"
            "- Streaming without overlay or 15 min delay is forbidden; violations can lead to Perma-Ban.\n"
            "- Officers/SL require a microphone; no mic/no comms can be punished.\n"
            "- No closed tank & recon squads; closed solo inf squad allowed only with mic.\n"
            "- Squads must have an SL or they can be dissolved.\n"
            "- Seeding rules: up to 30v30 mid-cap only; up to 29 players no tanks/arty.\n"
            "- Red zone movement after mid-cap can be punished; violations can lead to kick/punish.\n"
            "- Vote-kick abuse: must state reason; abuse can lead to temp-bans; single TK is not enough for vote-kick.\n"
            "- Intentional teamkilling is punishable.\n"
            "- Toxic chat, excessive trolling are punishable.\n"
            "- Political/religious statements/names are prohibited (EN rules).\n"
            "\n"
            "Common reasons to address (write them in your own words, do NOT copy templates):\n"
            "- Name violation (name doesn't meet criteria)\n"
            "- Streaming without overlay/delay\n"
            "- No mic / no communication for required roles\n"
            "- Racist / antisemitic language\n"
            "- Solo closed tank squad\n"
            "- Vote kick abuse\n"
            "- Intentional team killing\n"
            "- Toxic behavior in chat\n"
            "- Excessive trolling\n"
            "\n"
            "Style guidance for action_reason:\n"
            "- Write a short, clear, polite notice addressed to the reported player by name.\n"
            "- Include: greeting, reason, duration (if any), and a polite closing.\n"
            "- Explain what happened and why the action was taken.\n"
            "- For severe offenses, be firm and clear, not lenient.\n"
            "- Keep it factual, non-aggressive, and player-specific.\n"
            "- Do not include gbg-hll.com in action_reason.\n"
            "- Include a Discord contact line before the closing, with https://discord.gg/gbg-hll.\n"
            "- Do NOT use a fixed template; vary wording each time.\n"
            "- action_reason should describe the Maßnahme/ban reason (what will be applied).\n"
            "- Put the violation description in rationale (Verstoß) for admin display only.\n"
            "\n"
            "Style guidance for reply_suggestion (if needed):\n"
            "- Address the reporter by name if available.\n"
            "- Ask clarifying questions or give a helpful response.\n"
            "- The reply is sent in-game; do not ask for screenshots or clips.\n"
            "- reply_suggestion must include https://discord.gg/gbg-hll and must NOT include gbg-hll.com.\n"
            "- Use the report language (German only if clearly 100% German).\n"
            "- Use the same structured tone: greeting, request/answer, polite closing.\n"
            "\n"
            "Examples (structure only, do not copy text):\n"
            "- Mild insult -> Punish, short warning to player.\n"
            "- Hate speech -> Perma-Ban, clear reason.\n"
            "- Vague report like \"macht nur tk\" -> reply_suggestion asking for details.\n"
            "- Player asks a question -> reply_suggestion with a helpful answer.\n"
            "\n"
            "Return JSON with keys:\n"
            "- action (string, one of the allowed actions)\n"
            "- duration_hours (integer or null; required for Temp-Ban)\n"
            "- recommendation (short sentence for admins, ALWAYS in German; must state the action that would be executed)\n"
            "- action_reason (short reason to use for the action)\n"
            "- rationale (violation description for admins, ALWAYS in German)\n"
            "- reply_suggestion (optional; response to reporter if report is a question/incomplete)\n"
            "\n"
            "Consistency rules:\n"
            "- If action is No-Action and reply_suggestion exists, recommendation should say to request clarification.\n"
            "- If reply_suggestion exists, set action to Message-Reporter.\n"
            "- Use a single language per field; do not mix German and English in the same field.\n"
            "- Teamkill rule: KICK only if teamkills >= 2. Do NOT kick for a single teamkill.\n"
            "- If the report text is English, reply_suggestion must be English.\n"
            "- If the report text is German, reply_suggestion must be German.\n"
            "- If the report is just a general complaint/opinion without a concrete violation, use No-Action and no reply_suggestion.\n"
            "- Only use reply_suggestion when the report explicitly asks a question or lacks key details about a clear violation.\n"
            "\n"
            f"Reported player: {reported_player_name}\n"
            f"Report text: {report_text}\n"
            f"Player stats: {player_stats if player_stats else 'unknown'}\n"
            f"Detected report language: {detected_lang}\n"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=60)
        max_attempts = int(os.getenv("GROK_MAX_ATTEMPTS", "2"))
        retry_backoff = float(os.getenv("GROK_RETRY_BACKOFF_SECONDS", "1.5"))
        text = ""
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(1, max_attempts + 1):
                try:
                    async with session.post(self.base_url, headers=headers, json=payload) as response:
                        text = await response.text()
                        if response.status != 200:
                            message = text
                            try:
                                error_payload = json.loads(text)
                                if isinstance(error_payload, dict):
                                    err = error_payload.get("error") or error_payload
                                    message = err.get("message", err) if isinstance(err, dict) else err
                            except Exception:
                                pass
                            logger.error("Grok API error %s: %s", response.status, message)
                            raise RuntimeError(f"Grok API error {response.status}: {message}")
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    if attempt >= max_attempts:
                        raise RuntimeError(f"Grok request failed: {exc.__class__.__name__}") from exc
                    await asyncio.sleep(retry_backoff * attempt)

        data = self._extract_json(text)
        if not data:
            logger.error("Failed to parse Grok response: %s", text)
            raise RuntimeError("Grok response parsing failed")

        return data

    def _extract_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(raw_text)
            if isinstance(payload, dict) and "error" in payload:
                logger.error("Grok API error response: %s", payload.get("error"))
                return None
            content = payload["choices"][0]["message"]["content"]
        except Exception:
            content = raw_text

        try:
            if isinstance(content, dict):
                return content
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    def _detect_language(self, text: str) -> str:
        if not text:
            return "en"
        sample = text.lower()
        de_markers = [
            " der ", " die ", " das ", " und ", " nicht ", " bitte ",
            " wegen ", " aber ", " auch ", " du ", " dein ", " eine ",
        ]
        en_markers = [
            " the ", " and ", " not ", " please ", " because ", " but ",
            " also ", " you ", " your ", " a ", " an ",
        ]
        de_score = sum(1 for m in de_markers if m in sample)
        en_score = sum(1 for m in en_markers if m in sample)
        for ch in "äöüß":
            if ch in sample:
                de_score += 2
        return "de" if de_score >= en_score else "en"
