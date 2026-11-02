<p align="center">
  <img src="scr/mata-hijau.jpg" alt="py-eye em ação" width="480">
</p>

<h1 align="center">py-eye</h1>

<p align="center">
  Olhos robóticos autônomos direto no seu terminal.<br>
  Feito para <strong>Termux</strong>, animado com <strong>curses</strong>, vivo com <strong>numpy</strong>.
</p>

<p align="center">
  <a href="https://github.com/anonvict/py-eye/actions/workflows/tests.yml">
    <img alt="CI" src="https://img.shields.io/github/actions/workflow/status/anonvict/py-eye/tests.yml?branch=main&style=flat-square">
  </a>
  <a href="https://www.python.org/downloads/release/python-390/">
    <img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square">
  </a>
  <a href="https://f-droid.org/repo/com.termux.window_15.apk">
    <img alt="Termux Float" src="https://img.shields.io/badge/termux%3Afloat-recomendado-green?style=flat-square">
  </a>
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square">
  </a>
</p>

---

## Por que esse projeto existe

Eu queria algo que deixasse o terminal menos morto. Um personagem simples, mas com personalidade, que reagisse ao ambiente e a você — sem precisar controlar cada expressão manualmente.

O resultado é o `py-eye`: um par de olhos ASCII com emoção, memória, fala e até reação a sensores do celular.

---

## O que ele faz

- **Comportamento autônomo**: não precisa apertar tecla para o personagem reagir. Ele escolhe expressões sozinho baseado em energia, humor, curiosidade, social e irritação.
- **Interpolação fluida**: as expressões não “pulam” de um estado para outro. Tudo se transforma suavemente a 24 FPS.
- **Memória persistente**: ele lembra do que funcionou ou não em `brain.json` e adapta as escolhas com o tempo.
- **Fala em PT-BR**: usa `termux-tts-speak` para falar frases naturais em português brasileiro.
- **Sons sintéticos**: feedback sonoro gerado por `ffmpeg`, sem depender de samples prontos.
- **Sensores opcionais**: proximidade, luz ambiente, acelerômetro e Motoglance.
- **Funciona no Termux normal ou no Termux:Float**: no Float, pode ficar sobreposto em cima de outras telas.

---

## Instalação

```bash
# dependências
apt update
apt install python git play-audio ffmpeg termux-api -y

# clone
git clone https://github.com/anonvict/py-eye.git
cd py-eye

# sons
python tools/sound_cli.py generate-all --volume 0.18

# roda
python eye.py
```

### Atalho rápido

Se você usa Termux:Float, recomendo criar um widget ou alias no `.bashrc`:

```bash
alias py-eye='cd ~/py-eye && python eye.py'
```

---

## Como usar

### Controles

| Tecla | Ação |
|-------|------|
| `q` / `Esc` | Sai |
| Qualquer outra | Estimula o personagem |

Quase qualquer tecla funciona como estímulo. O ideal é usar no **Termux:Float** como se fosse um bichinho virtual na tela.

### Sons

```bash
# todos os sons
python tools/sound_cli.py generate-all

# um som específico
python tools/sound_cli.py generate happy --volume 0.22
```

Se `play-audio` não existir na sua versão do Termux, troque no código por `mpv` ou `aplay`.

---

## Arquitetura rápida

<p align="center">
  <img src="scr/mata-biru.jpg" alt="Preview blue eye" width="320">
</p>

```
Termux/Termux:Float
 └── curses main loop (24 FPS)
      ├── SensorEngine (background thread)
      ├── HabitBrain
      │    ├── drives
      │    ├── personality
      │    └── habits persistence
      └── EyeApp
           ├── pose interpolation
           ├── rounded renderer
           ├── mouth/effects
           └── AudioEngine
                ├── ffmpeg wav
                └── termux-tts-speak
```

Tudo roda no `eye.py` por propósito: o projeto é pequeno, então juntar evita import circular e deixa fácil de editar no celular.

---

## Estrutura do projeto

```
py-eye/
├── eye.py                 # app, engine, renderer, sensores, áudio
├── tools/
│   └── sound_cli.py       # gerador de sons via ffmpeg
├── scr/                   # screenshots e assets visuais
├── sound/
│   ├── robot-notif.wav   # som legado
│   └── generated/        # sons gerados automaticamente
├── docs/
│   ├── ARCHITECTURE.md   # como o código está organizado
│   ├── SENSORS.md        # sensores suportados e limites
│   └── SOUND.md          # sons, TTS e customização
├── requirements.txt
├── pyproject.toml
├── README.md
├── CHANGELOG.md
└── CONTRIBUTING.md
```

---

## Personalidade

Ele não é só um desenho. Tem:

- **curiosity**: quanto ele gosta de investigar coisas novas
- **playfulness**: propensão a ficar happy/giggle
- **patience**: quanto ele aguenta antes de ficar annoyed
- **affection**: tendência a ficar shy/love
- **talkative**: define se ele fala muito ou pouco

E drives que mudam com o tempo:

- **energy**: cai com o tempo, sobe no `sleep`
- **mood**: sobe com estímulo, desce com irritação
- **curiosity**: cresce no tédio, cai quando satisfeita
- **social**: cresce se você ignorar, cai quando interage
- **irritation**: cresce no tédio ou shake, cai no `annoyed`

Esses valores geram scores para cada comportamento. O vencedor é escolhido com amostragem ponderada, com viés de contexto, personalidade e hábitos passados.

---

## Expressões

| Comportamento | O que acontece |
|---------------|----------------|
| `calm` | Respiração suave, estado padrão |
| `observe` | Olhos passeiam devagar pela tela |
| `curious` | Um olho sobe, boca de interrogação |
| `happy` | Olhos apertados, boca aberta |
| `giggle` | Tremedeira rápida, boca animada |
| `surprised` | Olhos grandes, boca de espanto |
| `annoyed` | Olhos semicerrados, cortes diagonais |
| `sleepy` | Olhos caídos, boca de sono |
| `sleep` | Olhos fechados, Zs flutuando |
| `love` | Olhos em formato de coração |
| `confused` | Olhos assimétricos, boca de `?` |
| `dizzy` | Olhos em X, boca de tontura |
| `bored` | Olhos baixos, boca reta |
| `talking` | Boca animada, mais propenso a falar |
| `shy` | Olhos baixos para os lados |
| `smug` | Olhos com cortes, boca confiante |

---

## Notas importantes

- Use **Termux:Float** para a experiência completa. No Float, ele pode ficar sobreposto e parecer um pet de verdade.
- Se aparecer **linha preta no meio dos olhos**, ajuste o zoom do terminal ou mude a fonte/tamanho até sumir. É artefato de canvas pequeno em fontes específicas.
- `brain.json` é criado automaticamente em `~/.local/state/py-eye/`. Pode apagar se quiser resetar a memória.

---

## Roadmap

- Mais expressões
- Integração com relógio/hora do dia
- Novos sons e variações
- Integração com sensores extras
- Integração com widgets Termux

---

## Inspiração

Inspirado no projeto **RoboEyes** do Dennis Hoelscher:
- https://github.com/FluxGarage/RoboEyes

---

## Licença

Esse projeto é licenciado sob a licença MIT — veja [LICENSE](LICENSE) para detalhes.

---

<p align="center">
  Feito com <img src="scr/mata-hijau.jpg" width="18"> e numpy.
</p>
