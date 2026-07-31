# UNI Project - Team Coordination File

**Project**: UNI (Universal AI Platform) - Local Autonomous AI Agent
**Date**: 2026-07-30
**Lead Implementation Engineer**: OpenCode + Nemotron
**MVP Target**: Working demo in 1-2 days

---

## 📋 Current Status: Builds 1-11 COMPLETE

### ✅ Completed Components

| Build | Component | Files | Status |
|-------|-----------|-------|--------|
| 1 | Skeleton + Config | `pyproject.toml`, `config.yaml`, `uni/config.py` | ✅ |
| 2 | Brain Client (LM Studio) | `uni/brain.py` | ✅ |
| 3 | Working Memory (JSON) | `uni/working_memory.py` | ✅ |
| 4 | Capability Registry | `uni/capabilities/registry.py` | ✅ |
| 5a | Speech (Whisper + Piper) | `uni/capabilities/speech.py` | ✅ |
| 5b | Computer (PyAutoGUI + UIA) | `uni/capabilities/computer.py` | ✅ |
| 5c | Browser (Playwright) | `uni/capabilities/browser.py` | ✅ |
| 6a | Vision (VLM via LM Studio) | `uni/capabilities/vision.py` | ✅ |
| 6b | Memory Capability | `uni/capabilities/memory.py` | ✅ |
| 7 | Tool Registry & Executors | `uni/tools/definitions.py`, `executors.py` | ✅ |
| 8 | Event Loop | `uni/event_loop.py` | ✅ |
| 9 | Agent Class | `uni/agent.py` | ✅ |
| 10 | Role Loader | `uni/roles/loader.py`, `roles/assistant.md` | ✅ |
| 11 | CLI Entry | `uni.py` | ✅ |

---

## 🏗️ Architecture Implemented

```
Agent (uni/agent.py)
├── Brain (uni/brain.py) — LM Studio OpenAI-compatible client
├── EventLoop (uni/event_loop.py) — Observe→Think→Speak→Act→Verify
├── WorkingMemory (uni/working_memory.py) — JSON persistence
├── CapabilityRegistry (uni/capabilities/registry.py)
│   ├── SpeechCapability (uni/capabilities/speech.py) — Whisper STT + Piper TTS
│   ├── VisionCapability (uni/capabilities/vision.py) — VLM analysis
│   ├── BrowserCapability (uni/capabilities/browser.py) — Playwright
│   ├── ComputerCapability (uni/capabilities/computer.py) — PyAutoGUI + UIA
│   └── MemoryCapability (uni/capabilities/memory.py) — Memory wrapper
├── ToolExecutor (uni/tools/executors.py) — Dispatches 22 tools
├── RoleLoader (uni/roles/loader.py) — Markdown roles
└── Config (uni/config.py) — Pydantic Settings from config.yaml
```

---

## 🔧 Tool Catalog (22 tools)

| Capability | Tools |
|------------|-------|
| **Browser** (7) | navigate, click_selector, type_selector, extract_text, screenshot, wait_for_selector, get_page_info |
| **Computer** (8) | click, type, press, move, scroll, screenshot_region, focus_window, get_window_list |
| **Speech** (2) | listen, speak |
| **Vision** (3) | analyze_screen, find_element, read_text |
| **Memory** (5) | remember, recall, forget, list_memory, get_context |

---

## 📁 Project Structure

```
/home/dw/code/uni/
├── uni.py                    # CLI entry: python -m uni
├── pyproject.toml            # Package config (name: uni)
├── config.yaml               # All settings
├── roles/
│   └── assistant.md          # Default role (Markdown)
└── uni/
    ├── __init__.py
    ├── agent.py              # Main orchestrator
    ├── brain.py              # LM Studio client
    ├── config.py             # Pydantic Settings
    ├── event_loop.py         # Autonomous cycle
    ├── state.py              # AgentState enum + transitions
    ├── working_memory.py     # JSON persistence
    ├── capabilities/
    │   ├── __init__.py
    │   ├── registry.py       # Capability base + registry
    │   ├── speech.py         # Whisper + Piper
    │   ├── computer.py       # PyAutoGUI + UIA
    │   ├── browser.py        # Playwright
    │   ├── vision.py         # VLM via LM Studio
    │   └── memory.py         # Memory wrapper
    ├── tools/
    │   ├── __init__.py
    │   ├── definitions.py    # 22 tool schemas
    │   └── executors.py      # Dispatch to capabilities
    └── roles/
        └── loader.py         # Markdown parser
```

---

## 🤝 Team Member Requirements

### **ChatGPT — Chief Architect**
**Needs from me**: Final architecture validation, API contracts
**Provides**: High-level design decisions, cross-component integration patterns
**Coordination**: Review Event Loop → Planner integration when Planner is added

### **Claude — Software Architect**
**Needs from me**: Component interfaces, data flow diagrams
**Provides**: Code structure validation, dependency injection patterns
**Coordination**: Verify CapabilityRegistry pattern scales to plugins

### **DeepSeek — Algorithms Engineer**
**Needs from me**: Event Loop algorithm, verification logic, retry/recovery patterns
**Provides**: Planner algorithm, Task Queue design, optimal search strategies
**🔴 URGENT**: Provide **Planner interface spec** — Agent needs `plan(goal, context) → TaskTree`

