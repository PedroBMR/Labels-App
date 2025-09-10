# Caduceu client

Pequeno utilitário que envia mensagens ao servidor e reproduz respostas por voz.

## Configuração

1. Instale as dependências:

```bash
pip install gpiozero pyttsx3 pyyaml requests
```

2. Crie um arquivo `config.yaml` ao lado de `caduceu.py`:

```yaml
server: "https://exemplo.com"   # endereço da API
token: "seu_token_aqui"         # token Bearer
device_id: "cozinha"           # identificador deste dispositivo
gpio_pin: 17                    # GPIO para o botão (BCM 17 = pino físico 11)
```

Conecte um botão normalmente aberto entre o **GPIO 17** e o **GND**.

## Uso

Execute o cliente:

```bash
python caduceu.py
```

Aperte o botão para digitar ou falar a mensagem. O servidor retorna a resposta
em `/ask` e o módulo `pyttsx3` sintetiza o áudio localmente.
