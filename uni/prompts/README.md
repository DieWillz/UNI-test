# Папка с системными промптами для UNI Auto-Dev Council

Здесь собраны все системные промпты, необходимые для работы автономного цикла разработки UNI.

## Файлы

- **system_prompt_universal.txt** — общий контекст для всех ролей (архитектура, ограничения, правила).
- **system_prompt_advisor.txt** — промпт для Советников (DeepSeek, Qwen, Claude).
- **system_prompt_critic.txt** — промпт для Критика (Hermes).
- **system_prompt_executor.txt** — промпт для Исполнителя (Hermes).
- **system_prompt_hermes_critic_executor.txt** — дополнительный контекст для Hermes, когда он выполняет роли Критика или Исполнителя.

## Как использовать

1. **Для API-участников (DeepSeek, Qwen, Claude):**
   - Вставь `system_prompt_universal.txt` + `system_prompt_advisor.txt` в поле `system` промпта.
   - Передавай задачу и контекст в поле `user`.

2. **Для Hermes в роли Критика:**
   - Вставь `system_prompt_universal.txt` + `system_prompt_critic.txt` + `system_prompt_hermes_critic_executor.txt`.
   - Передай массив предложений от Советников в поле `user`.

3. **Для Hermes в роли Исполнителя:**
   - Вставь `system_prompt_universal.txt` + `system_prompt_executor.txt` + `system_prompt_hermes_critic_executor.txt`.
   - Передай утверждённый план в поле `user`.

## Важно

- Все промпты должны передаваться **в том же порядке**, в котором они указаны выше.
- Не изменяй текст промптов без согласования с архитектором проекта.
- Если роль меняется (например, Hermes становится Критиком, а затем Исполнителем), **меняй системный промпт полностью** — не используй один промпт для двух ролей одновременно.
