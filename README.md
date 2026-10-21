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
- **Watchlist**: filmes que você quer ver no futuro. Adicione pelo botão `＋  Watchlist` nos detalhes ou pelo clique
  direito; a lista fica na barra lateral.
- **Fonte dos metadados** (Configurações): TMDB (padrão) ou OMDb. O OMDb é gratuito (1.000 consultas/dia), só tem dados em
  inglês e não traz imagem de fundo nem trailer. Ao trocar de fonte, use **Metadados ▾ → Forçar atualização**
  para reidentificar os filmes já baixados.
- **Reescanear** (`F5`): roda ao abrir o app; detecta filmes novos e remove os que sumiram do disco.
  Arquivos movidos para outra subpasta mantêm metadados, coleções e marcações.
- **Metadados ▾**: buscar pendentes, forçar atualização de todos (mantém correspondências confirmadas)
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
