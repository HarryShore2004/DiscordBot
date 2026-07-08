import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
async def crashout(ctx, member: discord.Member | None = None):
    if member is None:
        member = ctx.author

    await ctx.send(f"{member.mention} has crashed out. The streak has been reset.")


@bot.command()
async def since(ctx):
    await ctx.send("It has been 0 days since the last crashout.")


if TOKEN is None:
    raise ValueError("DISCORD_TOKEN is missing. Check your .env file.")

bot.run(TOKEN)