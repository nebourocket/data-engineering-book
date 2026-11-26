pip install deltalake==1.6.6 "pyiceberg[sql-sqlite,pyarrow]==0.12.0" pyarrow==26.0.1 pytest
python examples/a03/demo.py
pytest -q examples/a03
