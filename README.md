# Bot de Monitoria de Cálculo 3 (Discord)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7.1-informational.svg)](https://discordpy.readthedocs.io/)
[![SQLite](https://img.shields.io/badge/sqlite-WAL%20Mode-success.svg)](https://www.sqlite.org/)

Bot de Discord para auxílio operacional às monitorias de **Cálculo 3**, focado em simplicidade, estabilidade e conformidade estrita com o princípio do menor privilégio.

O bot permite gerenciar o atendimento síncrono e assíncrono entre alunos e a equipe de monitoria com persistência completa em SQLite local (`data/bot.db`).

---

## 📌 Funcionalidades do MVP

- **Configuração Segura (`/configurar`):** Parametrização dinâmica de canais e cargos pelo administrador com validação rigorosa de permissões perigosas no cargo Aluno e conferência da hierarquia do bot.
- **Boas-vindas e Cadastro Efêmero (`/boas-vindas`, `/cadastro`):** Mensagem fixa com botão persistente que abre formulário privado (Modal) para coleta de Nome, RA e Turma (com seleção de opções padrão no banco de dados: Engenharia de Computação, Engenharia Civil, Engenharia Eletrônica e opção "Outro"). Atribui o cargo Aluno automaticamente sem expor dados em chats públicos.

- **Preservação e Validação de RA:** O RA é armazenado como texto, preservando zeros à esquerda (ex: `0012345`) com validação configurável por regex (`RA_REGEX`).
- **Dúvidas em Tópicos (`/duvida criar`, `/duvida minhas`, `/duvida resolver`):** Criação de mensagens com threads públicas associadas para cada dúvida, suportando anexos de imagens sem necessidade de download local ou OCR.
- **Fila FIFO de Atendimento (`/fila`):** Fila sequencial com controle de concorrência atômico (proteção contra chamadas simultâneas duplicadas), suporte a saída voluntária e limpeza administrativa.
- **Acervo de Links de Estudo (`/material`):** Cadastro e pesquisa indexada por termos e tags para links externos (HTTP/HTTPS) recomendados pelos monitores.
- **Horários Flexíveis (`/horarios`):** Consulta do cronograma de atendimento com fuso horário de referência (`America/Sao_Paulo`).
- **Rotina de Backup Atômico (`scripts/backup_db.py`):** Cópia consistente a quente utilizando a **SQLite Online Backup API**, segura mesmo em modo WAL com escritas ativas.
- **Pronto para Produção em VM (`deploy/monitoria-bot.service`):** Arquivo de serviço `systemd` para inicialização automática no boot, reinício resiliente e isolamento com usuário sem privilégios de root.

---

## 📚 Documentação Técnica Completa

- [Guia Passo a Passo no Discord Developer Portal](docs/discord-setup.md): Criação da aplicação, token, escopos, matriz de permissões e prevenção de envio público de RA.
- [Guia de Uso e Referência de Comandos](docs/usage.md): Tabela de comandos com perfis autorizados, argumentos e jornadas detalhadas de aluno e monitor.
- [Guia de Operação na VM e Instalação do SQLite](docs/deployment.md): Passo a passo para VM Ubuntu 22.04, systemd, logs com journald, backups com cron e restauração.
- [Modelo de Dados e Ciclo de Vida](docs/database.md): Schema SQLite, máquinas de estado, recuperação de pendências e procedimento de exclusão e privacidade.

---

## 🛠️ Pré-requisitos Locais

- **Python 3.12 ou superior**
- **SQLite 3.37 ou superior** (com suporte a WAL e índices parciais)
- Git

---

## 🚀 Instalação e Execução Local

### 1. Clonar o repositório
```bash
git clone <url-do-repositorio>
cd bot-monitoria-calculo3
```

### 2. Criar e ativar o ambiente virtual
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar o pacote e dependências
```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### 4. Configurar as variáveis de ambiente
Copie o template de exemplo:
```bash
cp .env.example .env
```
Edite o arquivo `.env` inserindo o seu `DISCORD_TOKEN`:
```env
DISCORD_TOKEN=seu_token_aqui_sem_aspas
DATABASE_PATH=./data/bot.db
LOG_LEVEL=INFO
RA_REGEX=^[A-Za-z0-9]{1,32}$
# Opcional: ID do servidor de testes para sincronização imediata de comandos
DISCORD_GUILD_ID=
```

### 5. Executar o bot localmente
```bash
python -m monitoria_bot
```

---

## 🧪 Testes Automatizados

O projeto conta com suíte abrangente de testes unitários e de integração utilizando `pytest` e `aiosqlite`, sem depender de tokens de rede ou conexão com o Discord:

```bash
pytest -v --tb=short
```

---

## 📋 Checklist Manual para Validação no Discord

Quando estiver com um bot configurado em um servidor real:
- [ ] Convidar o bot apenas com os escopos `bot` e `applications.commands`.
- [ ] Posicionar o cargo do bot acima do cargo **Aluno** na lista de cargos.
- [ ] Executar `/configurar` informando os canais e cargos criados.
- [ ] Executar `/boas-vindas` e verificar se a mensagem oficial e o botão aparecem no canal de entrada.
- [ ] Entrar com uma conta secundária de aluno e clicar em **Realizar cadastro**.
- [ ] Preencher o modal com um RA contendo zeros à esquerda (ex: `0012345`) e verificar a liberação instantânea dos canais restritos.
- [ ] Reiniciar o bot na máquina e clicar no botão antigo para testar a persistência da View.
- [ ] Abrir uma dúvida com `/duvida criar` e verificar a criação da thread correspondente.
- [ ] Entrar na fila com `/fila entrar`, chamar com o monitor `/fila proximo` e conferir se apenas o aluno é mencionado no canal da fila.

---

## ⚠️ Limitações do MVP e Funcionalidades Futuras

### Limitações Conhecidas do MVP
- **Instância Única:** O bot deve rodar em processo único em uma VM; não utilize múltiplas instâncias concorrentes sob o mesmo banco de dados.
- **Links de Materiais:** Os materiais são URLs externas; o bot não armazena, baixa nem faz upload de PDFs no servidor local.
- **Fila Única:** Um atendimento ativo por guilda no modelo do MVP.

### Funcionalidades Futuras Planejadas (Fora do MVP)
- Suporte a múltiplos atendimentos concorrentes com painel de monitores.
- Relatórios consolidados de frequência por período letivo.
- Notificações automáticas de início de plantão baseadas em agendamentos recorrentes.
