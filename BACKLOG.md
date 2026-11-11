# Build backlog

One small task per day, worked top to bottom. Each task should take 20–45 minutes to review, run and commit.
Mark a task `[x]` when its commit is pushed. Tasks marked **(you)** need something only Michael can do, such as downloading a file or making a judgement call.

## Project 1 — china-power-transition-risk

### Make the model credible
- [x] Add `outputs/` regeneration check: a test that runs the pipeline on a 20-plant sample and checks columns and row counts
- [x] Add a sensitivity table: break-even effective price vs EBITDA margin (10/15/20%) and pass-through (0/10/30%)
- [x] Add a sensitivity chart for the table above and a README paragraph explaining it
- [ ] **(you)** Download NGFS Phase V carbon-price paths for China and the EU (current policies, delayed transition, net zero 2050) and save them to `data/ngfs/`
- [ ] Load NGFS paths from file into the scenario config; keep the illustrative set as a fallback
- [ ] Re-run with NGFS prices; update README findings and remove "illustrative" wording where it no longer applies
- [ ] **(you)** Decide the free-allocation path assumptions to pair with NGFS prices, and note your reasoning in the config
- [x] Add a `--scenario` and `--year` CLI option for the headline outputs

### Better economics
- [ ] **(you)** Find a sourced table of provincial coal benchmark on-grid tariffs and save it to `data/`
- [ ] Use provincial tariffs instead of one national tariff; add a test
- [ ] Allow a capacity-factor override per province (config + test)
- [ ] Add a "years to break-even" metric per plant under each scenario

### Polish
- [ ] Add type hints and docstrings to every public function
- [ ] Add a GitHub Actions workflow that runs `pytest` on every push
- [ ] Add a short `docs/methodology.md` with the equations and worked example for one plant
- [ ] Add a Chinese-language summary section (中文摘要) to the README
- [ ] Add a one-page PDF/PNG "credit note" summarising the findings for a lender audience
- [ ] Tag release v0.2 and write release notes

## Project 2 — tnfd-nature-risk-screener (starts Feb 2027)
- [ ] Scaffold the repo (README, package layout, config, tests)
- [ ] **(you)** Download WDPA (Protected Planet) and ENCORE files; record versions
- [ ] Load sites and protected areas; spatial intersect with buffers
- [ ] Join ENCORE sector dependency and impact ratings
- [ ] Priority list and heat-map outputs; README findings
