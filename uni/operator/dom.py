"""Bounded, untrusted DOM observations in the existing BrowserSession.

Refs are identities retained in a private page handle, never model selectors.
Only the most recent observation may be acted on. No action verifies a mission.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

if TYPE_CHECKING:
    from uni.browser_session import BrowserSession


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StaleDOMRef(ValueError):
    def __init__(self) -> None:
        super().__init__("stale_ref")


# A closure-owned handle avoids publishing ref identities as page attributes.
# Selectors below are fixed adapter implementation, never supplied by a model.
_CAPTURE = r"""({snapshotId, limit, scope, previous, filter}) => {
    let generation = 0;
    const bump = () => { generation++; };
    const observer = new MutationObserver(bump);
    const events = ['resize', 'hashchange', 'popstate'];
    const windowFocus = event => { if (event.target === window) bump(); };
    const text = value => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 600);
    const visible = el => {
        const style = getComputedStyle(el), box = el.getBoundingClientRect();
        return el.isConnected && !el.closest('[hidden],[inert],[aria-hidden="true"]') &&
            style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0 &&
            box.width > 0 && box.height > 0 && box.bottom > 0 && box.right > 0 &&
            box.top < innerHeight && box.left < innerWidth;
    };
    const roleOf = el => {
        const explicit = text(el.getAttribute('role')).split(' ')[0];
        if (explicit) return explicit;
        const tag = el.tagName.toLowerCase(), type = (el.type || '').toLowerCase();
        if (tag === 'a' && el.hasAttribute('href')) return 'link';
        if (tag === 'button' || (tag === 'input' && ['button','submit','reset'].includes(type))) return 'button';
        if (tag === 'input') return ({checkbox:'checkbox', radio:'radio', range:'slider', number:'spinbutton',
            file:'file', search:'searchbox', hidden:'none'})[type] || 'textbox';
        if (tag === 'textarea' || el.isContentEditable) return 'textbox';
        if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
        if (/^h[1-6]$/.test(tag)) return 'heading';
        return ({img:'img',summary:'button',progress:'progressbar',option:'option',dialog:'dialog',
            main:'main',nav:'navigation',section:'region',form:'form',fieldset:'group'})[tag] || 'text';
    };
    const describe = el => {
        const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
        const labelled = text(ids.map(id => document.getElementById(id)?.textContent || '').join(' '));
        const labels = text(Array.from(el.labels || []).map(label => label.textContent || '').join(' '));
        const body = text(el.innerText || el.textContent);
        const name = labelled || text(el.getAttribute('aria-label')) || labels ||
            text(el.getAttribute('alt')) || text(el.getAttribute('title')) ||
            (['button','submit','reset'].includes(el.type) ? text(el.value) : '') ||
            text(el.getAttribute('placeholder')) || body;
        const box = el.getBoundingClientRect(), checked = el.getAttribute('aria-checked');
        const sensitive = el.type === 'password';
        return {role:roleOf(el), name, text:body,
            bbox:[box.x,box.y,box.width,box.height].map(v => Math.round(v * 10) / 10),
            enabled:!el.matches(':disabled') && !el.closest('[inert],[aria-disabled="true"]'),
            value:sensitive ? null : ('value' in el ? String(el.value).slice(0,2000) :
                el.isContentEditable ? text(el.innerText) : null),
            checked:typeof el.checked === 'boolean' ? el.checked :
                checked === 'true' ? true : checked === 'false' ? false : null,
            metadata:{tag:el.tagName.toLowerCase(), input_type:el.type || null,
                href:el.tagName === 'A' ? el.href : null, sensitive, untrusted:true,
                frame:'main', coordinate_space:'css_viewport', visible:true,
                in_dialog:!!el.closest('dialog[open],[role="dialog"],[role="alertdialog"]'),
                scope_names:Array.from((function*(node) { while (node) { yield node; node=node.parentElement; } })(el))
                    .map(node => text(node.getAttribute('aria-label'))).filter(Boolean).slice(0,8)}};
    };
    const identity = (el, activationChecked) => {
        const item = describe(el);
        if (typeof activationChecked === 'boolean') item.checked = activationChecked;
        return JSON.stringify([item, el.getAttribute('id'), el.getAttribute('name'),
            el.getAttribute('href'), el.getAttribute('type')]);
    };
    const selector = 'a[href],button,input,textarea,select,summary,[role],[contenteditable="true"],'+
        'h1,h2,h3,h4,h5,h6,p,li,label,img,output,progress,dialog,main,nav,section,form,fieldset,[tabindex]';
    const candidates = [], walker = document.createTreeWalker(document, NodeFilter.SHOW_ELEMENT);
    let scanned = 0, next;
    while ((next = walker.nextNode()) && scanned < 5000) {
        scanned++;
        if (next.matches(selector)) candidates.push(next);
    }
    let root = document;
    if (scope?.ref) {
        if (!previous) throw Error('stale_ref');
        root = previous.validate(scope);
    } else if (scope && (scope.role || scope.name)) {
        const matches = candidates.filter(el => visible(el) && (!scope.role || roleOf(el) === scope.role) &&
            (!scope.name || describe(el).name === scope.name));
        if (matches.length !== 1) throw Error(matches.length ? 'scope_ambiguous' : 'scope_not_found');
        root = matches[0];
    }
    observer.observe(document, {subtree:true, childList:true, attributes:true, characterData:true});
    for (const event of events) window.addEventListener(event, bump, true);
    window.addEventListener('focus', windowFocus, true);
    window.addEventListener('blur', windowFocus, true);
    const controls = new Set(['link','button','textbox','searchbox','checkbox','radio','slider','spinbutton',
        'file','listbox','combobox','switch','menuitem','tab']);
    candidates.sort((a,b) => Number(controls.has(roleOf(b))) - Number(controls.has(roleOf(a))));
    const refs = new Map(), elements = [];
    let matched = 0;
    for (const el of candidates) {
        if (!root.contains(el) || !visible(el)) continue;
        const item = describe(el);
        if (item.role === 'none' || (item.role === 'text' && !item.name)) continue;
        if (filter && ((filter.role && item.role !== filter.role) ||
            (filter.name && item.name !== filter.name) ||
            (filter.query && !(item.name + ' ' + item.text).toLowerCase().includes(filter.query.toLowerCase())))) continue;
        matched++;
        if (elements.length >= limit) continue;
        const ref = 'e' + (elements.length + 1);
        refs.set(ref, {node:el, fingerprint:identity(el), checked:item.checked});
        elements.push({ref, source:'dom', confidence:1.0, ...item});
    }
    const capturedGeneration = generation, capturedUrl = location.href;
    const validateSnapshot = snapshot_id => {
        if (observer.takeRecords().length) bump();
        if (snapshot_id !== snapshotId || generation !== capturedGeneration || location.href !== capturedUrl)
            throw Error('stale_ref');
    };
    const validate = ({ref, snapshot_id}, checkboxActivation = false) => {
        validateSnapshot(snapshot_id);
        const entry = refs.get(ref);
        if (!entry || !visible(entry.node) ||
            identity(entry.node, checkboxActivation ? entry.checked : undefined) !== entry.fingerprint) throw Error('stale_ref');
        return entry.node;
    };
    let guard = null;
    const guardEvents = ['pointerdown','mousedown','click','keydown','beforeinput'];
    const stopGuard = () => {
        const blocked = !!guard?.blocked;
        if (guard) for (const event of guardEvents) window.removeEventListener(event, guard.listener, true);
        guard = null;
        return blocked;
    };
    const armGuard = args => {
        stopGuard();
        const node = validate(args);
        guard = {blocked:false, listener:event => {
            try {
                // HTML checkbox/radio pre-activation changes checked before the
                // trusted click capture phase; all other identity fields stay exact.
                validate(args, event.type === 'click' &&
                    node.matches('input[type="checkbox"],input[type="radio"]'));
                if (event.target !== node && !node.contains(event.target)) throw Error('stale_ref');
            } catch (_) {
                guard.blocked = true;
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        }};
        for (const event of guardEvents) window.addEventListener(event, guard.listener, true);
    };
    return {
        snapshotId, elements, complete:!next, truncated:matched > limit,
        activeDialog:candidates.some(el => visible(el) && el.matches('dialog[open],[role="dialog"],[role="alertdialog"]')),
        validate, validateSnapshot, armGuard, stopGuard,
        observe: args => describe(validate(args)),
        dispose: () => {
            stopGuard();
            observer.disconnect();
            for (const event of events) window.removeEventListener(event, bump, true);
            window.removeEventListener('focus', windowFocus, true);
            window.removeEventListener('blur', windowFocus, true);
            refs.clear();
        }
    };
}"""


class DOMOperator:
    """The session owns this adapter and its lock; observations never start it."""

    def __init__(self, session: BrowserSession) -> None:
        self.session = session
        self._handle = None
        self._snapshot: dict[str, Any] | None = None
        self._page = None
        self._epoch = -1

    async def _discard(self) -> None:
        handle, self._handle = self._handle, None
        self._snapshot = None
        if handle is not None:
            try:
                await handle.evaluate("state => state.dispose()")
            except Exception:
                pass  # Navigation destroys the previous execution context.
            try:
                await handle.dispose()
            except Exception:
                pass

    async def find(self, *, query: str = "", role: str = "", name: str = "",
                   scope: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        return await self.inspect(limit=limit, scope=scope,
                                  _filter={"query": query, "role": role, "name": name})

    async def inspect(self, *, limit: int = 100, scope: dict[str, Any] | None = None,
                      _filter: dict[str, str] | None = None) -> dict[str, Any]:
        async with self.session.operator_lock:
            snapshot: dict[str, Any] = {
                "snapshot_id": f"dom-{uuid4().hex}", "timestamp": _now(),
                "active_window": {}, "windows": [], "browser": {},
                "elements": [], "evidence_refs": [], "errors": [],
            }
            try:
                if scope is not None and (not isinstance(scope, dict) or
                        set(scope) - {"ref", "snapshot_id", "role", "name"} or not scope):
                    raise ValueError("invalid_scope")
                page = await self.session.active_page(start_if_missing=False)
                if page is None:
                    snapshot["errors"].append("browser_not_running")
                    return snapshot
                if scope and scope.get("ref"):
                    scoped_node = await self._target(str(scope["ref"]), str(scope.get("snapshot_id", "")))
                    await scoped_node.dispose()
                self._page = page
                snapshot["browser"] = {"tab_id": self.session.tab_id(page), "url": page.url,
                                       "title": await page.title(), "session_id": self.session.session_id,
                                       "tabs": await self.session.list_tabs(), "snapshot_id": snapshot["snapshot_id"],
                                       "timestamp": snapshot["timestamp"]}
                self._epoch = self.session._operator_epoch
                # Let initial viewport/font work settle, bounded even in a background tab.
                await page.evaluate("() => Promise.race([new Promise(resolve => requestAnimationFrame(() => "
                                    "requestAnimationFrame(resolve))), new Promise(resolve => setTimeout(resolve, 120))])")
                handle = await page.evaluate_handle(_CAPTURE, {
                    "snapshotId": snapshot["snapshot_id"], "limit": max(1, min(int(limit), 200)),
                    "scope": scope, "previous": self._handle if scope and scope.get("ref") else None,
                    "filter": _filter,
                })
                await self._discard()
                self._handle = handle
                snapshot["elements"] = await self._handle.evaluate("state => state.elements")
                snapshot["browser"].update(await self._handle.evaluate(
                    "state => ({complete:state.complete, truncated:state.truncated, "
                    "elements_complete:state.complete && !state.truncated, active_dialog:state.activeDialog})"))
                snapshot["browser"]["tabs_complete"] = True
                for element in snapshot["elements"]:
                    element["metadata"].update({"session_id": self.session.session_id,
                                               "tab_id": snapshot["browser"]["tab_id"],
                                               "snapshot_id": snapshot["snapshot_id"]})
                await self._handle.evaluate("(state, id) => state.validateSnapshot(id)", snapshot["snapshot_id"])
                active = await self.session.active_page(start_if_missing=False)
                if (active is not page or self._epoch != self.session._operator_epoch
                        or page.url != snapshot["browser"]["url"]):
                    raise StaleDOMRef()
                self._snapshot = snapshot
            except Exception as exc:
                await self._discard()
                snapshot["elements"] = []
                error = next((code for code in ("stale_ref", "scope_ambiguous", "scope_not_found", "invalid_scope")
                              if code in str(exc)), "dom_unavailable")
                snapshot["errors"].append(error)
            self.session.release_operator_page_pin()
            return snapshot

    async def _target(self, ref: str, snapshot_id: str):
        await self._validate_session(snapshot_id)
        try:
            node = await self._handle.evaluate_handle("(state, args) => state.validate(args)",
                                                      {"ref": ref, "snapshot_id": snapshot_id})
            element = node.as_element()
            if element is None:
                await node.dispose()
                raise StaleDOMRef()
            return element
        except Exception as exc:
            raise StaleDOMRef() from exc

    async def _validate_session(self, snapshot_id: str) -> None:
        page = await self.session.active_page(start_if_missing=False)
        if (self._snapshot is None or self._handle is None or page is not self._page or page is None
                or self._epoch != self.session._operator_epoch
                or self._snapshot["snapshot_id"] != snapshot_id
                or page.url != self._snapshot["browser"]["url"]):
            raise StaleDOMRef()
        try:
            await self._handle.evaluate("(state, id) => state.validateSnapshot(id)", snapshot_id)
        except Exception as exc:
            raise StaleDOMRef() from exc

    async def act(self, action: str, **params: Any) -> dict[str, Any]:
        """Execution observations are not an independent mission verification.

        Native input uses retained ElementHandles (never re-resolved locators).
        The lock serializes UNI operations; page scripts can still run between
        Playwright protocol calls, so failed/ambiguous actions remain not_verified.
        """
        async with self.session.operator_lock:
            if action == "wait":
                milliseconds = max(0, min(int(params.get("milliseconds", 250)), 5000))
                await asyncio.sleep(milliseconds / 1000)
                return {"milliseconds": milliseconds, "observed_at": _now(), "status": "not_verified"}
            ref, snapshot_id = str(params.get("ref", "")), str(params.get("snapshot_id", ""))
            if params.get("tab_id") and (self._snapshot is None or
                    params["tab_id"] != self._snapshot["browser"].get("tab_id")):
                raise StaleDOMRef()
            if not ref:
                if action != "scroll":
                    raise ValueError("ref_required")
                await self._validate_session(snapshot_id)
                try:
                    observed = await self._handle.evaluate("""(state, args) => {
                        state.validateSnapshot(args.snapshot_id);
                        window.scrollBy({left:args.dx, top:args.dy, behavior:'instant'});
                        return {x:scrollX, y:scrollY};
                    }""", {"snapshot_id": snapshot_id,
                            "dx": max(-4000, min(int(params.get("delta_x", 0)), 4000)),
                            "dy": max(-4000, min(int(params.get("delta_y", 0)), 4000))})
                    return {"action": action, "scroll_observation": observed, "observed_at": _now(),
                            "status": "not_verified", "requires_fresh_snapshot": True}
                finally:
                    self.session.invalidate_operator_snapshot()
            node = await self._target(ref, snapshot_id)
            invalidate = action not in {"assert", "read"}
            guarded = action in {"click_ref", "press", "check_ref", "uncheck_ref", "download"}
            try:
                if action in {"assert", "read"}:
                    prop = str(params.get("property", ""))
                    if action == "assert" and (prop not in {"value", "checked", "text", "name", "enabled"}
                                               or "equals" not in params):
                        raise ValueError("assert_requires_property_and_equals")
                    # Separate, fresh read from the exact node, not cached/global page text.
                    observed = await self._handle.evaluate("(state, args) => state.observe(args)",
                                                          {"ref": ref, "snapshot_id": snapshot_id})
                    if action == "read":
                        return {"observed": observed, "ref": ref, "snapshot_id": snapshot_id,
                                "observed_at": _now(), "source": "dom", "untrusted": True,
                                "status": "not_verified"}
                    if observed["metadata"].get("sensitive") and prop == "value":
                        raise ValueError("sensitive_value_unavailable")
                    actual, expected = observed[prop], params["equals"]
                    matched = type(actual) is type(expected) and actual == expected
                    return {"assertion_passed": matched, "ref": ref, "snapshot_id": snapshot_id,
                            "property": prop, "expected": expected, "observed": actual,
                            "observed_at": _now(), "source": "dom", "untrusted": True,
                            "status": "not_verified"}
                observed = await self._handle.evaluate("(state, args) => state.observe(args)",
                                                      {"ref": ref, "snapshot_id": snapshot_id})
                if not observed["enabled"]:
                    raise ValueError("disabled_target")
                if guarded:
                    await self._handle.evaluate("(state, args) => state.armGuard(args)",
                                                {"ref": ref, "snapshot_id": snapshot_id})
                if action == "click_ref":
                    await node.click(timeout=5000)
                elif action == "fill_ref":
                    text = params.get("text", "")
                    if not isinstance(text, str) or len(text) > 100_000:
                        raise ValueError("invalid_text")
                    await node.fill(text, timeout=5000)
                elif action == "press":
                    key = params.get("key", "")
                    if not isinstance(key, str) or not key or len(key) > 80:
                        raise ValueError("invalid_key")
                    await node.press(key, timeout=5000)
                elif action == "select_ref":
                    value = params.get("value")
                    if not isinstance(value, (str, list)) or (isinstance(value, list) and
                            (len(value) > 100 or not all(isinstance(item, str) for item in value))):
                        raise ValueError("invalid_select_value")
                    await node.select_option(value=value, timeout=5000)
                elif action in {"check_ref", "uncheck_ref"}:
                    checked = False if action == "uncheck_ref" else params.get("checked")
                    if type(checked) is not bool:
                        raise ValueError("checked_must_be_boolean")
                    await node.set_checked(checked, timeout=5000)
                elif action == "hover_ref":
                    await node.hover(timeout=5000)
                elif action in {"scroll", "scroll_element"}:
                    dx = max(-4000, min(int(params.get("delta_x", 0)), 4000))
                    dy = max(-4000, min(int(params.get("delta_y", 0)), 4000))
                    await self._handle.evaluate("""(state, args) => {
                        const el = state.validate(args);
                        const target = args.targeted ? el : window;
                        target.scrollBy({left:args.dx, top:args.dy, behavior:'instant'});
                    }""", {"ref": ref, "snapshot_id": snapshot_id, "targeted": bool(params.get("ref")),
                            "dx": dx, "dy": dy})
                elif action == "upload":
                    paths = params.get("paths")
                    if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
                        raise ValueError("explicit_upload_paths_required")
                    files = []
                    for value in paths:
                        candidate = Path(str(value)).expanduser()
                        if not candidate.is_absolute() or not candidate.is_file():
                            raise ValueError("upload_path_must_be_existing_absolute_file")
                        files.append(str(candidate.resolve()))
                    await node.set_input_files(files, timeout=5000)
                    uploaded = await node.evaluate("""el => {
                        if (!el.isConnected || el.tagName !== 'INPUT' || el.type !== 'file')
                            throw Error('upload_target_unavailable_after_action');
                        return Array.from(el.files || []).map(file => ({name:file.name, size:file.size,
                            type:file.type, last_modified:file.lastModified}));
                    }""")
                    return {"action": action, "ref": ref, "snapshot_id": snapshot_id,
                            "file_observation": {"files": uploaded, "observed_at": _now(), "source": "input.files"},
                            "status": "not_verified", "requires_fresh_snapshot": True}
                elif action == "download":
                    return await self._download(node, ref, snapshot_id, params.get("path"))
                else:
                    raise ValueError("unsupported_dom_action")
                if guarded and await self._finish_guard():
                    raise StaleDOMRef()
                return {"action": action, "ref": ref, "snapshot_id": snapshot_id,
                        "observed_at": _now(), "status": "not_verified", "requires_fresh_snapshot": True}
            except Exception as exc:
                blocked = await self._finish_guard() if guarded else False
                if blocked or "stale_ref" in str(exc):
                    raise StaleDOMRef() from exc
                raise
            finally:
                if guarded:
                    await self._finish_guard()
                await node.dispose()
                if invalidate:
                    self.session.invalidate_operator_snapshot()

    async def _finish_guard(self) -> bool:
        try:
            return bool(await self._handle.evaluate("state => state.stopGuard()"))
        except Exception:
            return False  # The page may have navigated; navigation invalidates all refs.

    async def _download(self, node, ref: str, snapshot_id: str, raw_path: Any) -> dict[str, Any]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("explicit_download_path_required")
        path = Path(raw_path).expanduser()
        if not path.is_absolute() or not path.parent.is_dir():
            raise ValueError("download_requires_absolute_path_and_existing_parent")
        path = path.resolve()
        if path.exists():
            raise FileExistsError(str(path))
        # No placeholder is created before a real download event. A timeout or
        # popup/navigation is not evidence that the requested file exists.
        try:
            async with self._page.expect_download(timeout=15_000) as pending:
                await node.click(timeout=5000)
                if await self._finish_guard():
                    raise StaleDOMRef()
            download = await pending.value
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("download_event_missing_after_click_navigation_or_popup_not_a_download") from exc
        failure = await download.failure()
        if failure:
            raise RuntimeError(f"download_failed: {failure}")
        temporary = await download.path()
        if temporary is None:
            raise RuntimeError("download_file_unavailable")
        import shutil

        # Exclusive create also rejects a destination that appeared during the
        # click/download. save_as alone would silently overwrite that race.
        with path.open("xb") as output:
            with Path(temporary).open("rb") as source:
                await asyncio.to_thread(shutil.copyfileobj, source, output)
            output.flush()
        stat = path.stat()
        return {"action": "download", "ref": ref, "snapshot_id": snapshot_id,
                "download_event": {"url": download.url, "suggested_filename": download.suggested_filename,
                                   "failure": None},
                "file_observation": {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                     "observed_at": _now()},
                "status": "not_verified", "requires_fresh_snapshot": True}
