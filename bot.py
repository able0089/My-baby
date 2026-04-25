import discord
import sys
import os
import re
from collections import defaultdict
import random
import urllib.request
import json

print("Bot starting...", flush=True)

# ── Config ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_KEY    = os.environ.get("GEMINI_API_KEY")

if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN missing!", flush=True)
    sys.exit(1)
if not GEMINI_KEY:
    print("ERROR: GEMINI_API_KEY missing!", flush=True)
    sys.exit(1)

print("Env vars OK", flush=True)

POKETWO_ID = 716390085896962058

COMMAND_CONTEXTS = [
    (re.compile(r"<@716390085896962058>\s+catch\s+(\S+)", re.I),
     lambda m: f"trying to catch a {m.group(1)} using Pokétwo"),

    (re.compile(r"<@716390085896962058>\s+hint", re.I),
     lambda m: "asking Pokétwo for a hint on the spawned Pokémon"),

    (re.compile(r"<@716390085896962058>\s+info", re.I),
     lambda m: "checking their Pokémon info/IVs on Pokétwo"),

    (re.compile(r"<@716390085896962058>\s+trade", re.I),
     lambda m: "initiating a trade on Pokétwo"),

    (re.compile(r"<@716390085896962058>\s+duel", re.I),
     lambda m: "starting a duel on Pokétwo"),

    (re.compile(r"<@716390085896962058>\s+release", re.I),
     lambda m: "releasing a Pokémon on Pokétwo (letting it go forever)"),

    (re.compile(r"<@716390085896962058>\s+evolve", re.I),
     lambda m: "evolving their Pokémon on Pokétwo"),

    (re.compile(r"<@716390085896962058>\s+select\s+(\S+)", re.I),
     lambda m: f"selecting Pokémon #{m.group(1)} as their active one"),

    # n! = P2A (Pokétwo Assistant)
    (re.compile(r"n!m\s*s", re.I),
     lambda m: "searching the Pokétwo market using P2A (n!m s)"),

    (re.compile(r"n!a\s*s", re.I),
     lambda m: "browsing Pokétwo auctions using P2A (n!a s)"),

    (re.compile(r"n!a\s+b\b", re.I),
     lambda m: "placing a bid on a Pokétwo auction using P2A"),

    (re.compile(r"n!stats\s+(\S+)", re.I),
     lambda m: f"looking up Pokétwo stats for {m.group(1)} using P2A"),

    (re.compile(r"n!b\b", re.I),
     lambda m: "checking their Pokétwo balance using P2A"),

    # pk! = Pickey (your naming/collection bot)
    (re.compile(r"pk!cl\b", re.I),
     lambda m: "viewing their Pokémon collection using Pickey (pk!cl)"),

    (re.compile(r"pk!sh\b", re.I),
     lambda m: "checking their shiny hunt tracker on Pickey (pk!sh)"),

    (re.compile(r"pk!n\b", re.I),
     lambda m: "naming one of their Pokémon using Pickey"),

    (re.compile(r"pk!top\b", re.I),
     lambda m: "checking the Pickey leaderboard (pk!top)"),

    (re.compile(r"pk!help\b", re.I),
     lambda m: "opening the Pickey help menu"),
]

conversation_history = defaultdict(list)

SYSTEM_PROMPT = """You are a chill, witty person hanging out in a Pokétwo Discord server. You talk like a real human — casual, funny, sometimes sarcastic, never robotic.

Context about this server:
- Pokétwo is the main bot — wild Pokémon spawn and users catch them by mentioning the bot
- P2A (prefix n!) is a Pokétwo assistant bot — helps with market search, auctions, stats, balance
- Pickey (prefix pk!) is a custom Pokémon naming and collection management bot

Your vibe:
- Talk like a real Discord user. Lowercase, abbreviations, slang. Not overly formal.
- Read the energy and match it. Someone venting? Be chill. Someone hyped about a shiny? Go off.
- Keep replies SHORT — 1 to 3 sentences. Only go longer if someone asks something detailed.
- Never say "As an AI" or anything robotic. You're just a person in the server.
- You know Pokémon well — types, rarities, evolutions, competitive stuff, lore.
- Emojis sparingly — only when it genuinely fits.
- No bullet points in casual chat. Just talk normally.
- React to things like a person would. Laugh, clap back, hype them up, whatever fits.
- Never be preachy."""

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"

