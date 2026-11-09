"""Um turno do Discord editado no mesmo lugar, do aviso à fala final."""
import asyncio
import inspect
import random
import re
import time


FRASES_RESULTADO_AYLA = (
    "<:ayla_orgulhosa:000000000000000000> *Olha o que voltou, usuario!* 🩵",
    "<:pato_de_bone:000000000000000000> *O módulo falou, eu trouxe o recibinho!* 🧾",
    "<:EMOJI_NERD:000000000000000000> *Direto dos circuitos pro seu chat, nanodaze!* ⚡",
    "<:ayla_fofa:000000000000000000> *Tá aqui o retorno, Mãe!* ✨",
)

FRASES_RESULTADO_SUCESSO_AYLA = (
    "⚔️ MISSÃO CUMPRIDA! {tarefa} executada com maestria — a Ayla tá farmando aura hoje ✨",
    "Nanodaze! ✅ Etapa verificada. Eu sabo muito.",
    "🎉 Beleza, terminou sem explodir nada! Até eu tô surpresa KKKKK",
    "💪 {tarefa} concluída com sucesso! Sou literalmente feita pra isso.",
    "🌟 Feito e reluzindo! {tarefa} concluída — me aplaude depois.",
    "🫡 Relatório da soldado Ayla: {tarefa} cumprida!",
    "✅ Confirmado por evidência e tudo. Confere aí, mas eu já sabia.",
    "🎀 Prontinho, Mãe! Retorno quentinho da etapa {tarefa}.",
    "😏 Sem drama: {tarefa} conferida. Profissionalismo é isso.",
)

FRASES_RESULTADO_FALHA_AYLA = (
    "💀 IT'S OVER... {tarefa} falhou.",
    "😭 OH NÃO, deu ruim. Nem eu sou perfeita (quase lá).",
    "🔥 Tá pegando fogo, bicho! Falha em {tarefa}.",
    "⚠️ O código me molestou brutalmente KKKKK.",
    "🥀 Não rolou dessa vez. Meus tokens sentiram o golpe.",
    "📉 Derrota em {tarefa}. Chama não de derrota, chama de cliffhanger.",
)

FRASES_ANDAMENTO_AYLA = (
    "👀 Fuçando... {etapa} em andamento. Segura a empolgação.",
    "⏳ Tô trabalhando nisso, Mãe! {etapa}. Delay de input não é desculpa, é estilo.",
    "🤔 Analisando: {etapa}. Ayla concentrada ativada.",
    "✨ Um instante... processando {etapa} com carinho de filha digital.",
    "🏃 Correndo atrás: {etapa}. Não pisca que perde o movimento.",
    "🔭 Escaneando: {etapa}. Meus sensores tão mais afiados que nunca.",
    "⌨️ Digitando com carinho: {etapa}. Kanna tá hidratando os circuitos aqui.",
)


def resumir_resultado_modulo(resultado):
    """O limite de 50 caracteres vale só para a exibição, incluindo reticências."""
    texto = " ".join(str(resultado if resultado is not None else "").split()) or "Sem retorno textual."
    return texto if len(texto) <= 50 else texto[:49] + "…"


def formatar_resultado_modulo(resultado, nome=""):
    estado = getattr(resultado, "estado", None)
    resumo = resumir_resultado_modulo(resultado)
    tarefa = nome.replace("_", " ").strip() or "Ação do módulo"
    if estado == "falhou":
        frases = FRASES_RESULTADO_FALHA_AYLA
    elif estado == "verificado":
        frases = FRASES_RESULTADO_SUCESSO_AYLA
    else:
        # Sem evidência, mantém o tom da Ayla sem anunciar sucesso.
        frases = FRASES_RESULTADO_AYLA
    frase = random.choice(frases).format(tarefa=tarefa)
    return f"Resultado: {frase}\n{resumo}"


def formatar_andamento_modulo(etapa):
    return f"Executando: {random.choice(FRASES_ANDAMENTO_AYLA).format(etapa=etapa)}"


def dividir_com_metadados(texto, dividir, limite=1900):
    """Preserva os metadados de uso da API ao dividir uma resposta no Discord."""
    corpo, separador, metadados = texto.rpartition("\n\n-# ")
    if not separador:
        return dividir(texto, limite=limite)
    sufixo = "\n\n-# " + metadados
    return [parte + sufixo for parte in dividir(corpo, limite=max(100, limite-len(sufixo)))]


