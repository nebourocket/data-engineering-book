#!/bin/bash
# 第 11 章: PostgreSQL でマテリアライズドビューと GRANT を試す（リポジトリの直下で、compose.yaml のサービスを起動してから）
# docker compose up -d --wait
PSQL="docker compose exec -T postgres psql -U deb -d deb"

$PSQL -f - < examples/b11/setup_pg.sql
$PSQL -f - < examples/b11/matview_flow.sql
$PSQL -f - < examples/b11/grant_pg.sql
$PSQL -f - < examples/b11/cleanup_pg.sql
