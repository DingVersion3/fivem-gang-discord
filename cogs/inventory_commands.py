from __future__ import annotations
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from inventory import (
    InventoryError,
    validate_category,
    validate_name,
    validate_price,
    validate_quantity,
)

# Slash-command argument types (Discord enforces these ranges client-side)
PriceArg = app_commands.Range[float, 0, 1_000_000_000]
QtyArg = app_commands.Range[int, 1, 1_000_000]
ReasonArg = app_commands.Range[str, 1, 200]
LimitArg = app_commands.Range[int, 1, 25]


def money(value: float) -> str:
    return f"${value:,.2f}"


def stamp(iso: str) -> str:
    return discord.utils.format_dt(datetime.fromisoformat(iso), "f")


def clip(text: str, limit: int = 4000) -> str:
    # Embed descriptions max out at 4096 characters
    if len(text) <= limit:
        return text
    return text[: limit - 10].rsplit("\n", 1)[0] + "\n…"


def is_king():
    # Passes only if the member has the role named by KING_ROLE_NAME
    async def predicate(interaction: discord.Interaction) -> bool:
        role_name = interaction.client.config.king_role_name
        user = interaction.user
        if isinstance(user, discord.Member) and any(
            r.name.lower() == role_name.lower() for r in user.roles
        ):
            return True
        raise app_commands.CheckFailure(f"You need the {role_name} role to use this command.")

    return app_commands.check(predicate)


class InventoryCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- error handling ----------

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(error, app_commands.CheckFailure):
            message = str(error) or "You can't use that command."
        elif isinstance(original, (InventoryError, ValueError)):
            message = str(original)
        elif isinstance(original, sqlite3.IntegrityError):
            message = "Couldn't save that. An item with that name may already exist."
        else:
            name = interaction.command.name if interaction.command else "?"
            logging.exception("Unhandled error in /%s", name, exc_info=error)
            message = "Something went wrong while running that command. Check the bot console for details."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    # ---------- helpers ----------

    async def _require_item(self, name: str):
        item = await self.bot.db.get_item(validate_name(name, "Item"))
        if item is None:
            raise InventoryError(f"Item '{name.strip()}' not found.")
        return item

    async def _move_stock(
        self,
        interaction: discord.Interaction,
        item_name: str,
        quantity: int,
        action: str,
        sign: int,
        unit_price: Optional[float],
        price_field: Optional[str],
        reason: Optional[str],
        title: str,
    ):
        item = await self._require_item(item_name)
        qty = validate_quantity(quantity)
        if unit_price is None:
            unit_price = item[price_field] if price_field else 0.0
        price = validate_price(unit_price)
        reason = reason.strip() if reason else None

        updated = await self.bot.db.change_stock(
            item["name"],
            sign * qty,
            action,
            price,
            reason,
            interaction.user.id,
            interaction.user.display_name,
        )

        embed = discord.Embed(title=f"{title}: {updated['name']}", color=discord.Color.blurple())
        embed.add_field(name="Quantity", value=f"{qty:,}")
        if price_field:
            embed.add_field(name="Unit price", value=money(price))
            embed.add_field(name="Total", value=money(price * qty))
        embed.add_field(name="In stock now", value=f"{updated['quantity']:,}")
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    # ---------- King-only commands ----------

    @app_commands.command(name="additem", description="Create a new inventory item (King only)")
    @app_commands.describe(
        name="Item name",
        category="Category (e.g. Weapons, Drugs, Materials)",
        buy_price="Price you pay per unit",
        sell_price="Price you sell for per unit",
    )
    @is_king()
    async def additem(
        self,
        interaction: discord.Interaction,
        name: str,
        category: str,
        buy_price: PriceArg,
        sell_price: PriceArg,
    ):
        item = await self.bot.db.create_item(
            validate_name(name),
            validate_category(category),
            validate_price(buy_price),
            validate_price(sell_price),
        )
        embed = discord.Embed(title=f"Item created: {item['name']}", color=discord.Color.green())
        embed.add_field(name="Category", value=item["category"])
        embed.add_field(name="Buy price", value=money(item["buy_price"]))
        embed.add_field(name="Sell price", value=money(item["sell_price"]))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="edititem", description="Edit an item's details (King only)")
    @app_commands.describe(
        item="Item to edit",
        new_name="New name",
        category="New category",
        buy_price="New buy price",
        sell_price="New sell price",
    )
    @is_king()
    async def edititem(
        self,
        interaction: discord.Interaction,
        item: str,
        new_name: Optional[str] = None,
        category: Optional[str] = None,
        buy_price: Optional[PriceArg] = None,
        sell_price: Optional[PriceArg] = None,
    ):
        if all(v is None for v in (new_name, category, buy_price, sell_price)):
            raise InventoryError("Nothing to change. Provide at least one field to edit.")

        current = await self._require_item(item)
        updated = await self.bot.db.update_item(
            current["name"],
            validate_name(new_name) if new_name is not None else current["name"],
            validate_category(category) if category is not None else current["category"],
            validate_price(buy_price) if buy_price is not None else current["buy_price"],
            validate_price(sell_price) if sell_price is not None else current["sell_price"],
        )
        embed = discord.Embed(title=f"Item updated: {updated['name']}", color=discord.Color.orange())
        embed.add_field(name="Category", value=updated["category"])
        embed.add_field(name="Buy price", value=money(updated["buy_price"]))
        embed.add_field(name="Sell price", value=money(updated["sell_price"]))
        embed.add_field(name="In stock", value=f"{updated['quantity']:,}")
        await interaction.response.send_message(embed=embed)

    # ---------- stock commands ----------

    @app_commands.command(name="addstock", description="Add stock to an item")
    @app_commands.describe(item="Item", quantity="How many to add", reason="Why (optional)")
    async def addstock(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: QtyArg,
        reason: Optional[ReasonArg] = None,
    ):
        await self._move_stock(interaction, item, quantity, "add", 1, None, None, reason, "Stock added")

    @app_commands.command(name="purchase", description="Record a purchase and add the stock")
    @app_commands.describe(
        item="Item",
        quantity="How many were bought",
        unit_price="Price paid per unit (defaults to the item's buy price)",
        reason="Note (optional)",
    )
    async def purchase(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: QtyArg,
        unit_price: Optional[PriceArg] = None,
        reason: Optional[ReasonArg] = None,
    ):
        await self._move_stock(interaction, item, quantity, "purchase", 1, unit_price, "buy_price", reason, "Purchased")

    @app_commands.command(name="sell", description="Record a sale and remove the stock")
    @app_commands.describe(
        item="Item",
        quantity="How many were sold",
        unit_price="Price per unit (defaults to the item's sell price)",
        reason="Note (optional)",
    )
    async def sell(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: QtyArg,
        unit_price: Optional[PriceArg] = None,
        reason: Optional[ReasonArg] = None,
    ):
        await self._move_stock(interaction, item, quantity, "sell", -1, unit_price, "sell_price", reason, "Sold")

    @app_commands.command(name="remove", description="Remove stock for another reason (lost, used, etc.)")
    @app_commands.describe(item="Item", quantity="How many to remove", reason="Why (optional)")
    async def remove(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: QtyArg,
        reason: Optional[ReasonArg] = None,
    ):
        await self._move_stock(interaction, item, quantity, "remove", -1, None, None, reason, "Stock removed")

    # ---------- read-only commands ----------

    @app_commands.command(name="inventory", description="View current stock")
    @app_commands.describe(category="Only show this category (optional)")
    async def inventory(self, interaction: discord.Interaction, category: Optional[str] = None):
        rows = await self.bot.db.list_items(category.strip() if category else None)
        if not rows:
            await interaction.response.send_message("No items found.", ephemeral=True)
            return

        lines = []
        current = None
        for r in rows:
            if r["category"] != current:
                current = r["category"]
                lines.append(f"\n**{current}**")
            lines.append(
                f"{r['name']} — **{r['quantity']:,}** in stock "
                f"(buy {money(r['buy_price'])}, sell {money(r['sell_price'])})"
            )

        embed = discord.Embed(
            title="Inventory",
            description=clip("\n".join(lines).strip()),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="history", description="View recent transactions")
    @app_commands.describe(item="Only show this item (optional)", limit="How many to show (default 10)")
    async def history(
        self,
        interaction: discord.Interaction,
        item: Optional[str] = None,
        limit: LimitArg = 10,
    ):
        rows = await self.bot.db.history(item.strip() if item else None, limit)
        if not rows:
            await interaction.response.send_message("No transactions found.", ephemeral=True)
            return

        lines = []
        for r in rows:
            line = (
                f"{stamp(r['created_at'])} — **{r['action']}** {r['quantity']:,} × {r['item_name']} "
                f"@ {money(r['unit_price'])} by {r['actor_name']}"
            )
            if r["reason"]:
                line += f" — {r['reason']}"
            lines.append(line)

        embed = discord.Embed(
            title="Recent transactions",
            description=clip("\n".join(lines)),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats", description="View inventory totals")
    async def stats(self, interaction: discord.Interaction):
        s = await self.bot.db.stats()
        embed = discord.Embed(title="Inventory stats", color=discord.Color.blurple())
        embed.add_field(name="Items", value=f"{s['item_count']:,}")
        embed.add_field(name="Total units", value=f"{s['units']:,}")
        embed.add_field(name="Stock cost value", value=money(s["cost_value"]))
        embed.add_field(name="Stock retail value", value=money(s["retail_value"]))
        await interaction.response.send_message(embed=embed)

    # ---------- autocomplete ----------

    @addstock.autocomplete("item")
    @purchase.autocomplete("item")
    @sell.autocomplete("item")
    @remove.autocomplete("item")
    @edititem.autocomplete("item")
    @history.autocomplete("item")
    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        names = await self.bot.db.search_item_names(current.strip())
        return [app_commands.Choice(name=n, value=n) for n in names]

    @additem.autocomplete("category")
    @edititem.autocomplete("category")
    @inventory.autocomplete("category")
    async def category_autocomplete(self, interaction: discord.Interaction, current: str):
        cats = await self.bot.db.categories(current.strip())
        return [app_commands.Choice(name=c, value=c) for c in cats]


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCommands(bot))