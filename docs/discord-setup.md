# Guia de Configuração no Discord — Passo a Passo

Este guia detalha a configuração completa no Discord Developer Portal e no servidor Discord para a operação segura do **Bot de Monitoria de Cálculo 3**.

---

## 1. Criação da Aplicação e do Bot no Discord Developer Portal

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications).
2. Clique em **New Application** no canto superior direito.
3. Nomeie a aplicação (ex: `Monitoria de Cálculo 3`) e confirme os termos.
4. No menu lateral esquerdo, navegue até a aba **Bot**:
   - Altere o nome de exibição e adicione um avatar se desejar.
   - Clique em **Reset Token** para gerar o token inicial.
   - **IMPORTANTE:** Copie o token imediatamente e armazene-o de forma segura (por exemplo, no arquivo de variáveis de ambiente da VM ou gerenciador de senhas). **Nunca versione o token no Git nem o compartilhe em chats.**
   - Caso o token seja exposto acidentalmente, retorne a esta tela imediatamente e clique em **Reset Token** para revogar a credencial antiga.

---

## 2. Configuração de Privileged Gateway Intents

No menu **Bot** > seção **Privileged Gateway Intents**:

- **Presence Intent:** `DESATIVADO` (Não necessário).
- **Server Members Intent:** `DESATIVADO` (Não necessário para o MVP).
- **Message Content Intent:** `DESATIVADO` (Não necessário).

> [!NOTE]
> O bot opera inteiramente através de **Slash Commands (`/`)**, **Botões** e **Modais**. As interações com o bot não exigem leitura de mensagens comuns nem monitoramento do conteúdo enviado pelos usuários, respeitando o princípio do menor privilégio e dispensando autorizações especiais do Discord.

---

## 3. Geração do Link de Convite (OAuth2 & Permissões Mínimas)

No menu lateral esquerdo, acesse **OAuth2** > **URL Generator**:

### 3.1. Escopos Obrigatórios (Scopes)
Marque estritamente:
- `bot`
- `applications.commands`

### 3.2. Permissões de Bot (Bot Permissions)
Selecione exclusivamente as seguintes permissões funcionais:
- **General Permissions:**
  - `Manage Roles` (*Gerenciar Cargos*) — Necessário para que o bot atribua o cargo Aluno ao concluir o cadastro.
- **Text Permissions:**
  - `View Channels` (*Ver Canais*)
  - `Send Messages` (*Enviar Mensagens*)
  - `Create Public Threads` (*Criar Tópicos Públicos*) — Para o canal de dúvidas.
  - `Send Messages in Threads` (*Enviar Mensagens em Tópicos*) — Para respostas e encerramento de dúvidas.
  - `Embed Links` (*Inserir Links*)
  - `Attach Files` (*Anexar Arquivos*)
  - `Read Message History` (*Ver Histórico de Mensagens*)

> [!CAUTION]
> **Nunca conceda a permissão `Administrator` ao bot.** O bot foi projetado para operar estritamente com as permissões acima.

Copie a **Generated URL** no rodapé da página e acesse-a no navegador para adicionar o bot ao servidor desejado.

---

## 4. Organização de Cargos e Hierarquia no Servidor

No Discord, abra as configurações do seu servidor (**Server Settings** > **Roles**):

1. Crie o cargo **Monitor**:
   - Atribua aos monitores e professores.
   - Permissões recomendadas: permissões padrão de membros de equipe, sem necessidade de poderes administrativos.
2. Crie o cargo **Aluno**:
   - Este cargo será concedido automaticamente aos alunos cadastrados.
   - Permissões: permissões básicas padrão (leitura e envio de mensagens em canais liberados).
   - **Regra Crítica:** Não conceda a este cargo nenhuma permissão de moderação ou gerenciamento.
3. **Hierarquia de Cargos:**
   - O cargo gerado para o bot (geralmente com o nome do bot) deve ser arrastado na lista de cargos para ficar **hierarquicamente acima** do cargo **Aluno**.
   - *Por que isso é obrigatório?* No modelo de segurança do Discord, um bot só consegue adicionar ou remover cargos de outros membros se o seu cargo mais alto estiver acima do cargo que ele tenta atribuir.

