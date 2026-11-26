#!/bin/bash
# BigQuery でクエリを実行せずに、処理されるバイト数を見積もる（bq コマンドと自分のプロジェクトが要ります。本書のテストでは実行しません）
bq query --use_legacy_sql=false --dry_run \
  'SELECT sum(quantity * unit_price) FROM `my_project.neboske.sales` WHERE month = "2026-03"'
