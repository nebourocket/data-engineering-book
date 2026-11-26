"""第8章: 組み立てたイベントを、OpenLineage 公式の JSON Schema (2-0-2) で検査します。ネットワークが要るので pytest には入れません。"""
import json
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

sys.path.insert(0, str(Path(__file__).parent))
import lineage_events  # noqa: E402

ROOT_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json"
FACET_URL = "https://openlineage.io/spec/facets/1-1-1/SchemaDatasetFacet.json"


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as res:
        return Resource.from_contents(json.load(res))


if __name__ == "__main__":
    registry = Registry().with_resources([(ROOT_URL, fetch(ROOT_URL)), (FACET_URL, fetch(FACET_URL))])
    validator = Draft202012Validator({"$ref": f"{ROOT_URL}#/$defs/RunEvent"}, registry=registry,
                                     format_checker=Draft202012Validator.FORMAT_CHECKER)
    events = lineage_events.one_night()
    errors = [e.message for ev in events for e in validator.iter_errors(ev)]
    print(f"{len(events)} events, official schema errors: {len(errors)}")
