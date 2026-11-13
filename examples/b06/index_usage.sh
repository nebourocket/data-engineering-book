#!/bin/bash
# 第 6 章: インデックスの実験（DuckDB はメモリ上、PostgreSQL は PG_DSN の接続先）
python examples/b06/run_index.py duckdb
PG_DSN=postgresql://deb:deb@localhost:5432/deb python examples/b06/run_index.py postgres
