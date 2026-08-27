"""Cog de abertura, acompanhamento e resolução de dúvidas em threads."""

from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from monitoria_bot.checks import can_access_student_feature, is_guild_interaction, is_monitor_or_admin
from monitoria_bot.config import Config
from monitoria_bot.database import Database

logger = logging.getLogger(__name__)


class DoubtsCog(commands.GroupCog, name="duvida"):
    """Comandos para abertura e gestão de dúvidas de Cálculo 3."""

    def __init__(self, bot: commands.Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config
        super().__init__()

    @app_commands.command(
        name="criar",
        description="Abre uma nova dúvida e cria uma thread pública de discussão no canal de dúvidas.",
    )
    @app_commands.describe(
        assunto="Tópico da matéria (Ex: Derivadas Parciais, Integrais Duplas, Teorema de Green)",
        titulo="Resumo claro do problema ou questão",
        descricao="Enunciado, o que você já tentou e o ponto exato da sua dúvida",
        imagem="Foto ou anexo do enunciado/tentativa (opcional)",
    )
    async def criar(
        self,
        interaction: discord.Interaction,
        assunto: str,
        titulo: str,
        descricao: str,
        imagem: discord.Attachment | None = None,
    ) -> None:
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

        assert settings is not None
        channel = interaction.guild.get_channel(int(settings.doubts_channel_id))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ O canal de dúvidas configurado não foi encontrado ou não é um canal de texto.",
                ephemeral=True,
            )
            return

        # Defer ephemeral para permitir envio de mensagem e criação de thread
        await interaction.response.defer(ephemeral=True)

        interaction_id = str(interaction.id)
        doubt = await self.db.create_doubt_started(
            guild_id=guild_id,
            author_user_id=user_id,
            interaction_id=interaction_id,
            subject=assunto.strip(),
            title=titulo.strip(),
            description=descricao.strip(),
            channel_id=str(channel.id),
        )

        embed = discord.Embed(
            title=f"Dúvida #{doubt.id}: {titulo.strip()}",
            description=descricao.strip(),
            color=discord.Color.gold(),
        )
        embed.add_field(name="Assunto", value=assunto.strip(), inline=True)
        embed.add_field(name="Autor", value=interaction.user.mention, inline=True)
        embed.add_field(name="Status", value="🟡 Aberta", inline=True)

        if imagem:
            # Reutiliza a URL da imagem do anexo do Discord sem download local
            embed.set_image(url=imagem.url)

        embed.set_footer(text="Thread pública visível aos colegas da turma. Use /duvida resolver para encerrar.")

        try:
            msg = await channel.send(
                content=f"📢 Nova dúvida postada por {interaction.user.mention}!",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            )
            thread_title = f"Dúvida #{doubt.id}: {titulo.strip()}"[:100]
            thread = await msg.create_thread(
                name=thread_title,
                auto_archive_duration=1440,
                reason=f"Discussão da dúvida #{doubt.id}",
            )

            await self.db.complete_doubt_creation(
                guild_id=guild_id,
                doubt_id=doubt.id,
                message_id=str(msg.id),
                thread_id=str(thread.id),
            )

            await interaction.followup.send(
                f"✅ Sua dúvida foi criada com sucesso na thread {thread.mention}!\n"
                f"Acesse o canal {channel.mention} para participar da discussão.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Erro ao criar mensagem/thread para a dúvida %s: %s", doubt.id, e)
            await self.db.fail_doubt_creation(guild_id, doubt.id)
            await interaction.followup.send(
                "❌ Ocorreu um erro ao criar a thread no canal de dúvidas. "
                "Verifique se o bot possui permissão para criar threads públicas no canal.",
                ephemeral=True,
            )

    @app_commands.command(
        name="minhas",
        description="Lista as dúvidas criadas por você na monitoria.",
    )
    async def minhas(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        doubts = await self.db.list_user_doubts(guild_id, user_id, limit=10)
        if not doubts:
            await interaction.response.send_message(
                "ℹ️ Você ainda não registrou nenhuma dúvida neste servidor.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 Suas Dúvidas Registradas",
            description="Exibindo as 10 dúvidas mais recentes:",
            color=discord.Color.blue(),
        )

        for d in doubts:
            status_icon = "🟢 Resolvida" if d.status == "resolved" else ("🟡 Aberta" if d.status == "open" else f"⚪ {d.status}")
            link = f"https://discord.com/channels/{guild_id}/{d.thread_id}" if d.thread_id else "Sem thread"
            embed.add_field(
                name=f"#{d.id} — {d.title} ({status_icon})",
                value=f"• **Assunto:** {d.subject}\n• **Thread:** {link}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="resolver",
        description="Marca uma dúvida como resolvida (Autor, Monitor ou Administrador).",
    )
    @app_commands.describe(id="Identificador numérico da dúvida (Ex: 1)")
    async def resolver(self, interaction: discord.Interaction, id: int) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        doubt = await self.db.get_doubt(guild_id, id)
        if not doubt:
            await interaction.response.send_message(
                f"❌ Dúvida #{id} não encontrada neste servidor.",
                ephemeral=True,
            )
            return

        settings = await self.db.get_guild_settings(guild_id)
        is_author = doubt.author_user_id == user_id
        is_staff = is_monitor_or_admin(interaction, settings)

        if not (is_author or is_staff):
            await interaction.response.send_message(
                "❌ Permissão negada: Somente o autor da dúvida, um monitor ou um administrador podem marcá-la como resolvida.",
                ephemeral=True,
            )
            return

        if doubt.status == "resolved":
            await interaction.response.send_message(
                f"ℹ️ A dúvida #{id} já estava marcada como resolvida.",
                ephemeral=True,
            )
            return

        resolved = await self.db.resolve_doubt(guild_id, id, user_id)
        assert resolved is not None

        # Tenta enviar mensagem na thread e arquivá-la
        if doubt.thread_id:
            try:
                thread = interaction.guild.get_thread(int(doubt.thread_id))
                if not thread:
                    thread = await interaction.guild.fetch_channel(int(doubt.thread_id))

                if isinstance(thread, discord.Thread):
                    await thread.send(
                        f"✅ Esta dúvida foi marcada como **resolvida** por {interaction.user.mention}."
                    )
                    try:
                        await thread.edit(archived=True, locked=False, reason="Dúvida resolvida")
                    except Exception as e:
                        logger.debug("Não foi possível arquivar a thread %s: %s", doubt.thread_id, e)
            except Exception as e:
                logger.warning("Falha ao atualizar thread no Discord para dúvida %s: %s", id, e)

        await interaction.response.send_message(
            f"✅ A dúvida #{id} (**{doubt.title}**) foi marcada como resolvida com sucesso!",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    db: Database = getattr(bot, "db")
    config: Config = getattr(bot, "config")
    await bot.add_cog(DoubtsCog(bot, db, config))
