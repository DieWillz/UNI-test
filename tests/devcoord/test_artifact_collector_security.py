from __future__ import annotations

import pytest

from uni.devcoord.artifacts import ArtifactCollector


@pytest.mark.parametrize("name", [".env.local", ".env.production", ".env.dev"])
def test_dotenv_variants_are_rejected_as_secret_bearing(tmp_path, name: str) -> None:
    (tmp_path / name).write_text("SAFE_LOOKING=value", encoding="utf-8")

    with pytest.raises(ValueError, match="secret-bearing artifact"):
        ArtifactCollector(tmp_path).collect([name])
