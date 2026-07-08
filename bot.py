import os
import json
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.path.join(
    os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "."),
    "crashout_data.json"
)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

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
    """
    New data structure:

    {
        "SERVER_ID": {
            "users": {},
            "reports": []
        }
    }

    This also handles your older save file where users were stored directly
    inside the server ID.
    """
    guild_id = str(guild_id)

    if guild_id not in data:
        data[guild_id] = {
            "users": {},
            "reports": []
        }

    # Migration for old format
    if "users" not in data[guild_id]:
        old_user_data = data[guild_id]
        data[guild_id] = {
            "users": old_user_data,
            "reports": []
        }

    if "reports" not in data[guild_id]:
        data[guild_id]["reports"] = []

    return data[guild_id]


def get_users_data(server_data):
    return server_data["users"]


def get_reports_data(server_data):
    return server_data["reports"]


def get_user_data(server_data, member):
    users_data = get_users_data(server_data)
    user_id = str(member.id)
    now = get_now()

    if user_id not in users_data:
        users_data[user_id] = {
            "crashouts": 0,
            "last_crashout": datetime_to_string(now),
            "display_name": member.display_name,
            "username": member.name
        }
    else:
        users_data[user_id]["display_name"] = member.display_name
        users_data[user_id]["username"] = member.name

        if "crashouts" not in users_data[user_id]:
            users_data[user_id]["crashouts"] = 0

        if "last_crashout" not in users_data[user_id]:
            users_data[user_id]["last_crashout"] = datetime_to_string(now)

    return users_data[user_id]


async def initialise_server_members():
    data = load_data()

    for guild in bot.guilds:
        server_data = get_server_data(data, guild.id)

        async for member in guild.fetch_members(limit=None):
            if not member.bot:
                get_user_data(server_data, member)

    save_data(data)


async def ask_for_text(ctx, user, question, timeout_seconds=180):
    await ctx.send(question)

    def check(message):
        return (
            message.author.id == user.id
            and message.channel.id == ctx.channel.id
            and not message.author.bot
        )

    try:
        message = await bot.wait_for(
            "message",
            timeout=timeout_seconds,
            check=check
        )
        return message.content.strip()

    except TimeoutError:
        return None


async def ask_for_rating(ctx, user, timeout_seconds=180):
    await ctx.send(
        f"{user.mention}, rate this crashout from **1 to 10**."
    )

    def check(message):
        return (
            message.author.id == user.id
            and message.channel.id == ctx.channel.id
            and not message.author.bot
        )

    try:
        message = await bot.wait_for(
            "message",
            timeout=timeout_seconds,
            check=check
        )

        rating = int(message.content.strip())

        if rating < 1 or rating > 10:
            await ctx.send("Rating must be between **1 and 10**. Report cancelled.")
            return None

        return rating

    except ValueError:
        await ctx.send("That was not a valid number. Report cancelled.")
        return None

    except TimeoutError:
        await ctx.send("No rating was given in time. Report cancelled.")
        return None


def create_report_id(reports):
    return len(reports) + 1


def find_report_by_id(reports, report_id):
    for report in reports:
        if report["report_id"] == report_id:
            return report

    return None

def format_report_date(value):
    try:
        created_at = string_to_datetime(value)
        return created_at.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        return "Unknown date"


def shorten_text(text, max_length=80):
    text = str(text)

    if len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."


def build_reports_list_message(reports, title):
    message = f"{title}\n\n"

    for report in reports:
        report_id = report.get("report_id", "Unknown")
        accused_name = report.get("accused_name", "Unknown User")
        reporter_name = report.get("reporter_name", "Unknown Reporter")
        rating = report.get("rating", "Unknown")
        created_at = format_report_date(report.get("created_at", ""))
        reason = shorten_text(report.get("reason", "No reason given."))

        message += (
            f"**Report #{report_id}** — {accused_name}\n"
            f"Rating: **{rating}/10** | Reported by: **{reporter_name}**\n"
            f"Date: **{created_at}**\n"
            f"Reason: {reason}\n"
            f"View full report: `!crashoutreport {report_id}`\n\n"
        )

    return message


