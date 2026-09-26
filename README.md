# Discord Inventory Bot

A Python `discord.py` slash-command inventory bot with persistent SQLite storage.

## Commands

- `/additem` — King role only; create an item.
- `/edititem` — King role only; edit item details.
- `/addstock` — add stock.
- `/purchase` — add purchased stock and record the purchase.
- `/sell` — remove sold stock and record the sale.
- `/remove` — remove stock for another reason.
- `/inventory` — view current stock.
- `/history` — view recent transactions.
- `/stats` — view totals.

Stock can never become negative. Transactions record the actor, quantity, unit price, reason, and UTC timestamp.

## Windows setup

1. Install Python 3.11+.
2. Open this project folder in Command Prompt or PowerShell.
3. Run `py -m pip install -r requirements.txt`.
4. Copy `.env.example` to `.env`.
5. Put your Discord bot token in `.env`.
6. Optional: put your server ID in `GUILD_ID`. Using a guild ID makes slash-command syncing immediate for that server; otherwise commands sync globally.
7. Make sure the bot is invited with the `bot` and `applications.commands` scopes.
8. Give the bot permission to send messages and embeds in the channels where it will be used.
9. Make sure the server has a role named `King`, or change `KING_ROLE_NAME` in `.env`.
10. Run `py bot.py`.

The database is automatically created at `data/inventory.db`.
