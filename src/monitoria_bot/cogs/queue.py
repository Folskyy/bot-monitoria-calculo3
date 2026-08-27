"""Cog para gerenciamento da fila FIFO de atendimento síncrono da monitoria."""

from __future__ import annotations

import html
import logging
import discord
from discord import app_commands
from discord.ext import commands

from monitoria_bot.checks import can_access_student_feature, is_admin, is_guild_interaction, is_monitor_or_admin
from monitoria_bot.config import Config
from monitoria_bot.database import Database

logger = logging.getLogger(__name__)


class QueueCog(commands.GroupCog, name="fila"):
    """Comandos para entrada, saída e atendimento na fila da monitoria."""

    def __init__(self, bot: commands.Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config
        super().__init__()

    @app_commands.command(
        name="entrar",
        description="Entra na fila de atendimento individual da monitoria.",
    )
    @app_commands.describe(assunto="Tema ou exercício que você deseja sanar com o monitor.")
    async def entrar(self, interaction: discord.Interaction, assunto: str) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await self.db.get_guild_settings(guild_id)
        student = await self.db.get_student(guild_id, user_id)

        can_access, access_err = can_access_student_feature(interaction, student, settings)
        if not can_access:
            await interaction.response.send_message(f"❌ {access_err}", ephemeral=True)
            return

        try:
            entry = await self.db.enqueue(guild_id, user_id, assunto.strip())
            waiting_list = await self.db.list_queue(guild_id)
            position = next((idx + 1 for idx, e in enumerate(waiting_list) if e.id == entry.id), len(waiting_list))

            await interaction.response.send_message(
                f"✅ Você entrou na fila de atendimento com sucesso!\n"
                f"• **Posição:** {position}º\n"
                f"• **Assunto:** {discord.utils.escape_markdown(assunto.strip())}\n\n"
                "Fique atento às notificações no canal da fila quando for chamado pelo monitor.",
                ephemeral=True,
            )
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)

    @app_commands.command(
        name="sair",
        description="Sai da fila de atendimento caso você não precise mais de ajuda no momento.",
    )
    async def sair(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        removed = await self.db.leave_queue(guild_id, user_id)
        if removed:
            await interaction.response.send_message("✅ Você saiu da fila de atendimento.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "ℹ️ Você não possui uma entrada em espera na fila no momento.",
                ephemeral=True,
            )

    @app_commands.command(
        name="listar",
        description="Exibe a situação atual da fila de monitoria e quem está em atendimento.",
    )
    async def listar(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)

        active_serving = await self.db.get_active_serving(guild_id)
        waiting_entries = await self.db.list_queue(guild_id)

        embed = discord.Embed(
            title="👥 Fila de Atendimento — Monitoria de Cálculo 3",
            color=discord.Color.teal(),
        )

        if active_serving:
            called_by_mention = f"<@{active_serving.called_by_user_id}>" if active_serving.called_by_user_id else "Monitor"
            safe_subj = discord.utils.escape_markdown(active_serving.subject)
            embed.add_field(
                name="🟢 Em Atendimento Agora",
                value=(
                    f"• **Aluno:** <@{active_serving.user_id}>\n"
                    f"• **Atendido por:** {called_by_mention}\n"
                    f"• **Assunto:** {safe_subj}"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="🟢 Em Atendimento Agora",
                value="Nenhum atendimento em andamento no momento.",
                inline=False,
            )

        if waiting_entries:
            lines = []
            for idx, entry in enumerate(waiting_entries, start=1):
                safe_subj = discord.utils.escape_markdown(entry.subject)
                lines.append(f"`{idx}º` <@{entry.user_id}> — {safe_subj}")
            embed.add_field(
                name=f"⏳ Aguardando Atendimento ({len(waiting_entries)})",
                value="\n".join(lines[:20]) + ("\n*... e mais*" if len(lines) > 20 else ""),
                inline=False,
            )
        else:
            embed.add_field(
                name="⏳ Aguardando Atendimento",
                value="A fila está vazia no momento.",
                inline=False,
            )

        embed.set_footer(text="A fila funciona em ordem FIFO (primeiro que chega, primeiro atendido).")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(
        name="proximo",
        description="Chama o próximo aluno da fila para atendimento (Apenas Monitores e Administradores).",
    )
    async def proximo(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        guild_id = str(interaction.guild.id)
        monitor_user_id = str(interaction.user.id)

        settings = await self.db.get_guild_settings(guild_id)
        if not is_monitor_or_admin(interaction, settings):
            await interaction.response.send_message(
                "❌ Permissão negada: Este comando é restrito a monitores e administradores.",
                ephemeral=True,
            )
            return

        entry, err = await self.db.call_next(guild_id, monitor_user_id)
        if err == "already_serving":
            await interaction.response.send_message(
                "⚠️ Já existe um atendimento em andamento. Conclua-o com `/fila encerrar` antes de chamar o próximo aluno.",
                ephemeral=True,
            )
            return

        if err == "queue_empty" or not entry:
            await interaction.response.send_message("ℹ️ A fila está vazia no momento.", ephemeral=True)
            return

        # Notifica no canal da fila com menção exclusiva ao aluno
        assert settings is not None
        queue_channel = interaction.guild.get_channel(int(settings.queue_channel_id))
        student_member = interaction.guild.get_member(int(entry.user_id))

        if isinstance(queue_channel, discord.TextChannel):
            safe_subject = discord.utils.escape_markdown(entry.subject)
            mention_target = student_member.mention if student_member else f"<@{entry.user_id}>"
            notification_text = (
                f"📢 {mention_target}, **é a sua vez!**\n"
                f"Seu atendimento foi iniciado por {interaction.user.mention}.\n"
                f"• **Assunto:** {safe_subject}"
            )
            try:
                allowed_users = [student_member] if student_member else []
                await queue_channel.send(
                    content=notification_text,
                    allowed_mentions=discord.AllowedMentions(users=allowed_users),
                )
            except Exception as e:
                logger.error("Falha ao enviar notificação de chamada no canal da fila: %s", e)

        await interaction.response.send_message(
            f"✅ Aluno <@{entry.user_id}> chamado com sucesso para atendimento!",
            ephemeral=True,
        )

    @app_commands.command(
        name="encerrar",
        description="Encerra o atendimento em andamento (Apenas Monitores e Administradores).",
    )
    async def encerrar(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)

        settings = await self.db.get_guild_settings(guild_id)
        if not is_monitor_or_admin(interaction, settings):
            await interaction.response.send_message(
                "❌ Permissão negada: Este comando é restrito a monitores e administradores.",
                ephemeral=True,
            )
            return

        finished = await self.db.finish_serving(guild_id)
        if not finished:
            await interaction.response.send_message(
                "ℹ️ Não há nenhum atendimento em andamento para ser encerrado.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Atendimento do aluno <@{finished.user_id}> encerrado com sucesso!",
            ephemeral=True,
        )

    @app_commands.command(
        name="limpar",
        description="Cancela todas as entradas pendentes da fila (Apenas Administradores).",
    )
    async def limpar(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        if not is_admin(interaction):
            await interaction.response.send_message(
                "❌ Somente administradores podem limpar a fila.",
                ephemeral=True,
            )
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)

        count = await self.db.clear_queue(guild_id)
        await interaction.response.send_message(
            f"🧹 A fila foi limpa. Foram canceladas {count} entradas.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    db: Database = getattr(bot, "db")
    config: Config = getattr(bot, "config")
    await bot.add_cog(QueueCog(bot, db, config))