async def send_long_message(ctx, message):
    """
    Discord has a message length limit.
    This splits long report lists into multiple messages.
    """
    max_length = 1900

    if len(message) <= max_length:
        await ctx.send(message)
        return

    current_message = ""

    for line in message.splitlines(keepends=True):
        if len(current_message) + len(line) > max_length:
            await ctx.send(current_message)
            current_message = line
        else:
            current_message += line

    if current_message:
        await ctx.send(current_message)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await initialise_server_members()
    print("All server member timers have been initialised.")


@bot.event
async def on_member_join(member):
    if member.bot:
        return

    data = load_data()
    server_data = get_server_data(data, member.guild.id)
    get_user_data(server_data, member)
    save_data(data)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild is not None:
        data = load_data()
        server_data = get_server_data(data, message.guild.id)
        get_user_data(server_data, message.author)
        save_data(data)

    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
async def crashout(ctx, member: discord.Member | None = None):
    if member is None:
        await ctx.send("You need to mention who crashed out. Example: `!crashout @user`")
        return

    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    reports = get_reports_data(server_data)

    accused_user_data = get_user_data(server_data, member)
    reporter_user_data = get_user_data(server_data, ctx.author)

    now = get_now()
    last_crashout = string_to_datetime(accused_user_data["last_crashout"])
    time_without_crashing_out = now - last_crashout

    accused_user_data["crashouts"] += 1
    accused_user_data["last_crashout"] = datetime_to_string(now)
    accused_user_data["display_name"] = member.display_name
    accused_user_data["username"] = member.name

    reporter_user_data["display_name"] = ctx.author.display_name
    reporter_user_data["username"] = ctx.author.name

    formatted_time = format_duration(time_without_crashing_out.total_seconds())

    await ctx.send(
        f"🚨 ALERT ALERT 🚨\n\n"
        f"{member.mention} has just crashed out.\n"
        f"They spent **{formatted_time}** without crashing out, "
        f"but today got them.\n\n"
        f"Their total crashouts is now **{accused_user_data['crashouts']}**."
    )

    reason = await ask_for_text(
        ctx,
        ctx.author,
        f"{ctx.author.mention}, fill out the crashout report.\n"
        f"Why did {member.mention} crash out?"
    )

    if reason is None:
        await ctx.send("Crashout report cancelled because no reason was given.")
        save_data(data)
        return

    rating = await ask_for_rating(ctx, ctx.author)

    if rating is None:
        save_data(data)
        return

    accused_response = await ask_for_text(
        ctx,
        member,
        f"{member.mention}, you have been accused of crashing out.\n"
        f"Reply with your side of the crashout."
    )

    if accused_response is None:
        accused_response = "No response was given."

    report_id = create_report_id(reports)

    report = {
        "report_id": report_id,
        "created_at": datetime_to_string(now),
        "reporter_id": str(ctx.author.id),
        "reporter_name": ctx.author.display_name,
        "accused_id": str(member.id),
        "accused_name": member.display_name,
        "time_without_crashing_out": formatted_time,
        "reason": reason,
        "rating": rating,
        "accused_response": accused_response
    }

    reports.append(report)
    save_data(data)

    await ctx.send(
        f"📄 **Crashout Report #{report_id} Saved**\n\n"
        f"Accused: **{member.display_name}**\n"
        f"Reported by: **{ctx.author.display_name}**\n"
        f"Rating: **{rating}/10**\n\n"
        f"Use `!crashoutreport {report_id}` to view it later."
    )


