# Arquitetura do py-eye

Esse documento explica como o projeto está organizado por dentro, sem enrolação. Serve tanto para quem quer entender o código quanto para quem quer contribuir sem quebrar nada.

## Visão geral

O `py-eye` roda em uma única thread de terminal usando `curses`, mas divide a responsabilidade em três blocos principais:

- `SensorEngine`: lê sensores do Termux em background.
- `HabitBrain`: decide qual comportamento executar agora.
- `EyeApp + AudioEngine`: desenha a cena e toca sons/falas.

```
Termux/Termux:Float
 └── curses main loop
      ├── SensorEngine (background thread)
      ├── HabitBrain
      └── EyeApp
            ├── pose interpolation
            ├── renderer
            └── AudioEngine
```

## eye.py

O arquivo principal não é apenas um script de desenho. Ele carrega todo o comportamento:

- Loop principal a 24 FPS usando `time.sleep` para controle de frame.
- Interpolação exponencial entre poses alvo, o que deixa a animação fluida.
- Sistema de drives (`energy`, `mood`, `curiosity`, `social`, `irritation`) que evoluem com o tempo.
- Personalidade fixa (`curiosity`, `playfulness`, `patience`, `affection`, `talkative`) que influencia as escolhas.
- Hábitos persistidos em `~/.local/state/py-eye/brain.json`, separados por contexto.
- Seleção de comportamento via scoring + softmax, com viés por sensores.

### Estados relevantes

- `idle`: tempo sem estímulo.
- `stimulated`: true após tecla, proximidade, shake ou Motoglance.
- `behavior`: nome da expressão atual.
- `behavior_duration`: quanto tempo essa expressão vai durar.

### Render

Cada frame:
1. Calcula `target` pela expressão atual.
2. Aplica interpolação exponencial para `pose`.
3. Desenha canvas 58x17 com olhos arredondados e boca.
4. Escreve no centro do terminal usando `curses.addstr`.

## tools/sound_cli.py

Gera sons `.wav` sintéticos com `ffmpeg`. Não depende de biblioteca de áudio extra no Python, porque delega toda a filtragem para o `ffmpeg`.

Cada som é uma sequência de frequências e durações. O comando principal:

```bash
python tools/sound_cli.py generate-all --volume 0.18
```

Saída: `sound/generated/<nome>.wav`

## Estrutura de arquivos

```
py-eye/
├── eye.py                # app principal, engine, renderer, sensores, áudio
├── tools/
│   └── sound_cli.py     # gerador de sons via ffmpeg
├── scr/                  # prints e assets visuais
├── sound/
│   ├── robot-notif.wav  # som legado de notificação
│   └── generated/       # sons gerados automaticamente
├── requirements.txt
├── pyproject.toml
├── README.md
└── docs/
    ├── ARCHITECTURE.md
    ├── SENSORS.md
    └── SOUND.md
```

## Convenções

- Não use bibliotecas pesadas. O projeto usa só `numpy`.
- Toda nova expressão deve ter entrada em `BEHAVIORS`, `PT_BR_DIALOG`, `pose_for` e `render_mouth`.
- Sons opcionais: se não existir o `.wav`, o app continua funcionando.
- Sensores opcionais: se `termux-sensor` não estiver instalado, o app roda sem percepção física.