### **Qwen — Python Module Developer**
**Needs from me**: Capability base classes, tool schema format
**Provides**: Additional capability implementations (Telegram, Discord, Arduino, ComfyUI)
**Coordination**: Follow `Capability` abstract class pattern exactly

### **Gemini — Research Engineer**
**Needs from me**: Vision prompts, VLM benchmark results
**Provides**: Optimal prompts for `find_element`, `read_text`, `analyze_screen`
**Coordination**: Test prompts against actual VLM (llava/qwen-vl) and share results

---

## 🔴 What I Need FROM Team (Blocking)

| Priority | Item | From | Details |
|----------|------|------|---------|
| **CRITICAL** | Planner Interface | DeepSeek | `class Planner: async def plan(goal, context) -> TaskTree` + `replan(failure)` |
| **HIGH** | VLM Prompts | Gemini | Optimized prompts for: element detection, OCR, screen verification |
| **HIGH** | Plugin Architecture | ChatGPT | How external plugins register capabilities without core changes |
| **MEDIUM** | Task Queue Design | DeepSeek | Priority queue, command queuing during execution |
| **MEDIUM** | Human Context Detection | Claude | Idle/away/busy detection for TTS timing |

---

## 🔧 What I Can Provide TO Team

| Item | Location | Description |
|------|----------|-------------|
| Capability Interface | `uni/capabilities/registry.py` | Abstract `Capability` class + `CapabilityRegistry` |
| Tool Schema Format | `uni/tools/definitions.py` | Pydantic models → OpenAI function calling JSON |
| Event Loop Hook Points | `uni/event_loop.py` | Where Planner, TaskQueue, HumanContext integrate |
| Role Format | `roles/assistant.md` | Frontmatter + `## System Prompt` / `## Behavior` / `## Constraints` |
| Config Schema | `uni/config.py` | All settings as Pydantic models |
| Test Commands | Below | Run commands for each component |

---

## 🧪 Test Commands (Run in `/home/dw/code/uni`)

```bash
# Install deps
pip install -e .
playwright install chromium

# Test individual capabilities
python -c "
import asyncio
from uni.capabilities.speech import SpeechCapability
async def t():
    s = SpeechCapability()
    await s.initialize()
    await s.speak('Тест речи')
asyncio.run(t())
"

python -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
async def t():
    c = ComputerCapability()
    print(await c.get_window_list({}))
asyncio.run(t())
"

python -c "
import asyncio
from uni.capabilities.browser import BrowserCapability
async def t():
    b = BrowserCapability(headless=False)
    await b.initialize()
    await b.navigate('https://example.com')
    print(await b.extract_text('body'))
asyncio.run(t())
"

# Full agent test
python -m uni "Открой блокнот и напиши привет"
```

---

## 🎯 Next Builds (12+)

| Build | Component | Owner | Dependencies |
|-------|-----------|-------|--------------|
| 12 | Planner Integration | **DeepSeek** + Me | Planner interface spec |
| 13 | Task Queue | DeepSeek | Planner |
| 14 | Human Context Detection | Claude | Audio/Video input |
| 15 | Plugin System | ChatGPT | CapabilityRegistry extension |
| 16 | Skills/Workflows (Markdown) | Me | Planner + Plugin system |

---

## ⚠️ Known Issues / Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| LM Studio VLM model not loaded | Vision fails | Check `llava` or `qwen-vl` loaded in LM Studio |
| Whisper CPU slow (~3s) | Speech latency | Use `tiny` or `base` model; consider GPU |
| Windows UIA flaky | Window focus fails | PyAutoGUI fallback implemented |
| Playwright detection | Sites block automation | `headless=False`, stealth if needed |
| No Planner yet | Agent can't do multi-step | **Blocking** — needs DeepSeek delivery |

---

## 📝 Integration Contracts

### Planner → Agent
```python
# DeepSeek provides this interface
class Planner:
    async def plan(self, goal: str, context: dict) -> TaskTree: ...
    async def next_step(self, tree: TaskTree, state: dict) -> TaskNode: ...
    async def replan(self, tree: TaskTree, failure: dict) -> TaskTree: ...
```

### Agent → Planner (what I call)
```python
# In event_loop.py _think():
plan = await self.planner.plan(user_goal, observation)
# Then execute steps via tool_executor
```

### Vision Prompts (Gemini provides)
```python
# find_element prompt
"Find {description} in screenshot. Return JSON: {\"x\":int,\"y\":int,\"w\":int,\"h\":int,\"confidence\":float}"

# verify prompt  
"Did {action} succeed? Check screen. Return JSON: {\"success\":bool,\"reason\":\"...\"}"
```

---

## 🚀 Quick Start for New Team Members

```bash
cd /home/dw/code/uni
pip install -e .
playwright install chromium

# Start LM Studio with:
# - qwen2.5-7b-instruct (chat + function calling)
# - llava or qwen-vl (vision) on same port 1234

# Run agent
python -m uni "Открой браузер и зайди на youtube.com"
```

---

## 📞 Contact / Sync

- **Daily Standup**: Sync on Planner interface (DeepSeek) and Vision prompts (Gemini)
- **Architecture Reviews**: ChatGPT + Claude approve new capability patterns
- **Integration Testing**: Me + Qwen test plugin capability registration

---

**Last Updated**: 2026-07-30 by OpenCode (Lead Implementation Engineer)
**Next Review**: After Planner interface delivered