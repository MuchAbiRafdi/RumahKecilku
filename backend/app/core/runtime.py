from __future__ import annotations

import os
from dataclasses import dataclass


_APP_ENVIRONMENTS = {"development", "preview", "production"}
_DEFAULT_PREVIEW_HOSTS = ("localhost", "127.0.0.1", "testserver", "*.e2b.app")
MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024

PRODUCTION_BLOCKERS = (
    "akun dokter/pengasuh dan relasi keluarga belum diverifikasi atau dikelola melalui undangan institusi",
    "akses data belum diisolasi per daycare/organisasi dan kepemilikan anak secara menyeluruh",
    "SQLite dan foto tersimpan tanpa enkripsi aplikasi at-rest atau pengelolaan kunci produksi",
    "persetujuan, retensi/penghapusan, serta audit tahan perubahan belum lengkap",
    "MFA, pemulihan akun, pemantauan keamanan, dan uji penetrasi belum tersedia",
)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise RuntimeError(f"Nilai {name} harus berupa true/false.")


@dataclass(frozen=True)
class RuntimeSettings:
    app_env: str
    demo_mode: bool
    demo_sample_data: bool
    browser_session_token: bool
    allowed_hosts: tuple[str, ...]
    max_request_body_bytes: int = MAX_REQUEST_BODY_BYTES

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        app_env = os.getenv("RUMAH_APP_ENV", "development").strip().lower()
        if app_env not in _APP_ENVIRONMENTS:
            raise RuntimeError("RUMAH_APP_ENV harus development, preview, atau production.")

        demo_mode = env_flag("RUMAH_DEMO_MODE", default=False)
        demo_sample_data = env_flag("RUMAH_DEMO_SAMPLE_DATA", default=False)
        if demo_sample_data and not (app_env == "preview" and demo_mode):
            raise RuntimeError("Data observasi sintetis hanya boleh diaktifkan pada preview dengan RUMAH_DEMO_MODE=1.")
        browser_session_token = env_flag("RUMAH_BROWSER_SESSION_TOKEN", default=False)
        if browser_session_token and not (app_env == "preview" and demo_mode):
            raise RuntimeError(
                "Bearer token browser hanya boleh diaktifkan pada preview berisi data sintetis."
            )

        if app_env == "production":
            blockers = "; ".join(PRODUCTION_BLOCKERS)
            raise RuntimeError(
                "Startup produksi ditolak: Rumah Kecilku belum lulus kesiapan keamanan untuk data sensitif. "
                f"Selesaikan dahulu: {blockers}."
            )

        configured_hosts = os.getenv("RUMAH_ALLOWED_HOSTS", "").strip()
        allowed_hosts = tuple(
            host.strip()
            for host in configured_hosts.split(",")
            if host.strip()
        ) or _DEFAULT_PREVIEW_HOSTS
        if "*" in allowed_hosts:
            raise RuntimeError("RUMAH_ALLOWED_HOSTS tidak boleh menggunakan wildcard '*'.")

        return cls(
            app_env=app_env,
            demo_mode=demo_mode,
            demo_sample_data=demo_sample_data,
            browser_session_token=browser_session_token,
            allowed_hosts=allowed_hosts,
        )