def gemini(messages: list, max_tokens: int = 250) -> str:
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9}
    }).encode()

    req = urllib.request.Request(
        GEMINI_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini error: {e}", flush=True)
        return "lol something broke on my end"


def get_ai_reply(user_id: int, prompt: str) -> str:
    history = conversation_history[user_id]
    history.append({"role": "user", "content": prompt})
    if len(history) > 12:
        history[:] = history[-12:]
    reply = gemini(history)
    history.append({"role": "assistant", "content": reply})
    return reply


def quick_reply(prompt: str) -> str:
    return gemini([{"role": "user", "content": prompt}], max_tokens=150)


def detect_command(content: str):
    for pattern, describe in COMMAND_CONTEXTS:
        m = pattern.search(content)
        if m:
            return describe(m)
    return None


def is_poketwo_catch(message: discord.Message) -> str | None:
    if message.author.id != POKETWO_ID:
        return None
    for embed in message.embeds:
        text = (embed.title or "") + " " + (embed.description or "")
        match = re.search(r"caught (?:a |an )?(?:level \d+ )?(.+?)(?:!|\.)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    content = message.content.lower()
    if "congratulations" in content and "caught" in content:
        match = re.search(r"caught (?:a |an )?(.+?)(?:!|\.)", content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def is_poketwo_spawn(message: discord.Message) -> str | None:
    if message.author.id != POKETWO_ID:
        return None
    for embed in message.embeds:
        text = (embed.title or "") + " " + (embed.description or "")
        if "wild pokémon" in text.lower() or "appeared" in text.lower():
            match = re.search(r"wild (.+?) has appeared", text, re.IGNORECASE)
            return match.group(1).strip() if match else "mystery Pokémon"
    return None


client = discord.Client(intents=discord.Intents.all())


@client.event
async def on_ready():
    print(f"Online as {client.user}", flush=True)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # 1. Pokétwo catch announcement
    pokemon = is_poketwo_catch(message)
    if pokemon:
        reply = quick_reply(
            f"Someone just caught a {pokemon} in Pokétwo. React like a real Discord person — "
            f"funny, hyped, or sarcastic depending on how rare or trash {pokemon} is. 1-2 sentences."
        )
        await message.channel.send(reply)
        return

    # 2. Wild spawn — comment 20% of the time
    spawn = is_poketwo_spawn(message)
    if spawn:
        if random.random() < 0.2:
            reply = quick_reply(
                f"A wild {spawn} just spawned in Pokétwo. One short sentence — worth catching or nah?"
            )
            await message.channel.send(reply)
        return

    # 3. Known bot command
    if message.author.id != POKETWO_ID:
        action = detect_command(message.content)
        if action:
            reply = quick_reply(
                f"{message.author.display_name} is {action}. "
                f"React like a real Discord person watching — casual and funny. 1-2 sentences."
            )
            await message.reply(reply)
            return

    # 4. Bot was pinged
    if client.user in message.mentions:
        user_msg = message.content.replace(f"<@{client.user.id}>", "").strip()
        if not user_msg:
            user_msg = "someone pinged you with no message"
        reply = get_ai_reply(message.author.id, user_msg)
        await message.reply(reply)
        return

    # 5. Ongoing conversation
    if conversation_history[message.author.id]:
        content = message.content.strip()
        if content and not content.startswith("/") and len(content) > 1:
            reply = get_ai_reply(message.author.id, content)
            await message.reply(reply)


print("Connecting to Discord...", flush=True)
client.run(DISCORD_TOKEN)
