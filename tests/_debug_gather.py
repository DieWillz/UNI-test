def test_debug_gather():
    import uni.webui.server as srv
    import uni.council.participants as P
    from pathlib import Path
    cfg = __import__("uni.config", fromlist=["load_config"]).load_config()
    print("\nDEBUG cfg hermes endpoint:", cfg.council.api_endpoints.get("hermes"))
    from uni.council._keys import resolve_endpoint
    print("DEBUG resolve hermes:", resolve_endpoint("hermes", cfg))
    parts = P.load_participants()
    print("DEBUG load_participants names:", [p.name for p in parts])
    gathered = srv._gather_participants()
    print("DEBUG gathered names:", sorted(p["name"] for p in gathered))
    print("DEBUG ROOT:", srv._ROOT)
    print("DEBUG cwd:", Path.cwd())
