# Sensores no py-eye

A integração com sensores é opcional, mas muda bastante a personalidade do personagem. O app detecta ausência de `termux-sensor` e segue funcionando normalmente.

## Sensores suportados

### Proximidade: `ltr569_ps`
- Raw value <= 6 → algo/pessoa está perto.
- Efeito: estimula o comportamento como se alguém tivesse encostado no aparelho.
- Aumenta `social` drop, sobe `mood` e reduz `irritation`.

### Luz ambiente: `ltr569_als`
- <= 5 lux → ambiente escuro.
- >= 80 lux → ambiente muito claro.
- Efeito no escuro: aumenta sono, drena energia mais rápido.
- Efeito no claro: curiosity up, mood levemente positivo.

### Acelerômetro: `lsm6dsv_acc`
- Mede delta de aceleração entre leituras.
- Magnitude > 3.5 m/s² → consideramos "shake".
- Efeito: surprised, dizzy, irritation spike.

### Motoglance: `Motoglance`
- Dispara quando o usuário levanta o aparelho para olhar.
- Efeito: acorda do sono, sobe social/energy/mood.
- Janela de ~3s após o evento.

## Como usar

```bash
apt install termux-api -y
termux-sensor -s ltr569_ps -n 1
termux-sensor -s ltr569_als -n 1
termux-sensor -s lsm6dsv_acc -n 1
termux-sensor -s Motoglance -n 1
```

O `SensorEngine` faz polling automático a cada 1.2s em thread separada. Não bloqueia a animação.

## Personalização

Você pode ajustar os limites diretamente no código:

```python
SensorEngine.PROX_NEAR_THRESHOLD = 6
SensorEngine.LIGHT_DIM_THRESHOLD = 5
SensorEngine.LIGHT_BRIGHT_THRESHOLD = 80
SensorEngine.MOTION_THRESHOLD = 3.5
```

Se o seu hardware usar sensores diferentes, basta alterar os nomes passados para `termux-sensor`.
