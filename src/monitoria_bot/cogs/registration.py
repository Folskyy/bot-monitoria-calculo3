"""Cog de gerenciamento cadastral de alunos e visualização de perfil."""

from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from monitoria_bot.checks import is_guild_interaction, is_monitor_or_admin
from monitoria_bot.config import Config
from monitoria_bot.database import Database
from monitoria_bot.views.modals import EditStudentModal, RegistrationModal

logger = logging.getLogger(__name__)


class RegistrationCog(commands.Cog, name="Cadastro"):
    """Comandos para cadastro de alunos, consulta de perfil e edição de registros."""

    def __init__(self, bot: commands.Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config

    @app_commands.command(
        name="cadastro",
        description="Abre o formulário para realização do cadastro de aluno da monitoria.",
    )
    async def cadastro(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message(
                "Este comando só pode ser executado dentro de um servidor Discord.",
                ephemeral=True,
            )
            return

        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await self.db.get_guild_settings(guild_id)
        if not settings:
            await interaction.response.send_message(
                "❌ O bot ainda não foi configurado pelo administrador (`/configurar`).",
                ephemeral=True,
            )
            return

        student = await self.db.get_student(guild_id, user_id)
        if not student:
            modal = RegistrationModal(self.db, self.config, settings)
            await interaction.response.send_modal(modal)
            return

        student_role = interaction.guild.get_role(int(settings.student_role_id))

        if student.status == "active":
            has_role = any(str(r.id) == settings.student_role_id for r in interaction.user.roles)
            if not has_role and student_role:
                try:
                    await interaction.user.add_roles(student_role, reason="Restaurando cargo Aluno de cadastro ativo")
                    await interaction.response.send_message(
                        f"✅ Seu cadastro já estava ativo (RA: **{student.ra}**). "
                        f"O cargo **{student_role.name}** foi restaurado com sucesso!",
                        ephemeral=True,
                    )
                except Exception as e:
                    logger.error("Erro ao restaurar cargo para %s: %s", user_id, e)
                    await interaction.response.send_message(
                        "⚠️ Seu cadastro está ativo, mas ocorreu erro ao restaurar o cargo. Avise um monitor.",
                        ephemeral=True,
                    )
            else:
                await interaction.response.send_message(
                    f"ℹ️ Você já possui um cadastro ativo neste servidor (RA: **{student.ra}**).\n"
                    "Use `/meu-cadastro` para conferir seus dados ou contate um monitor para alterações.",
                    ephemeral=True,
                )
            return

        if student.status == "pending_role":
            if not student_role:
                await interaction.response.send_message(
                    "⚠️ Cargo de Aluno não encontrado no servidor. Favor avisar a monitoria.",
                    ephemeral=True,
                )
                return

            try:
                await interaction.user.add_roles(student_role, reason="Ativando cargo Aluno de cadastro pendente")
                await self.db.activate_student(guild_id, user_id)
                await interaction.response.send_message(
                    f"✅ Cadastro ativado com sucesso, **{student.full_name}**! "
                    f"O cargo **{student_role.name}** foi atribuído.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error("Erro ao ativar cadastro pendente para %s: %s", user_id, e)
                await interaction.response.send_message(
                    "⚠️ Ainda não foi possível atribuir o cargo no Discord. Avise a equipe de monitoria.",
                    ephemeral=True,
                )

    @app_commands.command(
        name="meu-cadastro",
        description="Exibe seus dados cadastrais de forma privada e segura.",
    )
    async def meu_cadastro(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        student = await self.db.get_student(guild_id, user_id)
        if not student:
            await interaction.response.send_message(
                "❌ Você ainda não possui cadastro neste servidor. Utilize `/cadastro` ou o botão no canal de entrada.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="👤 Seus Dados Cadastrais",
            description="Estes dados são visíveis apenas para você e para a equipe de monitoria/professores.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Nome Completo", value=student.full_name, inline=False)
        embed.add_field(name="RA (Registro Acadêmico)", value=f"`{student.ra}`", inline=True)
        embed.add_field(name="Turma", value=student.class_name or "Não informada", inline=True)
        embed.add_field(
            name="Status",
            value="🟢 Ativo" if student.status == "active" else "🟡 Pendente de Cargo",
            inline=True,
        )
        embed.set_footer(text="Para solicitar correções ou exclusão, entre em contato privado com um monitor.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="aluno-editar",
        description="Abre um modal privado para editar os dados de um aluno (Apenas Monitores e Administradores).",
    )
    @app_commands.describe(aluno="Membro do servidor cujo cadastro será editado.")
    async def aluno_editar(self, interaction: discord.Interaction, aluno: discord.Member) -> None:
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

        student = await self.db.get_student(guild_id, str(aluno.id))
        if not student:
            await interaction.response.send_message(
                f"❌ O membro {aluno.mention} não possui cadastro registrado no banco de dados.",
                ephemeral=True,
            )
            return

        modal = EditStudentModal(self.db, self.config, aluno, student)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="ajuda",
        description="Apresenta os comandos disponíveis e orientações de uso da monitoria de Cálculo 3.",
    )
    async def ajuda(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="📚 Central de Ajuda — Monitoria de Cálculo 3",
            description="Comandos disponíveis para alunos, monitores e administradores:",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="🎓 Comandos para Alunos",
            value=(
                "• `/cadastro` — Realiza o cadastro de aluno e libera acesso aos canais.\n"
                "• `/meu-cadastro` — Consulta seus dados cadastrais de forma privada.\n"
                "• `/horarios` — Consulta os dias, horários e canais de atendimento.\n"
                "• `/duvida criar` — Abre uma nova dúvida e cria uma thread no canal de dúvidas.\n"
                "• `/duvida minhas` — Lista suas dúvidas e links das threads.\n"
                "• `/duvida resolver` — Marca sua dúvida como resolvida.\n"
                "• `/fila entrar` — Entra na fila de atendimento síncrono.\n"
                "• `/fila sair` — Sai da fila de atendimento.\n"
                "• `/fila listar` — Consulta a ordem da fila e quem está em atendimento.\n"
                "• `/material buscar` — Pesquisa materiais de estudo por termo ou tag."
            ),
            inline=False,
        )

        embed.add_field(
            name="🛡️ Comandos para Monitores e Administradores",
            value=(
                "• `/fila proximo` — Chama o próximo aluno da fila para atendimento.\n"
                "• `/fila encerrar` — Finaliza o atendimento atual.\n"
                "• `/fila limpar` — Limpa pendências da fila.\n"
                "• `/material adicionar` — Cadastra novo link de material de estudo.\n"
                "• `/material remover` — Remove um link de material pelo ID.\n"
                "• `/aluno-editar` — Corrige privadamente o cadastro de um aluno.\n"
                "• `/horarios definir` — Atualiza o texto dos horários de atendimento."
            ),
            inline=False,
        )

        embed.add_field(
            name="⚙️ Comandos Exclusivos de Administrador",
            value=(
                "• `/configurar` — Define os canais e cargos da monitoria.\n"
                "• `/boas-vindas` — Publica/atualiza a mensagem fixa com botão no canal de entrada."
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    db: Database = getattr(bot, "db")
    config: Config = getattr(bot, "config")
    await bot.add_cog(RegistrationCog(bot, db, config))
