# Som no py-eye

O projeto usa duas camadas de áudio: sons curtos de feedback e falas eventuais.

## Sons sintéticos

Gerados via `ffmpeg` usando osciladores senoidais. Vantagem: sem dependência de samples externos.

```bash
python tools/sound_cli.py generate-all --volume 0.18
```

Os arquivos ficam em `sound/generated/*.wav`. Em runtime, o `AudioEngine` prioriza os sons gerados e cai para `sound/robot-notif.wav` se não encontrar o específico.

## Falas

Usa `termux-tts-speak` com parâmetros afinados para PT-BR:

```bash
termux-tts-speak -l pt -n BR -p 0.92 -r 0.86 -s MUSIC "Oi, eu tô acordado."
```

A chance de falar depende da personalidade `talkative` e do cooldown. Expressões mais sociais (`talking`, `happy`, `love`) têm mais chance de falar.

## Requisitos

```bash
apt install termux-api ffmpeg play-audio -y
```

Se `play-audio` não estiver disponível na sua versão do Termux, use `mpv` ou `aplay` e altere a detecção no código.

## Customização

Para adicionar uma nova expressão com som:

1. Adicione a entrada em `tools/sound_cli.py` em `SOUNDS`.
2. Rode `generate-all` ou `generate <nome>`.
3. Adicione frases em `PT_BR_DIALOG[behavior]` se quiser fala.
