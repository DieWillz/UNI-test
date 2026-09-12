# Browser handoff — работа переключена на админку

2026-09-10. Браузерная задача прервана новым запросом координатора; статус общей приёмки: **not_verified**.

Изменены: `uni/browser_session.py`, `uni/operator/dom.py`, `browser_provider.py`, `browser_targeting.py`, `action_registry.py`, браузерные ветки `verifier.py`; `tests/operator/test_browser_provider.py`, `test_browser_dom.py`, `test_browser_verifier.py`, `test_browser_permissions.py`, `test_browser_acceptance.py`, `browser_fixtures.py`, `browser/playground.html`.

Interfaces: существующий BrowserSession + scoped DOM snapshots; ref+snapshot_id; semantic find/read/assert/wait/uncheck/scroll_element; browser.* aliases через существующий ActionRegistry; provider-owned last_action receipts; independent download stat; tab transitions; bounded pre-action scroll. Возможные внешние действия требуют external_effects permission. Raw ref без snapshot_id запрещён; postcondition по старому bare ref не подтверждается.

Последние завершённые прогоны (не общий green):
- provider + permissions: **15 passed**;
- verifier: **43 passed**, по выводу исполнителя;
- DOM: исполнитель сообщал **8 passed** до дополнительных race/scroll tests; итог последнего расширенного прогона не получен;
- реальные combined acceptance: **2 passed / 2 failed**. Download+independent stat и bounded scroll прошли. Form checkbox после fill получил stale_ref; switch_tab после popup вернул не ожидаемую активную вкладку. Эти две ошибки НЕ подтверждены исправленными.

Следующему владельцу browser: начать с двух failures в `test_browser_acceptance.py`; вероятные участки — DOM capture guard на change/blur предыдущего поля и выбор active_page по document.hasFocus. Не ослаблять stale-ref защиту ради зелёного теста. Затем проверить границы реального reconnect/replan и интеграцию MissionExecutor отдельно; этот слой здесь не менялся. Старые verifier fixtures без session/tab/snapshot/timestamp потребуют актуальных наблюдений, а не ослабления проверки.

Полный pytest, invariant checker, architecture audit, Dorch/Windows/Telegram проверки не запускались. Чужие изменения не откатывались; коммитов/пушей не было. Админка после переключения выполняется отдельным заданием, не является browser acceptance.