@bot.command()
async def since(ctx, member: discord.Member | None = None):
    if member is None:
        member = ctx.author

    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    user_data = get_user_data(server_data, member)
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
    users_data = get_users_data(server_data)

    if not users_data:
        await ctx.send("No crashout data yet.")
        return

    sorted_users = sorted(
        users_data.items(),
        key=lambda item: item[1].get("crashouts", 0),
        reverse=True
    )

    now = get_now()

    message = "🏆 **Crashout Leaderboard** 🏆\n\n"

    for index, (user_id, user_data) in enumerate(sorted_users, start=1):
        member = ctx.guild.get_member(int(user_id))

        if member:
            name = member.display_name
        else:
            name = user_data.get("display_name", "Unknown User")

        crashout_count = user_data.get("crashouts", 0)

        last_crashout = string_to_datetime(user_data["last_crashout"])
        time_since_last_crashout = now - last_crashout
        formatted_time = format_duration(time_since_last_crashout.total_seconds())

        message += (
            f"**{index}. {name}**\n"
            f"Crashouts: **{crashout_count}**\n"
            f"Time since last crashout: **{formatted_time}**\n\n"
        )

    await send_long_message(ctx, message)


@bot.command()
async def crashoutreports(ctx):
    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    reports = get_reports_data(server_data)

    if not reports:
        await ctx.send("There are no crashout reports yet.")
        return

    message = "📚 **Crashout Reports** 📚\n\n"

    for report in reports[-10:]:
        message += (
            f"**Report #{report['report_id']}** — "
            f"{report['accused_name']} rated **{report['rating']}/10**\n"
            f"Reported by: {report['reporter_name']}\n"
            f"Use `!crashoutreport {report['report_id']}` to view this report.\n\n"
        )

    await ctx.send(message)


@bot.command()
async def crashoutreport(ctx, report_id: int):
    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    reports = get_reports_data(server_data)

    report = find_report_by_id(reports, report_id)

    if report is None:
        await ctx.send(f"No crashout report found with ID `{report_id}`.")
        return

    await ctx.send(
        f"📄 **Crashout Report #{report['report_id']}**\n\n"
        f"**Accused:** {report['accused_name']}\n"
        f"**Reported by:** {report['reporter_name']}\n"
        f"**Crashout rating:** {report['rating']}/10\n"
        f"**Time they survived before crashing out:** {report['time_without_crashing_out']}\n\n"
        f"**Reason for crashout:**\n"
        f"{report['reason']}\n\n"
        f"**Their side of the story:**\n"
        f"{report['accused_response']}"
    )

@bot.command()
async def mycrashouts(ctx):
    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    reports = get_reports_data(server_data)

    user_reports = [
        report for report in reports
        if report.get("accused_id") == str(ctx.author.id)
    ]

    if not user_reports:
        await ctx.send(f"{ctx.author.mention}, you have no crashout reports yet.")
        return

    user_reports = sorted(
        user_reports,
        key=lambda report: report.get("report_id", 0),
        reverse=True
    )

    message = build_reports_list_message(
        user_reports,
        f"📕 **{ctx.author.display_name}'s Crashout Reports**"
    )

    await send_long_message(ctx, message)


@bot.command()
async def seecrashouts(ctx, member: discord.Member | None = None):
    if member is None:
        await ctx.send("You need to mention a user. Example: `!seecrashouts @user`")
        return

    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    reports = get_reports_data(server_data)

    user_reports = [
        report for report in reports
        if report.get("accused_id") == str(member.id)
    ]

    if not user_reports:
        await ctx.send(f"{member.mention} has no crashout reports yet.")
        return

    user_reports = sorted(
        user_reports,
        key=lambda report: report.get("report_id", 0),
        reverse=True
    )

    message = build_reports_list_message(
        user_reports,
        f"📕 **{member.display_name}'s Crashout Reports**"
    )

    await send_long_message(ctx, message)


@bot.command()
async def servercrashouts(ctx):
    data = load_data()
    server_data = get_server_data(data, ctx.guild.id)
    reports = get_reports_data(server_data)

    if not reports:
        await ctx.send("There are no crashout reports in this server yet.")
        return

    reports = sorted(
        reports,
        key=lambda report: report.get("report_id", 0),
        reverse=True
    )

    message = build_reports_list_message(
        reports,
        "🌍 **Full Server Crashout Report List**"
    )

    await send_long_message(ctx, message)

if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is missing. Check your .env file.")

bot.run(TOKEN)