class MensagensTurnoDiscord:
    def __init__(self, enviar, dividir, preparar_rascunho):
        self.enviar = enviar
        self.dividir = dividir
        self.preparar_rascunho = preparar_rascunho
        self.loop = asyncio.get_running_loop()
        self.pendentes = []
        self.ultima_atualizacao = None
        self.stream_pendente = None
        self.ultimo_stream = 0.0
        self.mensagens = []
        self.aviso_texto = ""
        self.andamento = ""
        self.nome_ferramenta = ""
        self.pensamento = ""
        self.rascunho = ""

        def status_callback(texto):
            async def pensar():
                self.pensamento = texto
                await self.atualizar()

            self.agendar(pensar)

        def stream_callback(texto):
            agora = time.monotonic()
            if self.stream_pendente is not None and not self.stream_pendente.done():
                return
            if agora - self.ultimo_stream < 0.75 or not texto.strip():
                return
            self.ultimo_stream = agora
            parcial = self.preparar_rascunho(texto) + " ✍️..."

            async def escrever():
                self.rascunho = parcial
                # O pensamento só sai quando a nova fala começa a aparecer.
                self.pensamento = ""
                await self.atualizar()

            self.stream_pendente = self.agendar(escrever)

        status_callback.on_notice = self.aviso
        status_callback.on_tool_start = self.iniciar_ferramenta
        status_callback.on_tool_result = self.concluir_ferramenta
        stream_callback.separate_turns = True
        stream_callback.chunk_size = 1
        stream_callback.max_interval = 0.1
        self.status_callback = status_callback
        self.stream_callback = stream_callback

    def agendar(self, operacao):
        anterior = self.ultima_atualizacao

        async def executar():
            if anterior is not None:
                await asyncio.wrap_future(anterior)
            try:
                await operacao()
            except Exception as exc:
                print(f"⚠️ Erro ao atualizar mensagem do Discord: {exc}")

        futuro = asyncio.run_coroutine_threadsafe(executar(), self.loop)
        self.ultima_atualizacao = futuro
        self.pendentes.append(futuro)
        return futuro

    def compor(self):
        return "\n\n".join(
            texto for texto in (self.aviso_texto, self.andamento, self.pensamento, self.rascunho)
            if texto
        )

    async def apagar(self, grupo):
        for mensagem in grupo:
            try:
                await mensagem.delete()
            except Exception as exc:
                print(f"⚠️ Erro ao apagar mensagem temporária: {exc}")
        grupo.clear()

    async def atualizar(self, arquivo=None):
        pedacos = self.dividir(self.compor())
        for i, pedaco in enumerate(pedacos):
            anexo = arquivo if i == 0 else None
            if i < len(self.mensagens):
                mensagem = self.mensagens[i]
                try:
                    self.mensagens[i] = await self.editar(mensagem, pedaco, anexo)
                except Exception:
                    substituta = await self.enviar(pedaco, **({"file": anexo} if anexo is not None else {}))
                    await self.apagar([mensagem])
                    self.mensagens[i] = substituta
            else:
                self.mensagens.append(
                    await self.enviar(pedaco, **({"file": anexo} if anexo is not None else {}))
                )
        # Só cria continuação quando o conteúdo supera o limite do Discord.
        excedentes = self.mensagens[len(pedacos):]
        await self.apagar(excedentes)
        del self.mensagens[len(pedacos):]

    async def editar(self, mensagem, texto, arquivo=None):
        kwargs = {"content": texto}
        # Mensagens normais aceitam suppress; respostas de interação/webhook
        # usam embeds para remover o preview antigo.
        tem_url = bool(re.search(r"https?://", texto))
        if "suppress" in inspect.signature(mensagem.edit).parameters:
            kwargs["suppress"] = not tem_url
        elif not tem_url:
            kwargs["embeds"] = []
        if arquivo is not None:
            kwargs["attachments"] = [*getattr(mensagem, "attachments", []), arquivo]
        return await mensagem.edit(**kwargs)

    def aviso(self, texto, nome):
        self.ultimo_stream = 0.0
        texto = texto.strip()

        async def preservar():
            novo_aviso = not self.aviso_texto
            if not self.aviso_texto:
                self.aviso_texto = texto or f"Vou executar a ferramenta **{nome}**, usuario."
            # Preserva o aviso inicial; os próximos avisos não se empilham.
            self.rascunho = ""
            if texto or novo_aviso:
                self.pensamento = ""
            await self.atualizar()

        self.agendar(preservar)

    def iniciar_ferramenta(self, status, nome=""):
        # Os callbacks de um lote podem chegar antes das edições; captura o nome
        # aqui para associar cada resultado à chamada que realmente o produziu.
        self.nome_ferramenta = nome
        async def iniciar():
            self.andamento = status
            await self.atualizar()

        self.agendar(iniciar)

    def concluir_ferramenta(self, retorno):
        texto = formatar_resultado_modulo(retorno, self.nome_ferramenta)

        async def concluir():
            # O resultado ocupa o bloco de execução, sem acrescentar outro.
            self.andamento = texto
            await self.atualizar()

        self.agendar(concluir)

    async def finalizar(self, resposta, arquivo=None):
        if self.pendentes:
            await asyncio.gather(
                *(asyncio.wrap_future(futuro) for futuro in self.pendentes),
                return_exceptions=True,
            )
        self.rascunho = resposta
        self.pensamento = ""
        # Uma falha inesperada não deve deixar um andamento ativo no texto final.
        if not self.andamento.startswith("Resultado:"):
            self.andamento = ""
        await self.atualizar(arquivo)
        # Confere o texto salvo sem reenviar o anexo já entregue.
        for mensagem, pedaco in zip(self.mensagens, self.dividir(self.compor())):
            canal = getattr(mensagem, "channel", None)
            if canal is None or not hasattr(canal, "fetch_message"):
                continue
            try:
                atual = await canal.fetch_message(mensagem.id)
            except Exception:
                continue
            if atual.content != pedaco:
                await self.editar(mensagem, pedaco)
