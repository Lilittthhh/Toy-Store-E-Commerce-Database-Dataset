from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]


def test_combined_launcher_exposes_only_web_ports_to_lan() -> None:
    launcher = (APP_ROOT / "scripts" / "run_web.ps1").read_text(encoding="utf-8")

    assert '"--host", "0.0.0.0", "--port", "8000"' in launcher
    assert "--server.address 0.0.0.0 --server.port 8501" in launcher
    assert '$localHealthUrl = "http://127.0.0.1:8000/health"' in launcher
    assert "5432" not in launcher


def test_streamlit_and_example_environment_are_lan_safe() -> None:
    streamlit_config = (APP_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    example_env = (APP_ROOT / ".env.example").read_text(encoding="utf-8")
    api_client = (APP_ROOT / "frontend" / "api_client.py").read_text(encoding="utf-8")

    assert 'address = "0.0.0.0"' in streamlit_config
    assert "port = 8501" in streamlit_config
    assert "PGHOST=localhost" in example_env
    assert "API_BASE_URL=http://HOST_IP:8000" in example_env
    assert "http://127.0.0.1:8000" not in api_client
