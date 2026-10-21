# CineLocal

Navegador de filmes locais para Linux e Windows, com visual estilo Netflix em preto e azul (modo noturno).
Rápido e offline: a internet só é usada para baixar capas e informações de filmes novos
(ou quando você força uma atualização).

## Instalação (Linux Mint / Ubuntu / Debian)

```bash
unzip cinelocal.zip && cd cinelocal
./install.sh
```

O script instala as bibliotecas do sistema que faltarem (pede a senha de administrador),
cria um ambiente virtual com o PySide6 e adiciona o **CineLocal** ao menu de aplicativos.
Para só testar sem instalar: `./run.sh`. Para remover: `./uninstall.sh` (`--purge` apaga também os dados).

## Instalação (Windows 10/11)

1. Instale o **Python 3.10 a 3.12** em [python.org/downloads/windows](https://www.python.org/downloads/windows/),
   marcando **"Add python.exe to PATH"** no instalador.
2. Extraia o zip do CineLocal e dê dois cliques em **`install.bat`** (ou rode `install.bat` no Prompt de Comando,
   dentro da pasta extraída).
3. Para usar o **player integrado**, instale também o [VLC](https://www.videolan.org/vlc/) de 64 bits
   (`winget install VideoLAN.VLC`). Sem ele o CineLocal abre o filme no player padrão do Windows.
4. Abra o **CineLocal** pelo Menu Iniciar.

O script copia o app para `%LOCALAPPDATA%\Programs\cinelocal`, cria um ambiente virtual com o PySide6
(precisa de internet, ~200 MB) e adiciona o atalho no Menu Iniciar. Não precisa de administrador.
Para só testar sem instalar: `run.bat`. Para remover: `uninstall.bat` (`--purge` apaga também os dados).

## Desinstalação

Seus filmes **nunca são apagados**: o uninstall só remove o app e, se você pedir, os dados do CineLocal.

### Linux

1. Abra um terminal na pasta extraída do CineLocal (a mesma do `install.sh`).
2. Se aparecer `Permissão negada`, dê permissão de execução ao script (alguns extratores de zip perdem essa permissão):

   ```bash
   chmod +x uninstall.sh
   ```

3. **Uninstall** — remove o app, o atalho do menu e o ícone, mas mantém biblioteca, capas e configurações
   (se reinstalar depois, tudo continua como estava):

   ```bash
   ./uninstall.sh
   ```

4. **Purge** (opcional) — remove também todos os dados. Isso apaga a biblioteca, as capas em cache, a chave da API
   e as posições salvas de "continuar assistindo", e não tem volta:

   ```bash
   ./uninstall.sh --purge
   ```

   Pastas removidas pelo purge: `~/.config/cinelocal`, `~/.local/share/cinelocal` e `~/.cache/cinelocal`.

### Windows

1. Abra o Prompt de Comando na pasta extraída do CineLocal (a mesma do `install.bat`). Não precisa de `chmod`
   nem de administrador.
2. **Uninstall** — remove o app e o atalho do Menu Iniciar, mantendo os dados:

   ```bat
   uninstall.bat
   ```

3. **Purge** (opcional) — remove também biblioteca, capas, chave da API e posições salvas, sem volta:

   ```bat
   uninstall.bat --purge
   ```

   Pastas removidas pelo purge: `%APPDATA%\cinelocal` e `%LOCALAPPDATA%\cinelocal`.

## Primeiros passos

1. Abra o app e clique em **Selecionar pasta de filmes** (a pasta é lida recursivamente).
2. Cole sua **chave gratuita do TMDB**: crie uma conta em themoviedb.org → Configurações → API →
   copie a "Chave da API" (ou o "Token de leitura"). Use **Testar** para validar.
3. O app identifica cada arquivo pelo nome (ignora `1080p`, `BluRay`, `[YTS]`... e usa o ano, se existir),
   baixa capa, sinopse, nota, elenco etc. em segundo plano e guarda tudo localmente.

## Uso

- **Grade**: clique numa capa para abrir os detalhes (na mesma janela; `←  Voltar`, `Esc` ou `Alt`+`←` voltam à lista
  exatamente onde você estava). `Ctrl`/`Shift`+clique seleciona vários filmes;
  clique direito abre o menu (favoritar, assistido, coleções, atualizar, corrigir correspondência).
- **Busca instantânea** (`Ctrl+F`) por título, ator, diretor ou gênero; **ordenação** por título, ano,
  nota ou adicionados recentemente.
- **Barra lateral**: Todos, Favoritos, Assistidos/Não assistidos, **Coleções** (um filme pode estar em várias),
  Gêneros e Anos (décadas). Clique direito numa coleção para renomear ou excluir.
- **Assistir** abre o **player integrado** (baseado no libVLC): `Espaço` pausa, `←`/`→` pulam 10 s, `↑`/`↓` mudam o
  volume, `M` muda o mudo, `F` tela cheia e `Esc` volta. Precisa do VLC instalado (no Linux o `install.sh` instala) e,
  no Linux, de uma sessão X11. Sem isso, ou se você definir um player em Configurações (ex.: `mpv --fs`),
  o filme abre no player externo (`xdg-open` no Linux, o programa associado no Windows).
  Ao passar de 95% o filme é marcado como assistido; ao fim de um episódio, o player oferece o próximo. Na grade, uma
  barra na capa mostra quanto já foi visto, e **Continuar assistindo** (barra lateral) reúne o que está pela metade
  (séries incluídas, com o episódio em andamento); "Assistir do início" fica no clique direito.
  O volume e os ajustes de imagem são lembrados entre filmes; na engrenagem (botão Configurações do player) há também **velocidade** (0,5x a 2x) e **atraso da
  legenda**, e a barra de progresso mostra o tempo do ponto sob o mouse.
  Em Configurações você escolhe o **player padrão** (integrado ou externo); clique direito num filme (ou o menu Configurações do player)
  para abrir no outro. O player integrado lembra onde você parou e retoma de lá, mesmo após fechar o app.
  No player, o botão **Configurações** reúne **Áudio** e **Legendas** (faixas que vêm no arquivo) e **Imagem**
  (brilho, contraste, cor e nitidez). Em tela cheia, os controles e o ponteiro somem depois de alguns segundos sem mexer o mouse.
- **Séries**: arquivos com `S01E02`, `1x02` ou `Temporada 1 Episódio 2` no nome (ou dentro de pastas `Temporada N`)
  são agrupados numa única capa de série, que abre a lista de temporadas e episódios, cada um com seus metadados.
  Séries aparecem com o selo “Série” na grade e ficam fora das coleções.
- **Watchlist**: filmes que você quer ver no futuro. Adicione pelo botão `Watchlist` nos detalhes ou pelo clique
  direito; a lista fica na barra lateral.
- **Fonte dos metadados** (Configurações): TMDB (padrão) ou OMDb. O OMDb é gratuito (1.000 consultas/dia), só tem dados em
  inglês e não traz imagem de fundo nem trailer. Ao trocar de fonte, use **Metadados → Forçar atualização**
  para reidentificar os filmes já baixados.
- **Reescanear** (`F5`): roda ao abrir o app; detecta filmes novos e remove os que sumiram do disco.
  Arquivos movidos para outra subpasta mantêm metadados, coleções e marcações.
- **Metadados**: buscar pendentes, forçar atualização de todos (mantém correspondências confirmadas)
  ou revisar filmes sem correspondência. Quando o app não tem certeza (remakes, título ambíguo, nada
  encontrado), o filme ganha o selo **Revisar** e você escolhe o correto numa janela.
- **Idioma** dos metadados: padrão `pt-BR` (com inglês como reserva quando falta tradução);
  altere em Configurações.

## Onde ficam os dados

| O quê | Onde |
|---|---|
| Biblioteca, coleções, marcações (SQLite) | `~/.local/share/cinelocal/library.db` |
| Capas, miniaturas e fundos | `~/.cache/cinelocal/images/` |
| Configurações (inclui a chave do TMDB) | `~/.config/cinelocal/settings.json` (permissão 600) |

No Windows: biblioteca em `%LOCALAPPDATA%\cinelocal\library.db`, capas em `%LOCALAPPDATA%\cinelocal\cache\images\`
e configurações em `%APPDATA%\cinelocal\settings.json`.

Seus arquivos de vídeo nunca são modificados.

## Estrutura do código

```
main.py                     ponto de entrada
cinelocal/
  config.py                 caminhos, extensões, configurações (JSON)
  db.py                     SQLite: filmes, coleções, marcações
  scanner.py                varredura da pasta e limpeza de nomes de arquivo
  library.py                sincroniza disco ↔ banco (novos, removidos, movidos)
  tmdb.py                   cliente HTTP do TMDB
  omdb.py                   cliente HTTP do OMDb (devolve o mesmo formato do TMDB)
  providers.py              escolhe o cliente conforme a fonte configurada
  parsing.py                interpreta respostas e escolhe a melhor correspondência
  metadata_service.py       identifica o filme, baixa metadados e imagens
  images.py                 cache de capas/miniaturas/fundos
  workers.py                threads (atualização em paralelo, tarefas em segundo plano)
  service.py                estado em memória + operações usadas pela interface
  filters.py                filtros, busca, ordenação e contagens
  player.py                 abre o filme no player externo
  ui/                       tema (QSS), grade, barra lateral, janelas e diálogos
  ui/player_page.py         player integrado (libVLC)
tests/test_core.py          testes da lógica sem interface
```

Testes: `python3 -m unittest discover -s tests`

## Observações

- Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB.
- Formatos reconhecidos: mkv, mp4, avi, mov, wmv, m4v, webm, flv, ts. Para mudar, edite `VIDEO_EXTENSIONS`
  em `cinelocal/config.py`.
