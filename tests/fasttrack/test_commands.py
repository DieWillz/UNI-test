import unittest

from uni.config import Config
from uni.event_loop import EventLoop


class DirectCommandTests(unittest.TestCase):
    def test_user_facing_answer_is_bounded_and_style_token_removed(self):
        loop = object.__new__(EventLoop)
        loop.config = Config()
        answer = loop._clean_answer(
            "stile=dominant\nПервое предложение. Второе предложение. "
            "Третье предложение. Четвёртое предложение, которое не должно звучать."
        )
        self.assertNotIn("stile=", answer)
        self.assertIn("Третье предложение.", answer)
        self.assertNotIn("Четвёртое", answer)

    def test_common_xtoys_transcription_variants_open_canonical_site(self):
        for phrase in ("Открывай x-twice", "Открой x2", "Открой Xpress.app"):
            with self.subTest(phrase=phrase):
                command = EventLoop.parse_direct_command(phrase)
                self.assertIsNotNone(command)
                self.assertEqual(command.action, "xtoys.open")

    def test_xtoys_commands(self):
        self.assertEqual(EventLoop.parse_direct_command("открой XToys").action, "xtoys.open")
        self.assertEqual(EventLoop.parse_direct_command("Открой Xtois").action, "xtoys.open")
        self.assertEqual(EventLoop.parse_direct_command("открой икс тойс").action, "xtoys.open")
        command = EventLoop.parse_direct_command("интенсивность 25")
        self.assertEqual(command.action, "xtoys.set_intensity")
        self.assertEqual(command.args, {"value": 25})
        speed = EventLoop.parse_direct_command("сделай скорость 5")
        self.assertEqual(speed.action, "xtoys.set_intensity")
        self.assertEqual(speed.args, {"value": 5})
        missing = EventLoop.parse_direct_command("попробуй изменить интенсивность")
        self.assertEqual(missing.action, "internal.response")
        retry = EventLoop.parse_direct_command("ничего не меняется, не работает")
        self.assertEqual(retry.action, "internal.retry_intensity_visual")
        self.assertEqual(EventLoop.parse_direct_command("паттерн wave").action, "xtoys.select_pattern")
        self.assertEqual(EventLoop.parse_direct_command("выключи игрушку").args, {"value": 0})
        self.assertEqual(EventLoop.parse_direct_command("подключи игрушку").action, "xtoys.toggle")

    def test_browser_and_vision_commands(self):
        search = EventLoop.parse_direct_command("найди в интернете новости ИИ")
        self.assertEqual(search.action, "browser.search_web")
        self.assertEqual(search.args["query"], "новости ИИ")
        self.assertEqual(EventLoop.parse_direct_command("открой сайт example.com").action, "browser.navigate")
        self.assertEqual(EventLoop.parse_direct_command("что на вкладке").action, "vision.analyze_screen")
        self.assertEqual(
            EventLoop.parse_direct_command("посмотри на экран и скажи что ты видишь").action,
            "vision.analyze_screen",
        )
        self.assertEqual(EventLoop.parse_direct_command("сделай скриншот").action, "browser.save_screenshot")
        images = EventLoop.parse_direct_command("найди среди картинок самые крупные породы собак")
        self.assertEqual(images.action, "browser.search_images")
        self.assertEqual(images.args["query"], "самые крупные породы собак")
        explore = EventLoop.parse_direct_command("полёт фантазии про гигантских собак")
        self.assertEqual(explore.action, "internal.explore")
        self.assertEqual(explore.args["topic"], "гигантских собак")
        message = EventLoop.parse_direct_command("напиши Асе: Привет, буду рад тебя увидеть")
        self.assertEqual(message.action, "internal.draft_message")
        self.assertEqual(message.args["contact"], "Ася")
        self.assertEqual(EventLoop.parse_direct_command("да, отправь").action, "internal.confirm_send")

    def test_camera_commands(self):
        self.assertEqual(
            EventLoop.parse_direct_command("посмотри через камеру").action,
            "internal.camera_look",
        )
        self.assertEqual(EventLoop.parse_direct_command("запусти камеру").action, "internal.camera_look")
        self.assertEqual(EventLoop.parse_direct_command("включи камеру").action, "internal.camera_look")
        watch = EventLoop.parse_direct_command("смотри через камеру 45 минут")
        self.assertEqual(watch.action, "internal.camera_watch")
        self.assertEqual(watch.args["seconds"], 2700)
        half_hour = EventLoop.parse_direct_command("наблюдай через камеру полчаса")
        self.assertEqual(half_hour.args["seconds"], 1800)
        self.assertEqual(
            EventLoop.parse_direct_command("перестань смотреть в камеру").action,
            "internal.camera_stop",
        )

    def test_audio_message_commands(self):
        wav = EventLoop.parse_direct_command("запиши голосовое: Привет, это Юни")
        self.assertEqual(wav.action, "internal.create_audio_message")
        self.assertEqual(wav.args, {"text": "Привет, это Юни", "format": "wav"})
        mp3 = EventLoop.parse_direct_command("создай аудиопослание mp3: Добрый вечер")
        self.assertEqual(mp3.args, {"text": "Добрый вечер", "format": "mp3"})

    def test_stop_is_emergency_zero_not_program_exit(self):
        for phrase in ("стоп", "красный", "остановись", "аварийный стоп"):
            command = EventLoop.parse_direct_command(phrase)
            self.assertEqual(command.action, "xtoys.set_intensity")
            self.assertEqual(command.args, {"value": 0})
            self.assertFalse(EventLoop.is_stop_command(phrase))
        self.assertTrue(EventLoop.is_stop_command("выход"))
