# code_comment_style: English, explanation_style: Vietnamese
import discord
from discord.ext import commands
import aiohttp
import os
import shlex
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

AIRFLOW_API_URL = os.getenv(
    "AIRFLOW_API_URL",
    "http://localhost:8080/api/v1/dags/auto_data_pipeline/dagRuns",
)
AIRFLOW_USER = os.getenv("AIRFLOW_USER", "admin")
AIRFLOW_PASS = os.getenv("AIRFLOW_PASSWORD", os.getenv("AIRFLOW_PASS", "admin"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


def parse_search_args(args: str) -> tuple[str, int]:
    tokens = shlex.split(args)
    keyword_parts: list[str] = []
    pages = 1
    idx = 0

    while idx < len(tokens):
        token = tokens[idx]
        if token in ("-k", "--keyword"):
            idx += 1
            while idx < len(tokens) and tokens[idx] not in ("-p", "--pages"):
                keyword_parts.append(tokens[idx])
                idx += 1
            continue
        if token in ("-p", "--pages"):
            idx += 1
            if idx >= len(tokens):
                raise ValueError("Missing page count after -p/--pages")
            try:
                pages = int(tokens[idx])
            except ValueError as exc:
                raise ValueError("Page count must be a positive integer") from exc
            if pages < 1:
                raise ValueError("Page count must be a positive integer")
        idx += 1

    keyword = " ".join(keyword_parts).strip()
    if not keyword:
        raise ValueError("Missing keyword")
    return keyword, pages

@bot.event
async def on_ready():
    print(f'Bot {bot.user} has connected successfully and is ready!')

@bot.command(name='search')
async def trigger_airflow(ctx, *, args: str = None):
    """
    Listens for command: !search -k <keyword> [-p <pages>]
    """
    if not args:
        await ctx.send('Syntax error. Please use: !search -k "Data Engineer" -p 2')
        return

    try:
        keyword, pages = parse_search_args(args)
    except ValueError as error:
        await ctx.send(f'Syntax error: {error}. Please use: !search -k "Data Engineer" -p 2')
        return

    await ctx.send(f"Transmitting command to Airflow to search for keyword: {keyword}, pages: {pages}...")

    payload = {
        "conf": {
            "keyword": keyword,
            "pages": pages
        }
    }
    
    # Use aiohttp for asynchronous, non-blocking HTTP requests
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": aiohttp.encode_basic_auth(AIRFLOW_USER, AIRFLOW_PASS),
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                AIRFLOW_API_URL,
                json=payload,
                headers=headers,
            ) as response:
                
                response.raise_for_status()
                await ctx.send(f"Success! Airflow received keyword '{keyword}' with {pages} page(s) and started the Data Pipeline.")
                
    except aiohttp.ClientError as e:
        print(f"API Error: {e}")
        await ctx.send("System Error: Cannot connect to Airflow server.")

if __name__ == "__main__":
    bot.run(TOKEN)
