# Changelog

Todos os lançamentos notáveis do py-eye serão documentados aqui.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/),
e esse projeto usa [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [2.1.0] - 2026-11-02

### Adicionado
- Integração com sensores do Termux: proximidade, luz ambiente, acelerômetro e Motoglance.
- Comportamento autônomo com sistema de drives e hábitos persistidos em `brain.json`.
- Motor de áudio com sons sintetizados por `ffmpeg` via `tools/sound_cli.py`.
- Falas em português brasileiro usando `termux-tts-speak`.
- Interpolação contínua de poses a 24 FPS, sem saltos entre expressões.

### Alterado
- README reestruturado com documentação visual e exemplos práticos.
- Comportamentos ganharam novas expressões: shy, smug, dizzy, talking.
- Indicadores sutis de sensores no topo da moldura dos olhos.

## [2.0.0] - 2026-06-27

### Adicionado
- Versão autônoma sem hotkeys fixas.
- Sistema de personalidade e memória de hábitos.
- Engine de renderização interpolada.

### Removido
- Seleção de expressões por teclas diretas.

## [1.0.0] - 2026-06-26

### Adicionado
- Versão inicial com olhos robóticos em terminal.
- Expressões básicas via curses.
- Suporte a Termux e Termux:Float.
