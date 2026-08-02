import pytest
import pytest_asyncio
from app.telegram_bot.bot import TelegramBotV3Handler, bot_handler, BOT_TOKEN, WEBAPP_URL, ALLOWED_COMMANDS


class TestTelegramBotSuite:
    """Comprehensive test suite for Phase 3 Telegram Bot v3 handlers and validation logic."""

    def test_bot_initialization_defaults(self):
        """Verify TelegramBotV3Handler default token and WebApp URL initialization."""
        bot = TelegramBotV3Handler()
        assert bot.token == BOT_TOKEN
        assert bot.webapp_url == WEBAPP_URL

    def test_bot_initialization_custom(self):
        """Verify custom token and WebApp URL configuration."""
        custom_token = "123456:ABC-DEF1234ghIkl-zyx57ABc"
        custom_url = "https://ai-coach.ru/pwa"
        bot = TelegramBotV3Handler(token=custom_token, webapp_url=custom_url)
        assert bot.token == custom_token
        assert bot.webapp_url == custom_url

    def test_validate_command_valid_cases(self):
        """Verify command validation accepts all supported bot commands."""
        bot = TelegramBotV3Handler()
        for cmd in ALLOWED_COMMANDS:
            assert bot.validate_command(cmd) is True, f"Command {cmd} should be valid"
            assert bot.validate_command(f"{cmd} extra_arg") is True, f"Command {cmd} with args should be valid"
            assert bot.validate_command(f"  {cmd.upper()}  ") is True, f"Command uppercase {cmd} should be valid"

    def test_validate_command_invalid_cases(self):
        """Verify command validation rejects invalid or unsupported commands."""
        bot = TelegramBotV3Handler()
        invalid_inputs = [
            "/unknown",
            "/hack",
            "/delete_all",
            "hello bot",
            "",
            None,
            12345
        ]
        for invalid in invalid_inputs:
            assert bot.validate_command(invalid) is False, f"Input {invalid} should be invalid"

    def test_validate_webapp_url_valid(self):
        """Verify WebApp URL validation for valid HTTP and HTTPS schemes."""
        bot = TelegramBotV3Handler()
        valid_urls = [
            "http://localhost:8000/pwa",
            "https://ai-coach-v7.ru/pwa",
            "https://subdomain.domain.org/app/checkin?user=123"
        ]
        for url in valid_urls:
            assert bot.validate_webapp_url(url) is True, f"URL {url} should be valid"

    def test_validate_webapp_url_invalid(self):
        """Verify WebApp URL validation for invalid schemes or empty values."""
        bot = TelegramBotV3Handler()
        invalid_urls = [
            "ftp://files.example.com",
            "javascript:alert(1)",
            "not_a_url",
            ""
        ]
        for url in invalid_urls:
            assert bot.validate_webapp_url(url) is False, f"URL {url} should be invalid"

        invalid_bot = TelegramBotV3Handler(webapp_url="invalid_scheme://test")
        assert invalid_bot.validate_webapp_url() is False

    @pytest.mark.asyncio
    async def test_handle_start_command(self):
        """Verify /start handler response payload, 323-FZ disclaimer, and inline keyboard WebApp link."""
        bot = TelegramBotV3Handler(webapp_url="https://test.ai-coach.ru/pwa")
        res = await bot.handle_start(user_id=1001, username="alexey_runner")

        assert "text" in res
        assert "alexey_runner" in res["text"]
        assert "323-ФЗ" in res["text"]  # Medical disclaimer check
        assert "AI Adaptive Coach v7." in res["text"]
        assert res["status"] == "success"

        # Verify inline keyboard with WebAppInfo
        markup = res.get("reply_markup", {})
        assert "inline_keyboard" in markup
        keyboard = markup["inline_keyboard"]
        assert len(keyboard) >= 1
        webapp_button = keyboard[0][0]
        assert "web_app" in webapp_button
        assert webapp_button["web_app"]["url"] == "https://test.ai-coach.ru/pwa"

    @pytest.mark.asyncio
    async def test_handle_checkin_command(self):
        """Verify /checkin handler response and Telegram Mini App launch button."""
        bot = TelegramBotV3Handler(webapp_url="http://localhost:8000/pwa")
        res = await bot.handle_checkin(user_id=1001)

        assert "text" in res
        assert "Daily Check-in" in res["text"]
        assert res["status"] == "success"

        markup = res.get("reply_markup", {})
        assert "inline_keyboard" in markup
        webapp_button = markup["inline_keyboard"][0][0]
        assert webapp_button["web_app"]["url"] == "http://localhost:8000/pwa"

    @pytest.mark.asyncio
    async def test_handle_workout_command(self):
        """Verify /workout handler returning today's workout plan with WebApp button."""
        bot = TelegramBotV3Handler()
        res = await bot.handle_workout(user_id=1001)

        assert "text" in res
        assert "Сегодняшняя тренировка" in res["text"]
        assert "Индекс готовности R_i" in res["text"]
        assert res["status"] == "success"

        markup = res.get("reply_markup", {})
        assert "inline_keyboard" in markup
        assert len(markup["inline_keyboard"]) >= 1

    @pytest.mark.asyncio
    async def test_handle_stats_command(self):
        """Verify /stats handler returning athlete HRV biometrics and Z-Score status."""
        bot = TelegramBotV3Handler()
        res = await bot.handle_stats(user_id=1001)

        assert "text" in res
        assert "HRV" in res["text"]
        assert "ACWR" in res["text"]
        assert res["status"] == "success"

    @pytest.mark.asyncio
    async def test_handle_sync_command(self):
        """Verify /sync handler status for wearable data updates."""
        bot = TelegramBotV3Handler()
        res = await bot.handle_sync(user_id=1001)

        assert res["status"] == "synced"
        assert "Garmin" in res["text"] or "Wearable" in res["text"]

    @pytest.mark.asyncio
    async def test_handle_help_command(self):
        """Verify /help handler listing all available bot commands."""
        bot = TelegramBotV3Handler()
        res = await bot.handle_help(user_id=1001)

        assert "text" in res
        for cmd in ["/start", "/checkin", "/workout", "/stats", "/sync", "/redflag", "/help"]:
            assert cmd in res["text"]

    @pytest.mark.asyncio
    async def test_handle_redflag_emergency_command(self):
        """Verify Emergency Red Flag trigger returns Level 1 HARD_LOCK status and safety warning."""
        bot = TelegramBotV3Handler()
        symptom = "Боль в груди при нагрузке"
        res = await bot.handle_redflag_emergency(user_id=1001, symptom=symptom)

        assert res["status"] == "HARD_LOCK"
        assert symptom in res["text"]
        assert "LEVEL 1 EMERGENCY" in res["text"]
        assert "112" in res["text"]

    def test_global_bot_instance_singleton(self):
        """Verify global bot_handler instance is correctly configured."""
        assert bot_handler is not None
        assert isinstance(bot_handler, TelegramBotV3Handler)
