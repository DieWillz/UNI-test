"""ВРЕМЕННЫЙ скрипт проверки (НЕ продакшн). Запуск:
PYTHONPATH=C:/LLM/UNI C:/LLM/python312/python.exe _verify_actions.py
Проверяет: движение мыши, клики ЛКМ, drag, поиск в Яндексе (веб+картинки),
открытие XToys (только UI), vision-скриншот, веб-камеру.
Безопасность: XToys не активирует устройство (без toggle/verified_physical).
"""
from __future__ import annotations
import asyncio, base64, sys, traceback
from pathlib import Path
from datetime import datetime

LOG = []
def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s); print(s, flush=True)

async def main():
    import pyautogui
    pyautogui.FAILSAFE = True
    from uni.config import load_config
    from uni.agent import Agent
    from uni.motion import SmoothMouseDriver
    from PIL import Image, ImageGrab

    cfg = load_config()
    agent = Agent(cfg)
    log("== initialize agent ==")
    await agent.initialize()
    caps = agent.capabilities
    w, h = pyautogui.size()
    log(f"screen size: {w}x{h}")

    # 1) Движение мыши (плавно)
    log("\n== 1) Плавное движение мыши ==")
    try:
        drv = SmoothMouseDriver(failsafe=True)
        for (x, y) in [(w//2, h//2), (200, 200), (w-200, h-200), (w//2, 150)]:
            before = pyautogui.position()
            await drv.move_to(x, y, duration=0.8)
            after = pyautogui.position()
            log(f"  move -> ({x},{y}); before={before} after={after} ok={abs(after[0]-x)<5 and abs(after[1]-y)<5}")
    except Exception as e:
        log("  MOUSE ERR:", repr(e))

    # 2) Клики ЛКМ в нескольких местах
    log("\n== 2) Клики ЛКМ ==")
    try:
        for (x, y) in [(w//2, h//2), (300, 300), (w-300, h-300)]:
            pyautogui.click(x, y)
            log(f"  click LMB at ({x},{y}) ok")
            await asyncio.sleep(0.3)
    except Exception as e:
        log("  CLICK ERR:", repr(e))

    # 3) Drag: зажать ЛКМ, вверх 20px, отжать
    log("\n== 3) Drag (зажать ЛКМ, вверх 20px, отжать) ==")
    try:
        sx, sy = w//2, h//2
        pyautogui.moveTo(sx, sy)
        before = pyautogui.position()
        pyautogui.mouseDown()
        pyautogui.move(0, -20, duration=0.4)
        mid = pyautogui.position()
        pyautogui.mouseUp()
        after = pyautogui.position()
        log(f"  drag: before={before} after_release={after} moved_up={before[1]-after[1]}px (ожидалось ~20)")
    except Exception as e:
        log("  DRAG ERR:", repr(e))

    # 4) Яндекс поиск (веб + картинки)
    log("\n== 4) Яндекс: поиск веб и картинки ==")
    browser = caps.get("browser")
    if browser is None:
        log("  browser capability недоступен")
    else:
        try:
            # принудительно через Яндекс
            sess = browser.session
            if hasattr(sess, "search_engine"):
                sess.search_engine = "https://yandex.ru/search/?text={query}"
            if hasattr(sess, "image_search_engine"):
                sess.image_search_engine = "https://yandex.ru/images/search?text={query}"
            r = await browser.search_web("UNI голосовой помощник")
            log(f"  web: {r.message}")
            data = (r.data or {})
            for i, item in enumerate((data.get('results') or [])[:3]):
                log(f"    {i+1}. {item.get('title','')[:60]} -> {item.get('url','')[:70]}")
            r2 = await browser.search_images("котик")
            log(f"  images: {r2.message}")
            data2 = (r2.data or {})
            imgs = data2.get('images') or []
            log(f"    найдено картинок: {len(imgs)}; пример: {imgs[0].get('image_url','')[:70] if imgs else 'нет'}")
        except Exception as e:
            log("  YANDEX ERR:", repr(e))

    # 5) XToys (ТОЛЬКО UI, без активации устройства)
    log("\n== 5) XToys (только UI) ==")
    xtoys = caps.get("xtoys")
    if xtoys is None:
        log("  xtoys capability недоступен")
    else:
        try:
            o = await xtoys.open()
            log(f"  open: {o.message} | url={ (o.data or {}).get('url') }")
            st = await xtoys.get_status()
            log(f"  status: {st.message} | текст:~{(st.data or {}).get('visible_text','')[:120]}")
            # малая интенсивность (UI-слайдер), НЕ выше капа, без verified_physical
            si = await xtoys.set_intensity("", 8)
            log(f"  set_intensity(8): {si.message} | verified_physical={xtoys.verified_physical}")
            ri = await xtoys.read_intensity("")
            log(f"  read_intensity: {ri.message}")
            # вернуть в 0
            await xtoys.set_intensity("", 0)
            log("  intensity возвращена в 0")
        except Exception as e:
            log("  XTOYS ERR:", repr(e))

    # 6) Vision скриншот рабочего стола (сохранить файл)
    log("\n== 6) Vision: скриншот рабочего стола ==")
    try:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = Path(f".uni-logs/verify_desktop_{ts}.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        img = ImageGrab.grab()
        img.save(out, "PNG")
        log(f"  сохранён скриншот: {out} ({img.size})")
        # попытка анализа через vision (если gradio/openai доступен)
        vision = caps.get("vision")
        if vision is not None:
            try:
                an = await vision.analyze_screen("Кратко опиши что видно на экране.")
                log(f"  analyze: {an.message} | {(an.data or {}).get('analysis','')[:200]}")
            except Exception as e:
                log(f"  analyze недоступен (локальный gradio/model не запущен?): {repr(e)[:160]}")
    except Exception as e:
        log("  VISION ERR:", repr(e))

    # 7) Веб-камера (гейт notice_ack соблюдён программно)
    log("\n== 7) Веб-камера ==")
    camera = caps.get("camera")
    if camera is None:
        log("  camera capability недоступен")
    else:
        try:
            ns = await camera.start(notice_ack=True)
            log(f"  start(notice_ack=True): success={getattr(ns,'success',ns)}")
            cap = await camera.capture_base64_frame()
            if getattr(cap, "success", False):
                b64 = (cap.data or {}).get("image_b64", "")
                raw = base64.b64decode(b64.split(",", 1)[1])
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                out = Path(f".uni-logs/verify_camera_{ts}.png")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(raw)
                log(f"  кадр получен и сохранён: {out} ({len(raw)} bytes)")
            else:
                log(f"  capture не удался: {getattr(cap,'message','')}")
            await camera.stop()
            log("  camera stop ok")
        except Exception as e:
            log("  CAMERA ERR (возможно не подключена):", repr(e))

    log("\n== ГОТОВО ==")
    await agent.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
    finally:
        Path("_verify_actions.log").write_text("\n".join(LOG), encoding="utf-8")
        print("LOG written to _verify_actions.log")