```text
▲ MAIS ALTO
│  [Dono do Servidor / Administradores]
│  [Cargo do Bot] ◄──── (DEVE ESTAR ACIMA DE ALUNO)
│  [Monitor]
│  [Aluno]
▼  [@everyone]
```

---

## 5. Matriz de Permissões de Canais e Prevenção de Vazamento de RAs

Configure os canais do servidor conforme a matriz abaixo:

| Canal / Categoria | `@everyone` (Não Cadastrados) | Cargo `Aluno` | Cargo `Monitor` | Cargo do `Bot` |
| :--- | :--- | :--- | :--- | :--- |
| **📢 `#boas-vindas`** | ✅ Ver canal<br>❌ Enviar mensagens | ✅ Ver canal<br>❌ Enviar mensagens | ✅ Ver canal<br>❌ Enviar mensagens | ✅ Ver canal<br>✅ Enviar mensagens |
| **💡 `#duvidas`** | ❌ Não ver canal | ✅ Ver canal<br>✅ Enviar mensagens<br>✅ Criar Threads | ✅ Ver canal<br>✅ Enviar mensagens<br>✅ Gerenciar Threads | ✅ Ver canal<br>✅ Enviar mensagens<br>✅ Criar Threads |
| **👥 `#fila-monitoria`** | ❌ Não ver canal | ✅ Ver canal<br>❌ Enviar mensagens | ✅ Ver canal<br>✅ Enviar mensagens | ✅ Ver canal<br>✅ Enviar mensagens |

### 🔒 Proteção Contra Envio de RAs em Chat Público
O bot coleta RAs **exclusivamente através de Modais efêmeros** (que são exibidos apenas na interface local do usuário). Contudo, o bot não impede que usuários desavisados digitem seus RAs em canais de texto abertos.

Para evitar isso:
1. No canal `#boas-vindas`, **desabilite `Send Messages` para `@everyone` e `Aluno`**. Assim, recém-chegados não conseguem digitar mensagens públicas nesse canal; apenas interagem com o botão "Realizar cadastro".
2. Nos canais de monitoria (`#duvidas` e `#fila-monitoria`), reforce que o comando `/cadastro` abre um formulário seguro e privado.

---

## 6. Configuração Inicial e Publicação com Slash Commands

Após convidar o bot e iniciar o serviço na VM ou máquina local:

1. Acesse qualquer canal de texto onde você tenha permissão de Administrador.
2. Execute o comando `/configurar`:
   - Selecione `canal_boas_vindas`: selecione `#boas-vindas`.
   - Selecione `canal_duvidas`: selecione `#duvidas`.
   - Selecione `canal_fila`: selecione `#fila-monitoria`.
   - Selecione `cargo_aluno`: selecione o cargo `@Aluno`.
   - Selecione `cargo_monitor`: selecione o cargo `@Monitor`.
   - `texto_horarios`: informe os horários iniciais (ex: `Segundas e Quartas das 14h às 16h`).
3. O bot validará se as permissões e hierarquias estão corretas. Se houver alguma inconformidade (ex: bot abaixo de Aluno ou falta de permissão em canais), uma mensagem explicativa será retornada sem aplicar a configuração.
4. Execute o comando `/boas-vindas`:
   - O bot publicará o painel oficial com instruções, regras, avisos de privacidade e o botão fixo **Realizar cadastro** no canal `#boas-vindas`.

---

## 7. Validação com Conta Comum de Teste

Para garantir que a configuração está funcionando:

1. Entre no servidor utilizando uma conta secundária do Discord que **não** tenha privilégios de Administrador.
2. Observe que essa conta consegue ver apenas `#boas-vindas` e não tem acesso a `#duvidas` nem `#fila-monitoria`.
3. Clique no botão **Realizar cadastro**.
4. Preencha seu Nome Completo e RA (ex: `001234`).
5. Confirme o envio. A mensagem de sucesso deve ser efêmera (visível apenas para você).
6. Verifique se o cargo **Aluno** foi atribuído e se os canais `#duvidas` e `#fila-monitoria` foram imediatamente desbloqueados.
