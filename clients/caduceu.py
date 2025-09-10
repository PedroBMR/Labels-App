import logging
import threading
import time
from pathlib import Path

import pyttsx3
import requests
import yaml
from gpiozero import Button

CONFIG_PATH = Path(__file__).with_name("config.yaml")


def load_config() -> dict:
    """Load connection details from config.yaml."""
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> None:
    config = load_config()
    server = config["server"].rstrip("/")
    token = config["token"]
    device_id = config["device_id"]
    button_pin = config.get("gpio_pin", 17)

    headers = {"Authorization": f"Bearer {token}"}

    try:
        engine = pyttsx3.init()
    except Exception as exc:  # pragma: no cover - depends on system TTS
        logging.error("Não foi possível inicializar o mecanismo de voz: %s", exc)
        engine = None

    try:
        button = Button(button_pin, pull_up=True)
    except Exception as exc:  # pragma: no cover - depends on GPIO hardware
        logging.error("Falha ao inicializar GPIO: %s", exc)
        return

    def send_message() -> None:
        try:
            text = input("Você: ")
        except Exception as exc:
            logging.error("Erro ao ler entrada: %s", exc)
            return

        payload = {"text": text, "source": "caduceu_cozinha", "device_id": device_id}
        try:
            requests.post(
                f"{server}/ideas", json=payload, headers=headers, timeout=10
            ).raise_for_status()
        except requests.RequestException as exc:
            logging.error("Erro de rede ao enviar mensagem: %s", exc)

    button.when_pressed = send_message

    def poll() -> None:
        while True:
            try:
                response = requests.get(
                    f"{server}/ask",
                    params={"device_id": device_id},
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    text = data.get("text")
                    if text and engine is not None:
                        try:
                            engine.say(text)
                            engine.runAndWait()
                        except Exception as exc:  # pragma: no cover
                            logging.error("Erro na síntese de voz: %s", exc)
            except requests.RequestException as exc:
                logging.error("Erro de rede ao buscar respostas: %s", exc)
            time.sleep(2)

    threading.Thread(target=poll, daemon=True).start()
    logging.info("Cliente Caduceu iniciado. Pressione o botão para falar.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Encerrando cliente Caduceu")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    main()
