**Como adicionar um módulo complexo**

Coloque a entrada `.py` nesta pasta. A entrada mantém o contrato `register(tool_map, function_declarations)` usado pelos outros modos. Implemente as operações em subpastas quando o módulo for grande.

O carregador reconhece esta pasta como complexa. Ativar o módulo retorna somente o catálogo curto; ativar uma ferramenta inclui apenas o schema selecionado na interação corrente. Ativar mais uma ferramenta conserva as já selecionadas nessa interação.

O modo não deve inicializar tarefas ou executar operações externas durante o import. A execução deve acontecer somente nas funções registradas. Os módulos de serviços que precisam sobreviver às respostas pertencem a `MODOS ADICIONAIS CONTINUOS`.

`Discord_ADM.py` demonstra uma entrada pequena com implementação separada por assunto e declarações em `discord_adm/declaracoes.json`.

Também é possível manter implementações em outras linguagens numa subpasta:
o carregador descobre somente as entradas `.py` desta pasta. A entrada Python
registra as ferramentas e chama o processo externo durante sua execução.
`editar_video.py` demonstra essa ponte com `editor_video/backend.py`, uma composição
React e o renderizador JavaScript do Remotion. Consulte `editor_video/README.md`
para instalação e uso com vídeos do Discord e da área de transferência.
