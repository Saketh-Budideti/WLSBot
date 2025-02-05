import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from helper import get_sheet_data, parse_transactions, get_target_sheet_gid, sheet_to_img
import io

load_dotenv()
discord_token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='$', intents=intents)

@bot.event
async def on_ready():
    print("Logged in as {0.user}".format(bot))

@bot.command()
async def ledger_text(ctx, *args):
    """
    Command to fetch ledger data from a specific sheet tab and send it as text.
    Usage: !ledger_text {page name in sheet}
    """
    try:
        sheet_name = ' '.join(args)

        # Retrieve the sheet data from Google Sheets
        df, disc = get_sheet_data(sheet_name)
        # output_text = parse_transactions(df, venmo)

        await ctx.send(''.join(disc[0]))
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command()
async def ledger_img(ctx, *args):
    """
    Command to fetch ledger data from a specific sheet tab and generate an image.
    Usage: !ledger_img {page name in sheet}
    """
    try:
        sheet_name = ' '.join(args)

        # Retrieve sheet GID and export the page as a PDF
        sheet_gid = get_target_sheet_gid(sheet_name)
        img_bytes = sheet_to_img(get_target_sheet_gid(sheet_name))

        # Send the generated image
        img_file = discord.File(io.BytesIO(img_bytes), filename="ledger.png")
        await ctx.send(file=img_file)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
@bot.command()
async def ledger(ctx, *args):
    """
    Command to fetch ledger data from a specific sheet tab and generate an image.
    Usage: !ledger {page name in sheet}
    """
    try:
        sheet_name = ' '.join(args)

        # Retrieve the sheet data from Google Sheets
        df, disc = get_sheet_data(sheet_name)
        output_text = ''.join(disc[0])

        # Retrieve sheet GID and export the page as a PDF
        img_bytes = sheet_to_img(get_target_sheet_gid(sheet_name))

        # Send the generated image
        img_file = discord.File(io.BytesIO(img_bytes), filename="ledger.png")

        await ctx.send(file=img_file)

        # Send the message with user pings
        await ctx.send(output_text)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

# it is used for the cooldown to prevent the bot from spam attack
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send("**Try after {0} second ".format(round(error.retry_after, 2)))

@bot.command()
@commands.cooldown(1, 10,
                   commands.BucketType.channel)  # it is used for the cooldown to prevent the bot from spam attack
async def ping(ctx):
    await ctx.send('Ping! **{0}**ms'.format(round(bot.latency, 1)))

bot.run(discord_token)
