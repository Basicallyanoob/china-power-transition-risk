"""Tests for the --scenario / --year command-line options.

These check the option handling only (no data download): `set_headline` swaps the
headline scenario-year in a copy of the config, rejects anything the config doesn't
model, and `parse_args` reads the options.
"""
from pathlib import Path

import pytest
import yaml

from transition_risk.__main__ import parse_args, set_headline

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text(encoding="utf-8"))


def test_no_options_keeps_config_headline():
    assert set_headline(CFG)["headline"] == CFG["headline"]


def test_override_scenario_and_year():
    out = set_headline(CFG, "delayed_transition", 2040)
    assert out["headline"] == {"scenario": "delayed_transition", "year": 2040}
    # The original config is not changed, so other code reading it is unaffected.
    assert CFG["headline"] == {"scenario": "net_zero", "year": 2030}


def test_override_one_keeps_the_other():
    assert set_headline(CFG, year=2035)["headline"] == {"scenario": CFG["headline"]["scenario"], "year": 2035}
    assert set_headline(CFG, scenario="current_policies")["headline"]["year"] == CFG["headline"]["year"]


@pytest.mark.parametrize("scenario, year, message", [
    ("net_zero_2050", None, "unknown scenario"),   # a name the config doesn't define
    (None, 2050, "not a study year"),              # outside study_years
])
def test_rejects_values_the_config_does_not_model(scenario, year, message):
    with pytest.raises(ValueError, match=message):
        set_headline(CFG, scenario, year)


def test_parse_args():
    args = parse_args(["--scenario", "net_zero", "--year", "2035"])
    assert args.scenario == "net_zero" and args.year == 2035 and args.out is None
    defaults = parse_args([])
    assert defaults.scenario is None and defaults.year is None
