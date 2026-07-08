import os
import json
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "crashout_data.json"


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def get_now():
    return datetime.now(timezone.utc)


def datetime_to_string(dt):
    return dt.isoformat()


def string_to_datetime(value):
    return datetime.fromisoformat(value)


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def format_duration(seconds):
    seconds = int(seconds)

    days = seconds // 86400
    seconds %= 86400

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60
    seconds %= 60

    parts = []

    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")

    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    if seconds > 0 or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return ", ".join(parts)


def get_server_data(data, guild_id):
    guild_id = str(guild_id)

    if guild_id not in data:
        data[guild_id] = {}

    return data[guild_id]


def get_user_data(server_data, user_id):
    user_id = str(user_id)
    now = get_now()

    if user_id not in server_data:
        server_data[user_id] = {
            "crashouts": 0,
            "last_crashout": datetime_to_string(now)
        }

    return server_data[user_id]


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild is not None:
        data = load_data()
        server_data = get_server_data(data, message.guild.id)
        get_user_data(server_data, message.author.id)
        save_data(data)

    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
async def crashout(ctx, member: discord.Member | None = None):
    if member is None:
        member = ctx.author

    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    user_data = get_user_data(server_data, member.id)

    now = get_now()
    last_crashout = string_to_datetime(user_data["last_crashout"])
    time_without_crashing_out = now - last_crashout

    user_data["crashouts"] += 1
    user_data["last_crashout"] = datetime_to_string(now)

    save_data(data)

    formatted_time = format_duration(time_without_crashing_out.total_seconds())

    await ctx.send(
        f"🚨 ALERT ALERT 🚨\n\n"
        f"{member.mention} has just crashed out.\n"
        f"They spent **{formatted_time}** without crashing out, "
        f"but today got them.\n\n"
        f"Their total crashouts is now **{user_data['crashouts']}**."
    )


@bot.command()
async def since(ctx, member: discord.Member | None = None):
    if member is None:
        member = ctx.author

    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    user_data = get_user_data(server_data, member.id)
    save_data(data)

    now = get_now()
    last_crashout = string_to_datetime(user_data["last_crashout"])
    time_without_crashing_out = now - last_crashout

    formatted_time = format_duration(time_without_crashing_out.total_seconds())

    await ctx.send(
        f"{member.mention} has gone **{formatted_time}** without crashing out.\n"
        f"Total crashouts: **{user_data['crashouts']}**."
    )


@bot.command()
async def leaderboard(ctx):
    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)

    if not server_data:
        await ctx.send("No crashout data yet.")
        return

    sorted_users = sorted(
        server_data.items(),
        key=lambda item: item[1]["crashouts"],
        reverse=True
    )

    message = "🏆 **Crashout Leaderboard** 🏆\n\n"

    for index, (user_id, user_data) in enumerate(sorted_users[:10], start=1):
        user = ctx.guild.get_member(int(user_id))
        name = user.mention if user else f"Unknown User ({user_id})"

        message += (
            f"**{index}.** {name} — "
            f"{user_data['crashouts']} crashout"
            f"{'s' if user_data['crashouts'] != 1 else ''}\n"
        )

    await ctx.send(message)


if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is missing. Check your .env file.")

bot.run(TOKEN)