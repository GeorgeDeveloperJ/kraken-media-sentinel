import logging
import unittest
from json import loads
from unittest.mock import patch
from urllib.error import URLError

from src.config import Config
from src.notifier import Notifier


class NotifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls) -> None:
        logging.disable(logging.NOTSET)

    test_config = Config(
        telegram_bot_token="fake_token_123",
        telegram_chat_id="fake_chat_456",
        discord_webhook_url="https://discord.mock/test",
    )

    @patch("src.notifier.urlopen")
    def test_telegram_success(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.getcode.return_value = 200
        test_notifier = Notifier(self.test_config)

        result = test_notifier.send_telegram(message="test message")
        request = mock_urlopen.call_args[0][0]
        payload = loads(request.data.decode("utf-8"))

        self.assertTrue(result)
        self.assertIn("api.telegram.org", request.full_url)
        self.assertEqual(payload["chat_id"], "fake_chat_456")
        self.assertEqual(payload["parse_mode"], "HTML")

    @patch("src.notifier.urlopen")
    def test_discord_success(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.getcode.return_value = 200
        test_notifier = Notifier(self.test_config)

        result = test_notifier.send_discord(
            title="test title", description="test description", color=0000
        )
        request = mock_urlopen.call_args[0][0]
        payload = loads(request.data.decode("utf-8"))

        self.assertTrue(result)
        self.assertEqual(self.test_config.discord_webhook_url, request.full_url)
        self.assertEqual(payload["embeds"][0]["title"], "test title")
        self.assertEqual(payload["embeds"][0]["description"], "test description")
        self.assertEqual(payload["embeds"][0]["color"], 0000)

    @patch("src.notifier.Request")
    def test_silent_noop_when_not_configured(self, mock_request):
        test_notifier = Notifier(Config())

        result = test_notifier.notify_test("test description")

        self.assertFalse(result["telegram_notification"])
        self.assertFalse(result["discord_notification"])
        mock_request.assert_not_called()

    @patch("src.notifier.urlopen")
    def test_network_error_resilience(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("URL not valid")
        test_notifier = Notifier(self.test_config)

        result = test_notifier.notify_test("test description")

        self.assertFalse(result["telegram_notification"])
        self.assertFalse(result["discord_notification"])
