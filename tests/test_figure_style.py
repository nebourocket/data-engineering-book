import importlib.util
import io
import logging
import warnings
from pathlib import Path

import matplotlib.pyplot as plt

STYLE = Path(__file__).resolve().parent.parent / "examples" / "figures" / "_style.py"


def load_style():
    spec = importlib.util.spec_from_file_location("_style", STYLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_japanese_title_renders_without_missing_glyph(caplog):
    style = load_style()
    with plt.rc_context():
        style.use_japanese_font()
        assert plt.rcParams["font.family"][0] == "Noto Sans CJK JP"
        assert plt.rcParams["axes.unicode_minus"] is False

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with caplog.at_level(logging.WARNING):
                fig, ax = plt.subplots()
                ax.set_title("売上の推移（月別）")
                ax.set_xlabel("月")
                fig.savefig(io.StringIO(), format="svg")
                plt.close(fig)

    messages = [str(w.message) for w in caught] + [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if "missing" in m], messages
