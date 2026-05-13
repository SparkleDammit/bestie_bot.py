import discord
from discord import app_commands
import os

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.command(name="check", description="Trigger an anonymous comfort check")
@app_commands.describe(color="Optional: signal a specific light without a full check-in")
@app_commands.choices(color=[
    app_commands.Choice(name="yellow", value="yellow"),
    app_commands.Choice(name="red", value="red"),
])
async def check(interaction: discord.Interaction, color: app_commands.Choice[str] = None):
    await interaction.response.send_message(
        "Your comfort check has been sent.",
        ephemeral=True
    )

    if color is None:
        await interaction.channel.send(
            "**COMFORT CHECK IN**\n\n"
            "<:GO:1490423634366304428> **Good to go.** I'm present, I'm in, keep going.\n"
            "<:WAIT:1490423509812511084> **Please wait.** Something shifted. I'm not sure. Pause here. Check in. Pull back.\n"
            "<:STOP:1490423467500109994> **Please stop.** This ends now."
        )
    elif color.value == "yellow":
        await interaction.channel.send(
            "<:WAIT:1490423509812511084> **Please wait.** Something shifted. I'm not sure. Pause here. Check in. Pull back."
        )
    elif color.value == "red":
        await interaction.channel.send(
            "<:STOP:1490423467500109994> **Please stop.** This ends now."
        )

@client.event
async def on_ready():
    guild = discord.Object(id=1487446782219911241)
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    print(f"Logged in as {client.user}")

client.run(os.environ["DISCORD_TOKEN"])