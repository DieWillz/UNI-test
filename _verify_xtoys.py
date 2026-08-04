"""ВРЕМЕННЫЙ: изолированная проверка XToys (сразу после initialize, без поиска)."""
import asyncio, traceback
from pathlib import Path
LOG=[]
def log(*a): s=" ".join(map(str,a)); LOG.append(s); print(s, flush=True)
async def main():
    from uni.config import load_config
    from uni.agent import Agent
    cfg = load_config()
    agent = Agent(cfg)
    log("init...")
    await agent.initialize()
    xtoys = agent.capabilities.get("xtoys")
    if xtoys is None:
        log("xtoys capability недоступен"); await agent.shutdown(); return
    try:
        o = await xtoys.open()
        log(f"open: success={o.success} msg={o.message} url={(o.data or {}).get('url')}")
        st = await xtoys.get_status()
        log(f"status: {st.message} | {(st.data or {}).get('visible_text','')[:150]}")
        si = await xtoys.set_intensity("", 8)
        log(f"set_intensity(8): {si.message} verified_physical={xtoys.verified_physical}")
        ri = await xtoys.read_intensity("")
        log(f"read_intensity: {ri.message}")
        await xtoys.set_intensity("", 0)
        log("intensity -> 0")
    except Exception as e:
        log("XTOYS ERR:", repr(e))
    await agent.shutdown()
if __name__ == "__main__":
    try: asyncio.run(main())
    except Exception: traceback.print_exc()
    finally:
        Path("_verify_xtoys.log").write_text("\n".join(LOG), encoding="utf-8")
