# criar_modpack_minecraft

Módulo complexo da Ayla, descoberto automaticamente pela entrada
`../criar_modpack_minecraft.py`. Não exige pacotes Python adicionais nem chave de
API. Se a engine já estiver aberta, recarregue o catálogo de módulos.

Ferramentas expostas:

- `pesquisar_mods_minecraft(versao_minecraft, loader, consulta='', limite=10, offset=0)`:
  consulta Modrinth e confere se existe uma versão que atende simultaneamente ao
  Minecraft e loader. Consulta vazia lista mods; use `proximo_offset` para continuar
  a paginação. O total é da pesquisa antes da conferência individual das versões.
- `criar_modpack_minecraft(versao_minecraft, loader, mods, pasta_destino='',
  nome='Modpack Ayla', versao_loader='')`: aceita IDs/slugs retornados pela pesquisa.
  Loader: `forge` ou `fabric`. Salva sempre em `DocumentosCriados/modpacks` dentro
  da instalação da Ayla. `pasta_destino` é opcional e define somente o nome da
  subpasta; se omitido, usa `nome`. Caminhos antigos Windows/Linux fornecem apenas
  o último nome, sem escrever fora dessa área. A subpasta deve ser nova.

Exemplo de argumentos para montagem:

```json
{
  "versao_minecraft": "1.20.1",
  "loader": "fabric",
  "mods": ["sodium", "fabric-api"],
  "pasta_destino": "modpack_fabric_1201",
  "nome": "Meu modpack"
}
```

A resolução prefere releases e datas mais recentes, respeita dependências
obrigatórias transitivas e versões fixadas, evita ciclos e tenta alternativas
quando encontra conflitos declarados. Dependências opcionais e embutidas não são
baixadas automaticamente. Uma dependência obrigatória sem ID resolvível causa
falha explícita. Limites: 100 mods solicitados, 200 projetos resolvidos, 10000
passos de resolução, 512 MiB por JAR e 2 GiB de download total.

Saída:

- `mods/*.jar`: arquivos principais baixados do CDN HTTPS do Modrinth.
- `manifest.json`: inventário Ayla versionado, com Minecraft, loader, projetos,
  versões exatas, dependências, URLs, tamanhos e hashes. Não é um arquivo de
  importação CurseForge/Modrinth.
- `INSTALACAO.txt`: instruções para criar a instância no launcher e copiar os mods.

`versao_loader` é uma informação opcional para instalação manual e não é validada
contra o catálogo do loader. Sem ela, as instruções pedem selecionar uma versão
compatível. O módulo não baixa o jogo, Java ou o instalador do loader.

Os downloads ficam em uma pasta temporária até terminar a montagem. Falhas de
rede, tamanho ou SHA-512 antes da publicação removem essa área e não criam o
destino. Se houver falha durante a publicação, o erro identifica a pasta parcial
para inspeção; ela não será sobrescrita em uma nova tentativa.

O retorno usa `ResultadoFerramenta`, que a engine serializa com
`verificacao.estado`, `evidencias` e `limite`. `verificado` significa que os JARs
foram relidos, tamanho/hash conferidos, estrutura ZIP aberta e manifest/instruções
comparados integralmente. Não significa que o Minecraft foi iniciado ou que não
existem conflitos não declarados pelos autores. Erros retornam `falhou`.

Testes (API e downloads simulados, sem rede):

```sh
python3 -m unittest test_ayla_minecraft_modpack -v
```

Referências da API implementada:

- https://docs.modrinth.com/api/operations/searchprojects/
- https://docs.modrinth.com/api/operations/getprojectversions/
- https://docs.modrinth.com/api/operations/getversion/
