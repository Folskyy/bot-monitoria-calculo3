"""Views persistentes com timeout=None e custom_id estável."""

from __future__ import annotations

import logging
import discord

from monitoria_bot.config import Config
from monitoria_bot.database import Database, GuildSettings
from monitoria_bot.views.modals import RegistrationModal

logger = logging.getLogger(__name__)


def build_welcome_embed(settings: GuildSettings) -> discord.Embed:
    """Gera o Embed padrão da mensagem fixa de boas-vindas e instruções da monitoria."""
    embed = discord.Embed(
        title="📐 **Bem-vindo(a) à Monitoria de Cálculo 3!**",
        description=(
            "Este servidor é o canal oficial para apoio e atendimento de dúvidas de Cálculo 3.\n\n"
            "Consulte os dias e horários de atendimento com o comando `/horarios`.\n\n"
            "Para ter acesso completo aos canais de dúvidas e demais recursos do servidor, **você deve se cadastrar** "
            "clicando no botão abaixo."
        ),
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="📝 **Como se Cadastrar**",
        value=(
            "Clique no botão **Realizar cadastro** abaixo ou use o comando `/cadastro`.\n\n"
            "Um formulário privado solicitará seu Nome Completo, RA e Turma (opcional). "
            "Ao concluir, o cargo de **Aluno** será concedido automaticamente."
        ),
        inline=False,
    )

    embed.add_field(
        name="💡 **Como Tirar Dúvidas**",
        value=(
            "Você pode pedir ajuda da forma que for mais confortável:\n\n"
            "• Envie sua dúvida diretamente no canal de dúvidas;\n"
            "• Envie uma mensagem privada (DM) para o monitor;\n"
            "• Use `/duvida criar` para organizar a pergunta em uma thread, informando assunto, título, descrição e, opcionalmente, uma imagem.\n\n"
            "Se quiser atendimento individual em tempo real, também existe a **fila de atendimento**.\n\n"
            "A fila é **opcional** e serve principalmente para avisar ao monitor que você está aguardando atendimento. Para entrar, use `/fila entrar assunto`.\n\n"
            "Você não precisa usar a fila para fazer perguntas."
        ),
        inline=False,
    )

    embed.add_field(
        name="📌 **Boas Práticas ao Enviar Dúvidas**",
        value=(
            "Para um atendimento mais ágil, sempre que possível inclua:\n\n"
            "1. **Enunciado completo** da questão;\n"
            "2. Sua **tentativa de resolução** (foto ou rascunho);\n"
            "3. O **ponto exato da dificuldade** onde você travou."
        ),
        inline=False,
    )

    embed.add_field(
        name="🤝 **Regras Curtas de Convivência**",
        value=(
            "• Mantenha o respeito com colegas e monitores.\n"
            "• As dúvidas e threads são públicas para que outros alunos também possam acompanhar e aprender.\n"
            "• Não envie dados pessoais no chat público."
        ),
        inline=False,
    )

    embed.add_field(
        name="⚠️ **Avisos Importantes e Privacidade**",
        value=(
            "• **Autodeclaração:** o cadastro realizado no servidor é autodeclarado e não comprova matrícula institucional formal.\n"
            "• **Privacidade do RA:** seu RA é coletado exclusivamente para controle de presença e identificação acadêmica pelos monitores e professores responsáveis, com acesso restrito. O RA não é exibido em threads públicas ou na fila.\n"
            "• **Correção e Exclusão:** para corrigir ou solicitar a exclusão de seus dados cadastrados, procure um monitor ou professor responsável."
        ),
        inline=False,
    )

    return embed


class RegistrationView(discord.ui.View):
    """View persistente associada à mensagem de boas-vindas."""

    def __init__(self, db: Database, config: Config) -> None:
        super().__init__(timeout=None)
        self.db = db
        self.config = config

    @discord.ui.button(
        label="Realizar cadastro",
        style=discord.ButtonStyle.primary,
        custom_id="monitoria:btn_register",
        emoji="📝",
    )
    async def register_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Esta ação só pode ser executada em um servidor Discord.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        member = interaction.user
        guild_id = str(guild.id)
        user_id = str(member.id)

        settings = await self.db.get_guild_settings(guild_id)
        if not settings:
            await interaction.response.send_message(
                "❌ O bot ainda não foi configurado pelo administrador deste servidor (`/configurar`).",
                ephemeral=True,
            )
            return

        student = await self.db.get_student(guild_id, user_id)

        # Caso 1: Usuário ainda não cadastrado -> abre o modal
        if not student:
            classes = await self.db.get_classes(guild_id)
            modal = RegistrationModal(self.db, self.config, settings, classes=classes)
            await interaction.response.send_modal(modal)
            return


        student_role = guild.get_role(int(settings.student_role_id))

        # Caso 2: Já cadastrado e ativo
        if student.status == "active":
            has_role = any(str(r.id) == settings.student_role_id for r in member.roles)
            if not has_role and student_role:
                try:
                    await member.add_roles(student_role, reason="Restaurando cargo Aluno de cadastro ativo")
                    await interaction.response.send_message(
                        f"✅ Seu cadastro já estava ativo (RA: **{student.ra}**). "
                        f"O cargo **{student_role.name}** foi restaurado com sucesso!",
                        ephemeral=True,
                    )
                except Exception as e:
                    logger.error("Erro ao restaurar cargo para %s: %s", user_id, e)
                    await interaction.response.send_message(
                        "⚠️ Seu cadastro está ativo, mas o bot não conseguiu atribuir o cargo no Discord. "
                        "Favor procurar um monitor.",
                        ephemeral=True,
                    )
            else:
                await interaction.response.send_message(
                    f"ℹ️ Você já possui um cadastro ativo neste servidor (RA: **{student.ra}**).\n"
                    "Caso precise corrigir seus dados, solicite a um monitor ou utilize `/meu-cadastro`.",
                    ephemeral=True,
                )
            return

        # Caso 3: Cadastro em estado pending_role -> tenta concluir atribuição de cargo
        if student.status == "pending_role":
            if not student_role:
                await interaction.response.send_message(
                    "⚠️ O cargo de Aluno configurado não foi encontrado no servidor. Avise a monitoria.",
                    ephemeral=True,
                )
                return

            try:
                await member.add_roles(student_role, reason="Ativando cargo Aluno de cadastro pendente")
                await self.db.activate_student(guild_id, user_id)
                await interaction.response.send_message(
                    f"✅ Cadastro ativado com sucesso, **{student.full_name}**! "
                    f"O cargo **{student_role.name}** foi atribuído.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error("Erro ao ativar cadastro pendente para %s: %s", user_id, e)
                await interaction.response.send_message(
                    "⚠️ Ainda não foi possível atribuir o cargo no Discord. Verifique a hierarquia de cargos com a moderação.",
                    ephemeral=True,
                )
