import logging
from json import dumps
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config import Config

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: Config) -> None:
        self.config = config

    def send_telegram(self, message: str) -> bool:
        """Sends HTML formatted message to Telegram if credentials exist."""

        token, chat_id = self.config.telegram_bot_token, self.config.telegram_chat_id

        if not token or not chat_id:
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        try:
            data_bytes = dumps(payload).encode("utf-8")

            request = Request(url, data=data_bytes, method="POST")
            request.add_header("Content-Type", "application/json; charset=utf-8")

            with urlopen(request, timeout=10) as response:
                return response.getcode() == 200

        except (HTTPError, URLError) as e:
            logger.error("Error while sending telegram message: %s", e)
            return False

    def send_discord(self, title: str, description: str, color: int) -> bool:
        """Sends embed to Discord Webhook if URL exist."""

        url = self.config.discord_webhook_url

        if not url:
            return False

        payload = {
            "embeds": [{"title": title, "description": description, "color": color}]
        }

        try:
            data_bytes = dumps(payload).encode("utf-8")
            request = Request(url, data=data_bytes, method="POST")
            request.add_header("Content-Type", "application/json")
            request.add_header(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )

            with urlopen(request, timeout=10) as response:
                return response.getcode() in (200, 204)

        except (HTTPError, URLError) as e:
            logger.error("Error while sending discord message: %s", e)
            return False

    def notify_critical(
        self, message: str = "Drive unmounted and failed 3 recovery attempts"
    ) -> None:
        """Broadcasts critical failure to all configured channels."""

        self.send_telegram(f"<b>[CRITICAL]</b> {message}")
        self.send_discord(
            title="🚨 Kraken Media Storage: CRITICAL",
            description=message,
            color=15158332,
        )

    def notify_recovery(
        self, message: str = "Storage successfully remounted and Docker resumed"
    ) -> None:
        """Broadcasts succesfull mount recovery to all configured channels."""

        self.send_telegram(f"<b>[RECOVERY]</b> {message}")
        self.send_discord(
            title="💚 Kraken Media Storage: Recovered",
            description=message,
            color=3066993,
        )

    def notify_test(self, message: str) -> dict[str, bool]:
        """Send test messages to verify configured channels."""

        telegram = self.send_telegram("<b>[TEST]</b> Kraken Media Mount Testing...")
        discord = self.send_discord(
            title="🧪 Kraken Media Storage: Test",
            description="Drive media test",
            color=3447003,
        )

        return {"telegram_notification": telegram, "discord_notification": discord}
