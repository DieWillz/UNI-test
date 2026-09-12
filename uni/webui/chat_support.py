"""Small, side-effect-free validation helpers for the WebUI chat boundary."""
import base64
import binascii
from io import BytesIO
import re

from PIL import Image


def validated_image(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 1_500_000:
        raise ValueError("Изображение должно быть JPEG/PNG/WebP до 1 МБ")
    if not value.startswith("data:"):
        value = "data:image/png;base64," + value
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        raise ValueError("Нужен JPEG, PNG или WebP в base64")
    try:
        raw = base64.b64decode(match[2], validate=True)
        if len(raw) > 1_048_576:
            raise ValueError("Изображение больше 1 МБ")
        with Image.open(BytesIO(raw)) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("Слишком большое разрешение изображения")
            if image.format != {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}[match[1]]:
                raise ValueError("Формат изображения не соответствует содержимому")
            image.verify()
        # This LM Studio build accepts PNG/JPEG but rejects a WebP data URL
        # as "url field must be a base64 encoded image". Convert pixels, not labels.
        if match[1] == "webp":
            with Image.open(BytesIO(raw)) as image:
                image.thumbnail((1600, 1600))
                output = BytesIO()
                image.convert("RGB").save(output, format="PNG")
                return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except (OSError, binascii.Error, Image.DecompressionBombError) as exc:
        raise ValueError("Повреждённое изображение") from exc
    return value


def power_request(text):
    """Parse a direct Dorch power request, including polite timed questions."""
    raw = " ".join(str(text or "").casefold().strip().split())
    if not raw:
        return None
    action_stems = (
        "\u0432\u043a\u043b\u044e\u0447", "\u0432\u044b\u0441\u0442\u0430\u0432", "\u0443\u0441\u0442\u0430\u043d\u043e\u0432",
        "\u043f\u043e\u0441\u0442\u0430\u0432", "\u0437\u0430\u0434\u0430\u0439", "\u0441\u0434\u0435\u043b\u0430\u0439", "\u0434\u0435\u0440\u0436",
    )
    power_stems = ("\u043c\u043e\u0449\u043d\u043e\u0441\u0442", "\u0438\u043d\u0442\u0435\u043d\u0441\u0438\u0432", "\u0441\u043a\u043e\u0440\u043e\u0441\u0442")
    if not (any(stem in raw for stem in action_stems) and (any(stem in raw for stem in power_stems) or "%" in raw)):
        return None
    value_match = re.search(r"([+-]?\d{1,3})\s*%", raw)
    if value_match is None:
        value_match = re.search(
            "(?:\\u043c\\u043e\\u0449\\u043d\\u043e\\u0441\\u0442\\w*|\\u0438\\u043d\\u0442\\u0435\\u043d\\u0441\\u0438\\u0432\\u043d\\u043e\\u0441\\u0442\\w*|\\u0441\\u043a\\u043e\\u0440\\u043e\\u0441\\u0442\\w*)\\s*(?:\\u043d\\u0430\\s*)?([+-]?\\d{1,3})\\b",
            raw,
        )
    if value_match is None:
        return None
    duration_match = re.search(
        "\\b\\u043d\\u0430\\s+(\\d+(?:[.,]\\d+)?)\\s*(?:\\u0441\\u0435\\u043a\\u0443\\u043d\\u0434(?:\\u0443|\\u044b)?|\\u0441\\u0435\\u043a|\\u0441|second(?:s)?)\\b",
        raw,
    )
    return {
        "value": int(value_match.group(1)),
        "duration_seconds": float(duration_match.group(1).replace(",", ".")) if duration_match else None,
    }


def explicit_power(text):
    """Backward-compatible exact power command parser."""
    request = power_request(text)
    if request is not None and request["duration_seconds"] is None:
        return int(request["value"])
    match = re.fullmatch(
        "(?:(?:\\u0432\\u044b\\u0441\\u0442\\u0430\\u0432\\u044c|\\u0443\\u0441\\u0442\\u0430\\u043d\\u043e\\u0432\\u0438|\\u043f\\u043e\\u0441\\u0442\\u0430\\u0432\\u044c|\\u0437\\u0430\\u0434\\u0430\\u0439|\\u0441\\u0434\\u0435\\u043b\\u0430\\u0439)\\s+)?(?:\\u043c\\u043e\\u0449\\u043d\\u043e\\u0441\\u0442\\u044c|\\u0438\\u043d\\u0442\\u0435\\u043d\\u0441\\u0438\\u0432\\u043d\\u043e\\u0441\\u0442\\u044c|\\u0441\\u043a\\u043e\\u0440\\u043e\\u0441\\u0442\\u044c)\\s*(?:\\u043d\\u0430\\s+)?([+-]?\\d+)\\s*%?[.!]?",
        str(text or "").casefold().strip(),
    )
    return int(match[1]) if match else None


def unverified_reply(command, text, actions=None):
    from uni.contracts import TaskOutcome
    outcome = TaskOutcome.finalize(command=command, message=text, actions=actions)
    return {
        "text": text, "audio_url": None, "task_id": outcome.task_id,
        "status": outcome.status.value,
        "verification": outcome.verification.model_dump(mode="json"),
        "outcome": outcome.model_dump(mode="json"),
    }
