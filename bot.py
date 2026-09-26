from __future__ import annotations
import logging
import discord
from discord.ext import commands
from discord import app_commands
from config import Config
from db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

class InventoryBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.db = Database(config.database_path)

    async def setup_hook(self):
        await self.db.connect()
        await self.load_extension("cogs.inventory_commands")
        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info("Synced commands to guild %s", self.config.guild_id)
        else:
            await self.tree.sync()
            logging.info("Synced global commands")

    async def close(self):
        await self.db.close()
        await super().close()

    async def on_ready(self):
        logging.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logging.exception("Application command error", exc_info=error)
        message = "Something went wrong while running that command. Check the bot console for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

def main():
    config = Config.from_env()
    bot = InventoryBot(config)
    bot.run(config.token)

if __name__ == "__main__":
    main()
