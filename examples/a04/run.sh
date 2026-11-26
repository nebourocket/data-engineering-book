docker compose up -d --wait   # Redpanda (Kafka の部分だけ)
python examples/a04/make_table.py
pytest -q examples/a04
