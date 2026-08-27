"""Classe principal do bot com gerenciamento do ciclo de vida e registro de views."""

from __future__ import annotations

import logging
import discord
from discord.ext import commands

from monitoria_bot.config import Config
from monitoria_bot.database import Database
from monitoria_bot.views.persistent import RegistrationView

logger = logging.getLogger(__name__)

INITIAL_EXTENSIONS = [
    "monitoria_bot.cogs.admin",
    "monitoria_bot.cogs.registration",
    "monitoria_bot.cogs.office_hours",
    "monitoria_bot.cogs.doubts",
    "monitoria_bot.cogs.queue",
    "monitoria_bot.cogs.materials",
]


class MonitoriaBot(commands.Bot):
    """Bot de monitoria de Cálculo 3 no Discord."""

    def __init__(self, config: Config, db: Database) -> None:
        intents = discord.Intents.default()
        # Message Content Intent explicitamente desabilitado por não ser necessário no MVP
        intents.message_content = False

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.config = config
        self.db = db

    async def setup_hook(self) -> None:
        """Inicializa o banco, registra views persistentes e carrega as extensões."""
        logger.info("Inicializando persistência no SQLite...")
        await self.db.init_db()

        # Registro da View persistente com timeout=None e custom_id estável
        logger.info("Registrando view persistente de cadastro...")
        self.add_view(RegistrationView(self.db, self.config))

        # Carregamento de cogs
        for ext in INITIAL_EXTENSIONS:
            logger.info("Carregando extensão: %s", ext)
            await self.load_extension(ext)

        # Sincronização de slash commands
        if self.config.discord_guild_id:
            guild_obj = discord.Object(id=self.config.discord_guild_id)
            logger.info("Sincronizando slash commands para o servidor de desenvolvimento: %s", self.config.discord_guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        else:
            logger.info("Sincronizando slash commands globalmente...")
            await self.tree.sync()

    async def on_ready(self) -> None:
        """Notificação de conexão sem ressincronizar comandos a cada reconexão."""
        logger.info("Bot conectado com sucesso como %s (ID: %s)", self.user, self.user.id if self.user else "N/A")

    async def close(self) -> None:
        """Encerramento gracioso fechando recursos do banco."""
        logger.info("Encerrando bot e liberando conexão com o SQLite...")
        await self.db.close()
        await super().close()
