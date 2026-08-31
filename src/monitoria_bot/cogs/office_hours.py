"""Cog para consulta e configuração dos horários de atendimento da monitoria."""

from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from monitoria_bot.checks import is_guild_interaction, is_monitor_or_admin
from monitoria_bot.config import Config
from monitoria_bot.database import Database

logger = logging.getLogger(__name__)


class OfficeHoursModal(discord.ui.Modal, title="Horários da Monitoria"):
    """Modal interativo de texto multi-linha para definir horários de monitoria."""

    texto = discord.ui.TextInput(
        label="Texto dos Horários",
        style=discord.TextStyle.paragraph,
        placeholder="Cole ou digite os horários aqui (aceita quebras de linha e Markdown)...",
        required=True,
        max_length=2000,
    )

    def __init__(self, db: Database, guild_id: str, default_value: str = "") -> None:
        super().__init__()
        self.db = db
        self.guild_id = guild_id
        if default_value:
            self.texto.default = default_value

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.db.update_office_hours_text(self.guild_id, self.texto.value.strip())
        await interaction.response.send_message(
            "✅ Horários de monitoria atualizados com sucesso!",
            ephemeral=True,
        )


class OfficeHoursCog(commands.Cog, name="Horários"):
    """Comandos para consulta e atualização dos horários de atendimento."""

    def __init__(self, bot: commands.Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config

    @app_commands.command(
        name="horarios",
        description="Exibe os dias, horários e canais de atendimento da monitoria de Cálculo 3.",
    )
    async def horarios(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        settings = await self.db.get_guild_settings(guild_id)

        hours_text = settings.office_hours_text if settings else "Horários ainda não informados pelo professor/monitor."
        tz_str = settings.timezone if settings else "America/Sao_Paulo"

        embed = discord.Embed(
            title="⏰ Horários da Monitoria de Cálculo 3",
            description=hours_text,
            color=discord.Color.teal(),
        )
        embed.set_footer(text=f"Fuso horário de referência: {tz_str}")

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(
        name="horarios-definir",
        description="Atualiza o texto dos horários de atendimento (Apenas Monitores e Administradores).",
    )
    @app_commands.describe(texto="Texto dos horários (opcional; se omitido, abre formulário). Use \\n para quebra de linha.")
    async def horarios_definir(self, interaction: discord.Interaction, texto: str | None = None) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        settings = await self.db.get_guild_settings(guild_id)

        if not is_monitor_or_admin(interaction, settings):
            await interaction.response.send_message(
                "❌ Permissão negada: Somente monitores e administradores podem alterar os horários.",
                ephemeral=True,
            )
            return

        if texto is None or not texto.strip():
            default_val = settings.office_hours_text if settings else ""
            modal = OfficeHoursModal(self.db, guild_id, default_value=default_val)
            await interaction.response.send_modal(modal)
            return

        formatted_text = texto.replace(r"\n", "\n").strip()
        await self.db.update_office_hours_text(guild_id, formatted_text)
        await interaction.response.send_message(
            "✅ Horários de monitoria atualizados com sucesso!",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    db: Database = getattr(bot, "db")
    config: Config = getattr(bot, "config")
    await bot.add_cog(OfficeHoursCog(bot, db, config))
