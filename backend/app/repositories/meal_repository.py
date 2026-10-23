from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


KEMENKES_TKPI_2020 = "https://repository.kemkes.go.id/book/668"
REFERENCE_MEALS: tuple[dict[str, Any], ...] = (
    {
        "id": "seed-tkpi2020-ap001",
        "name": "Nasi putih, matang",
        "serving_label": "100 g nasi matang",
        "serving_grams": 100,
        "energy_kcal": 180,
        "protein_g": 3.0,
        "carbohydrate_g": 39.8,
        "fat_g": 0.3,
        "fiber_g": 0.2,
        "allergens": "",
        "notes": "Data dasar TKPI per 100 g BDD; kode AP001, sumber komposisi yang tercetak KZGPI-1990. Berat porsi adalah contoh takaran, bukan rekomendasi diet.",
        "source": "Kemenkes RI · TKPI 2020 · AP001",
        "source_url": KEMENKES_TKPI_2020,
    },
    {
        "id": "seed-tkpi2019-dp002",
        "name": "Bayam, rebus",
        "serving_label": "50 g bayam rebus",
        "serving_grams": 50,
        "energy_kcal": 11.5,
        "protein_g": 0.6,
        "carbohydrate_g": 1.85,
        "fat_g": 0.3,
        "fiber_g": 0.55,
        "allergens": "",
        "notes": "Basis TKPI 2019 per 100 g BDD: 23 kkal, protein 1,2 g, karbohidrat 3,7 g, lemak 0,6 g, serat 1,1 g. Porsi 50 g dihitung proporsional; halaman sumber sekunder mencantumkan Kemenkes/TKPI.",
        "source": "Kemenkes RI · TKPI 2019 · DP002 (salinan sekunder AndraFarm)",
        "source_url": "https://m.andrafarm.com/_andra.php?_i=daftar-tkpi&kmakan=DP002",
    },
    {
        "id": "seed-tkpi2019-jr006",
        "name": "Susu sapi segar",
        "serving_label": "200 ml (≈200 g)",
        "serving_grams": 200,
        "energy_kcal": 122,
        "protein_g": 6.4,
        "carbohydrate_g": 8.6,
        "fat_g": 7.0,
        "fiber_g": 0.0,
        "allergens": "Susu",
        "notes": "Basis TKPI 2019 per 100 g BDD: 61 kkal, protein 3,2 g, karbohidrat 4,3 g, lemak 3,5 g. Porsi 200 ml dihitung sebagai kira-kira 200 g; gunakan label produk untuk susu kemasan/varian berbeda. Halaman sumber sekunder mencantumkan Kemenkes/TKPI.",
        "source": "Kemenkes RI · TKPI 2019 · JR006 (salinan sekunder AndraFarm)",
        "source_url": "https://m.andrafarm.com/_andra.php?_i=daftar-tkpi&kmakan=JR006",
    },
    {
        "id": "seed-tkpi2019-er074",
        "name": "Pisang ambon, segar",
        "serving_label": "100 g bagian termakan",
        "serving_grams": 100,
        "energy_kcal": 108,
        "protein_g": 1.0,
        "carbohydrate_g": 24.3,
        "fat_g": 0.8,
        "fiber_g": 1.9,
        "allergens": "",
        "notes": "Nilai TKPI 2019 per 100 g BDD (bagian termakan); BDD buah utuh tercatat 75%. Berat porsi menghitung daging buah, tanpa kulit. Halaman sumber sekunder mencantumkan Kemenkes/TKPI.",
        "source": "Kemenkes RI · TKPI 2019 · ER074 (salinan sekunder AndraFarm)",
        "source_url": "https://m.andrafarm.com/_andra.php?_i=daftar-tkpi&kmakan=ER074",
    },
    {
        "id": "seed-tkpi2020-bp011",
        "name": "Ubi jalar kuning, kukus",
        "serving_label": "100 g ubi kukus",
        "serving_grams": 100,
        "energy_kcal": 100,
        "protein_g": 0.7,
        "carbohydrate_g": 23.8,
        "fat_g": 0.3,
        "fiber_g": 1.0,
        "allergens": "",
        "notes": "Dicocokkan dengan entri BP011 pada tabel umbi berpati TKPI 2020 (PDF resmi Kemenkes RI); sumber data tercetak KZGPI-1990. Nilai per 100 g BDD; bumbu atau bahan tambahan tidak dihitung.",
        "source": "Kemenkes RI · TKPI 2020 · BP011",
        "source_url": KEMENKES_TKPI_2020,
    },
    {
        "id": "seed-tkpi2020-ap029",
        "name": "Biskuit, contoh TKPI",
        "serving_label": "20 g (timbang sesuai produk)",
        "serving_grams": 20,
        "energy_kcal": 91.4,
        "protein_g": 1.38,
        "carbohydrate_g": 15.02,
        "fat_g": 2.88,
        "fiber_g": 0.02,
        "allergens": "Periksa label produk",
        "notes": "Basis TKPI 2020 per 100 g BDD: 457 kkal, protein 6,9 g, karbohidrat 75,1 g, lemak 14,4 g, serat 0,1 g. Porsi contoh 20 g dihitung proporsional; jenis/merek dan alergen biskuit berbeda, label kemasan harus diutamakan.",
        "source": "Kemenkes RI · TKPI 2020 · AP029",
        "source_url": KEMENKES_TKPI_2020,
    },
)


class MealRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meal_catalog (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    serving_label TEXT NOT NULL,
                    serving_grams REAL NOT NULL,
                    energy_kcal REAL NOT NULL,
                    protein_g REAL NOT NULL,
                    carbohydrate_g REAL NOT NULL,
                    fat_g REAL NOT NULL,
                    fiber_g REAL NOT NULL,
                    allergens TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'Sumber belum dicantumkan',
                    source_url TEXT NOT NULL DEFAULT '',
                    organization_id TEXT
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(meal_catalog)")}
            for column, column_type in {
                "source": "TEXT NOT NULL DEFAULT 'Sumber belum dicantumkan'",
                "source_url": "TEXT NOT NULL DEFAULT ''",
                "organization_id": "TEXT",
            }.items():
                if column not in columns:
                    connection.execute(f"ALTER TABLE meal_catalog ADD COLUMN {column} {column_type}")
            # Custom legacy entries are attributed only when the author has one active daycare.
            connection.execute(
                """UPDATE meal_catalog SET organization_id = (
                       SELECT MIN(organization_id) FROM organization_memberships
                       WHERE user_id = meal_catalog.created_by AND status = 'active'
                       GROUP BY user_id HAVING COUNT(*) = 1
                   ) WHERE created_by != 'system-reference' AND organization_id IS NULL"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_meal_catalog_active_created ON meal_catalog(active, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_meal_catalog_org_active ON meal_catalog(organization_id, active, name COLLATE NOCASE)"
            )
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for item in REFERENCE_MEALS:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO meal_catalog (
                        id, name, serving_label, serving_grams, energy_kcal, protein_g,
                        carbohydrate_g, fat_g, fiber_g, allergens, notes, active,
                        created_by, created_at, source, source_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'system-reference', ?, ?, ?)
                    """,
                    (
                        item["id"], item["name"], item["serving_label"], item["serving_grams"],
                        item["energy_kcal"], item["protein_g"], item["carbohydrate_g"],
                        item["fat_g"], item["fiber_g"], item["allergens"], item["notes"],
                        created_at, item["source"], item["source_url"],
                    ),
                )

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "serving_label": row["serving_label"],
            "serving_grams": row["serving_grams"],
            "energy_kcal": row["energy_kcal"],
            "protein_g": row["protein_g"],
            "carbohydrate_g": row["carbohydrate_g"],
            "fat_g": row["fat_g"],
            "fiber_g": row["fiber_g"],
            "allergens": row["allergens"],
            "notes": row["notes"],
            "source": row["source"] if "source" in row.keys() else "Sumber belum dicantumkan",
            "source_url": row["source_url"] if "source_url" in row.keys() else "",
            "created_by": row["created_by"],
            "organization_id": row["organization_id"] if "organization_id" in row.keys() else None,
            "created_at": row["created_at"],
        }

    def create(self, payload: dict[str, Any], created_by: str, organization_id: str) -> dict[str, Any]:
        record = {
            "id": f"meal-{uuid4().hex[:12]}",
            **payload,
            "organization_id": organization_id,
            "source": payload.get("source") or "Sumber belum dicantumkan",
            "source_url": payload.get("source_url") or "",
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO meal_catalog (
                    id, name, serving_label, serving_grams, energy_kcal, protein_g,
                    carbohydrate_g, fat_g, fiber_g, allergens, notes, created_by,
                    created_at, source, source_url, organization_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["name"], record["serving_label"], record["serving_grams"],
                    record["energy_kcal"], record["protein_g"], record["carbohydrate_g"],
                    record["fat_g"], record["fiber_g"], record["allergens"], record["notes"],
                    record["created_by"], record["created_at"], record["source"], record["source_url"],
                    record["organization_id"],
                ),
            )
        return record

    def list_active(self, organization_ids: list[str]) -> list[dict[str, Any]]:
        organization_ids = list(dict.fromkeys(organization_ids))
        with self._connect() as connection:
            if organization_ids:
                placeholders = ",".join("?" for _ in organization_ids)
                rows = connection.execute(
                    f"""SELECT * FROM meal_catalog WHERE active = 1
                        AND (created_by = 'system-reference' OR organization_id IN ({placeholders}))
                        ORDER BY name COLLATE NOCASE, created_at DESC""",
                    tuple(organization_ids),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM meal_catalog WHERE active = 1 AND created_by = 'system-reference' ORDER BY name COLLATE NOCASE, created_at DESC"
                ).fetchall()
        return [self._serialize(row) for row in rows]

    def get_active(self, meal_id: str, organization_ids: list[str]) -> dict[str, Any] | None:
        organization_ids = list(dict.fromkeys(organization_ids))
        with self._connect() as connection:
            if organization_ids:
                placeholders = ",".join("?" for _ in organization_ids)
                row = connection.execute(
                    f"""SELECT * FROM meal_catalog WHERE id = ? AND active = 1
                        AND (created_by = 'system-reference' OR organization_id IN ({placeholders}))""",
                    (meal_id, *organization_ids),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM meal_catalog WHERE id = ? AND active = 1 AND created_by = 'system-reference'",
                    (meal_id,),
                ).fetchone()
        return self._serialize(row) if row else None
