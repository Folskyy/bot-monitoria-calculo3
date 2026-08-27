"""Modais de cadastro e edição de dados de alunos."""

from __future__ import annotations

import logging
import sqlite3
import discord

from monitoria_bot.config import Config
from monitoria_bot.database import Database, GuildSettings, Student

logger = logging.getLogger(__name__)


class RegistrationModal(discord.ui.Modal, title="Cadastro - Monitoria de Cálculo 3"):
    """Modal para coleta segura e privada dos dados cadastrais do aluno."""

    full_name_input = discord.ui.TextInput(
        label="Nome Completo",
        placeholder="Ex: Ana Clara dos Santos",
        required=True,
        min_length=1,
        max_length=100,
    )

    ra_input = discord.ui.TextInput(
        label="RA (Registro Acadêmico)",
        placeholder="Ex: 0012345 (conforme fornecido pela instituição)",
        required=True,
        min_length=1,
        max_length=32,
    )

    class_name_input = discord.ui.TextInput(
        label="Turma (Opcional)",
        placeholder="Ex: Turma A, Noturno, etc.",
        required=False,
        max_length=80,
    )

    def __init__(self, db: Database, config: Config, settings: GuildSettings) -> None:
        super().__init__()
        self.db = db
        self.config = config
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "O cadastro só pode ser realizado diretamente em um servidor Discord.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        member = interaction.user
        guild_id = str(guild.id)
        user_id = str(member.id)

        full_name = self.full_name_input.value.strip()
        ra = self.ra_input.value.strip()
        class_name = self.class_name_input.value.strip() if self.class_name_input.value else None

        # Validação do formato do RA
        if not self.config.ra_regex.match(ra):
            await interaction.response.send_message(
                f"❌ Formato de RA inválido. O RA deve corresponder ao padrão configurado ({self.config.ra_regex_str}). "
                "Zeros à esquerda são aceitos e preservados.",
                ephemeral=True,
            )
            return

        # Verificação de duplicidade de RA por outro usuário
        existing_ra = await self.db.get_student_by_ra(guild_id, ra)
        if existing_ra and existing_ra.user_id != user_id:
            await interaction.response.send_message(
                "❌ Este RA já foi cadastrado por outro usuário neste servidor. "
                "Caso este seja o seu RA, favor entrar em contato privado com a monitoria para verificação.",
                ephemeral=True,
            )
            return

        # Gravação inicial com status pending_role
        try:
            await self.db.create_pending_student(
                guild_id=guild_id,
                user_id=user_id,
                full_name=full_name,
                ra=ra,
                class_name=class_name,
            )
        except sqlite3.IntegrityError:
            await interaction.response.send_message(
                "❌ Não foi possível salvar o cadastro devido a um conflito de dados. "
                "Favor entrar em contato privado com a monitoria.",
                ephemeral=True,
            )
            return

        # Tentativa de atribuição do cargo Aluno no Discord
        student_role = guild.get_role(int(self.settings.student_role_id))
        if not student_role:
            await interaction.response.send_message(
                "⚠️ Seus dados foram salvos com sucesso, mas o cargo de Aluno configurado não foi encontrado no servidor. "
                "Avisamos os monitores para verificar as configurações.",
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(student_role, reason="Cadastro de monitoria concluído")
            await self.db.activate_student(guild_id, user_id)
            await interaction.response.send_message(
                f"✅ Cadastro concluído com sucesso, **{full_name}**! "
                f"O cargo **{student_role.name}** foi atribuído e os canais de monitoria foram liberados para você.",
                ephemeral=True,
            )
        except (discord.Forbidden, discord.HTTPException) as err:
            logger.error("Falha ao atribuir cargo Aluno no Discord para usuário %s: %s", user_id, err)
            await interaction.response.send_message(
                "⚠️ Seus dados foram registrados com sucesso, porém o bot não conseguiu atribuir o cargo de Aluno "
                "devido a permissões ou hierarquia de cargos do Discord. "
                "Seu cadastro permanece salvo em estado pendente. Você pode tentar clicar no botão de cadastro "
                "novamente após o administrador ajustar as permissões.",
                ephemeral=True,
            )


class EditStudentModal(discord.ui.Modal, title="Editar Cadastro de Aluno"):
    """Modal administrativo/monitor para ajuste de dados de um aluno."""

    def __init__(self, db: Database, config: Config, target_member: discord.Member, current_student: Student) -> None:
        super().__init__()
        self.db = db
        self.config = config
        self.target_member = target_member
        self.current_student = current_student

        self.full_name_input = discord.ui.TextInput(
            label="Nome Completo",
            default=current_student.full_name,
            required=True,
            min_length=1,
            max_length=100,
        )
        self.add_item(self.full_name_input)

        self.ra_input = discord.ui.TextInput(
            label="RA (Registro Acadêmico)",
            default=current_student.ra,
            required=True,
            min_length=1,
            max_length=32,
        )
        self.add_item(self.ra_input)

        self.class_name_input = discord.ui.TextInput(
            label="Turma (Opcional)",
            default=current_student.class_name or "",
            required=False,
            max_length=80,
        )
        self.add_item(self.class_name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = str(self.target_member.guild.id)
        user_id = str(self.target_member.id)

        full_name = self.full_name_input.value.strip()
        ra = self.ra_input.value.strip()
        class_name = self.class_name_input.value.strip() if self.class_name_input.value else None

        if not self.config.ra_regex.match(ra):
            await interaction.response.send_message(
                f"❌ Formato de RA inválido. Deve seguir o padrão {self.config.ra_regex_str}.",
                ephemeral=True,
            )
            return

        # Verifica unicidade se o RA tiver sido alterado
        if ra != self.current_student.ra:
            existing_ra = await self.db.get_student_by_ra(guild_id, ra)
            if existing_ra and existing_ra.user_id != user_id:
                await interaction.response.send_message(
                    "❌ Este novo RA já está em uso por outro aluno neste servidor.",
                    ephemeral=True,
                )
                return

        try:
            await self.db.update_student_profile(guild_id, user_id, full_name, ra, class_name)
            await interaction.response.send_message(
                f"✅ Cadastro do aluno **{self.target_member.display_name}** atualizado com sucesso.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Erro ao atualizar cadastro do aluno %s: %s", user_id, e)
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao atualizar os dados no banco.",
                ephemeral=True,
            )
