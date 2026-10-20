# Phase 3 benchmark baseline

This is the **baseline before tuning** for issue #135. The numbers are
engineering targets, not guarantees for every machine. Tuning and before/after
comparisons belong to #136.

## Reproduce it

The generator uses a fixed 24-month window (`2024-01-01` through `2025-12-31`)
and defaults to seed `20251019` and 500,000 data rows. The output is never
created in the repository unless the caller explicitly supplies such a path.
The documented local path is ignored by Git:

```sh
mkdir -p tmp_benchmarks
uv run python backend/scripts/generate_benchmark_data.py \
  --seed 20251019 --rows 500000 --output tmp_benchmarks/benchmark.csv
uv run python backend/scripts/benchmark.py \
  --input tmp_benchmarks/benchmark.csv --runs 5 \
  --json tmp_benchmarks/benchmark.json
```

The generator also supports `--without-customer-id` to measure the original
six-column import path. The runner measures validation plus import from a CSV
already on disk; HTTP upload transfer is excluded. It creates a fresh temporary
dataset directory and removes it on both success and failure. It measures
Overview, Products, Product detail, Customers and Projection through
`TestClient` with a bearer token. Projection is served by the Customers
endpoint after #132, so its response hash is intentionally the Customers body
hash for the same scenario.

## Baseline environment and input

Measured on 2026-10-19, before tuning:

- commit: `370589936fe0ea060ba239476506249a5031984d`
- CPU: 11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz, 4 logical CPUs
- RAM reported by `resource`: 439,160,832 bytes peak
- OS: Linux 6.18.33.2-microsoft-standard-WSL2 x86_64, WSL2
- Python: 3.12.7
- DuckDB: 1.5.6
- input: 500,000 rows, 26,357,436 bytes
- input SHA-256: `45615ab1f6c7fb761ceb5f084140654712b1cfc905d6c54253dc8628dbce7902`
- repetitions: 5

## First measured results

The import budget is 30 seconds, uncached module responses target 3 seconds,
and cached responses target 1 second. Median, minimum and maximum are in
seconds. The response hash is included so #136 can prove that tuning preserves
the result body.

| Operation | Scenario | Cache | Median | Min | Max | Budget | Within budget | Response SHA-256 |
| --- | --- | --- | ---: | ---: | ---: | ---: | :---: | --- |
| validate+import | all runs | uncached | 3.3170 | 3.1006 | 4.5838 | 30.0000 | yes | — |
| Overview | full previous period | uncached | 0.1391 | 0.1247 | 0.1459 | 3.0000 | yes | `24744df51675bc1af3b1b59974f57f502c8322227138b23a03494fa194d68a4b` |
| Overview | full previous period | cached | 0.0745 | 0.0640 | 0.1008 | 1.0000 | yes | `24744df51675bc1af3b1b59974f57f502c8322227138b23a03494fa194d68a4b` |
| Products | full previous period | uncached | 0.4173 | 0.3838 | 0.4304 | 3.0000 | yes | `83a6b11cf7c71ad6ffe2fe105336ea11b546e151899fa22a1ebf24c455742dda` |
| Products | full previous period | cached | 0.0660 | 0.0631 | 0.0856 | 1.0000 | yes | `83a6b11cf7c71ad6ffe2fe105336ea11b546e151899fa22a1ebf24c455742dda` |
| Product detail | full previous period | uncached | 0.2918 | 0.2473 | 0.3075 | 3.0000 | yes | `91f7fb616f8c83134f5296853b61d2ed5bc1adcad45abfa197b097a77c64e601` |
| Product detail | full previous period | cached | 0.0715 | 0.0641 | 0.0842 | 1.0000 | yes | `91f7fb616f8c83134f5296853b61d2ed5bc1adcad45abfa197b097a77c64e601` |
| Customers | full previous period | uncached | 0.6431 | 0.5848 | 0.7580 | 3.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Customers | full previous period | cached | 0.0653 | 0.0645 | 0.0800 | 1.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Projection | full previous period | uncached | 0.6109 | 0.5509 | 0.7974 | 3.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Projection | full previous period | cached | 0.0723 | 0.0668 | 0.0973 | 1.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Overview | full previous year | uncached | 0.1399 | 0.1320 | 0.1610 | 3.0000 | yes | `82d7fa03093a2b386087ce1ad72fe7a0edddddbaaebf9c7df48283c60b424e06` |
| Overview | full previous year | cached | 0.0739 | 0.0644 | 0.0795 | 1.0000 | yes | `82d7fa03093a2b386087ce1ad72fe7a0edddddbaaebf9c7df48283c60b424e06` |
| Products | full previous year | uncached | 0.3866 | 0.3819 | 0.4963 | 3.0000 | yes | `4ecc5696ed4a66c2b298b54e4db7f0673a21ee68c305f6613e0bd9f8d0c9ee2c` |
| Products | full previous year | cached | 0.0701 | 0.0627 | 0.1266 | 1.0000 | yes | `4ecc5696ed4a66c2b298b54e4db7f0673a21ee68c305f6613e0bd9f8d0c9ee2c` |
| Product detail | full previous year | uncached | 0.2727 | 0.2463 | 0.2957 | 3.0000 | yes | `101e7787d8a6efe18b33872851fe439f14b7fdcdd85f5b8d3285357e7cfdc5eb` |
| Product detail | full previous year | cached | 0.0688 | 0.0658 | 0.0757 | 1.0000 | yes | `101e7787d8a6efe18b33872851fe439f14b7fdcdd85f5b8d3285357e7cfdc5eb` |
| Customers | full previous year | uncached | 0.6064 | 0.5669 | 0.6695 | 3.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Customers | full previous year | cached | 0.0804 | 0.0612 | 0.1339 | 1.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Projection | full previous year | uncached | 0.6229 | 0.5708 | 0.6948 | 3.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Projection | full previous year | cached | 0.0694 | 0.0616 | 0.1041 | 1.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Overview | last 90 days, previous period | uncached | 0.1029 | 0.0959 | 0.1501 | 3.0000 | yes | `8b494e78a4a471996186fc1a89a5e111d1165cce7e0212b9ea5e344de25f2a62` |
| Overview | last 90 days, previous period | cached | 0.0642 | 0.0608 | 0.0694 | 1.0000 | yes | `8b494e78a4a471996186fc1a89a5e111d1165cce7e0212b9ea5e344de25f2a62` |
| Products | last 90 days, previous period | uncached | 0.1968 | 0.1683 | 0.2251 | 3.0000 | yes | `a88c9b396f29b350ff51c6cc5db2339e2e45d4ea4703b20a537867a7f53128d6` |
| Products | last 90 days, previous period | cached | 0.0800 | 0.0646 | 0.0840 | 1.0000 | yes | `a88c9b396f29b350ff51c6cc5db2339e2e45d4ea4703b20a537867a7f53128d6` |
| Product detail | last 90 days, previous period | uncached | 0.1294 | 0.1205 | 0.1403 | 3.0000 | yes | `57d6b5aabbfdaa7866938d8b9863b01036ab7a59c09aba1b9e987f8dd28909ac` |
| Product detail | last 90 days, previous period | cached | 0.0719 | 0.0626 | 0.0771 | 1.0000 | yes | `57d6b5aabbfdaa7866938d8b9863b01036ab7a59c09aba1b9e987f8dd28909ac` |
| Customers | last 90 days, previous period | uncached | 0.4847 | 0.4593 | 0.5721 | 3.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |
| Customers | last 90 days, previous period | cached | 0.0697 | 0.0649 | 0.0910 | 1.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |
| Projection | last 90 days, previous period | uncached | 0.5193 | 0.4657 | 0.6376 | 3.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |
| Projection | last 90 days, previous period | cached | 0.0670 | 0.0641 | 0.0773 | 1.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |

## After tuning / stability check (#136)

The After run used the same reference hardware, input bytes and five-run
runner. The Before and After response hashes are identical for all 30 module
rows (`same hashes: True`), so no result changed. The existing facts, SQL and
cache implementation already met the budgets with comfortable headroom; no
production query or schema rewrite was justified. The only changes in this
issue are the verification record and the legacy sample analytics test
expectations required by the two-year sample introduced in #134. Keeping the
facts date-independent and the cache unchanged avoids introducing a correctness
or isolation risk for a performance gain that is not needed yet.

After commit: `cb38217ccf7620b40b8e4269fadf8846e2909964`.

After environment was the same WSL2 reference machine (Python 3.12.7,
DuckDB 1.5.6, four logical CPUs). Peak resident memory reported by the
standard-library `resource` module was 406,609,920 bytes for the seven-column
run and 375,492,608 bytes for the six-column run.

| Operation | Scenario | Cache | Median | Min | Max | Budget | Within budget | Response SHA-256 |
| --- | --- | --- | ---: | ---: | ---: | ---: | :---: | --- |
| validate+import | all runs | uncached | 3.1048 | 2.8400 | 3.3439 | 30.0000 | yes | — |
| Overview | full previous period | uncached | 0.1413 | 0.1340 | 0.1806 | 3.0000 | yes | `24744df51675bc1af3b1b59974f57f502c8322227138b23a03494fa194d68a4b` |
| Overview | full previous period | cached | 0.0716 | 0.0691 | 0.0920 | 1.0000 | yes | `24744df51675bc1af3b1b59974f57f502c8322227138b23a03494fa194d68a4b` |
| Products | full previous period | uncached | 0.3763 | 0.3455 | 0.4350 | 3.0000 | yes | `83a6b11cf7c71ad6ffe2fe105336ea11b546e151899fa22a1ebf24c455742dda` |
| Products | full previous period | cached | 0.0670 | 0.0656 | 0.0747 | 1.0000 | yes | `83a6b11cf7c71ad6ffe2fe105336ea11b546e151899fa22a1ebf24c455742dda` |
| Product detail | full previous period | uncached | 0.2918 | 0.2420 | 0.3347 | 3.0000 | yes | `91f7fb616f8c83134f5296853b61d2ed5bc1adcad45abfa197b097a77c64e601` |
| Product detail | full previous period | cached | 0.0765 | 0.0661 | 0.0908 | 1.0000 | yes | `91f7fb616f8c83134f5296853b61d2ed5bc1adcad45abfa197b097a77c64e601` |
| Customers | full previous period | uncached | 0.6075 | 0.5849 | 0.9047 | 3.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Customers | full previous period | cached | 0.0697 | 0.0640 | 0.0752 | 1.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Projection | full previous period | uncached | 0.6838 | 0.5970 | 0.7674 | 3.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Projection | full previous period | cached | 0.0635 | 0.0629 | 0.0774 | 1.0000 | yes | `e26724414ac31fb64914ec9ddf3dd4b1073c537c1aa4690acd847a05ac97ef8e` |
| Overview | full previous year | uncached | 0.1421 | 0.1263 | 0.1604 | 3.0000 | yes | `82d7fa03093a2b386087ce1ad72fe7a0edddddbaaebf9c7df48283c60b424e06` |
| Overview | full previous year | cached | 0.0687 | 0.0608 | 0.0906 | 1.0000 | yes | `82d7fa03093a2b386087ce1ad72fe7a0edddddbaaebf9c7df48283c60b424e06` |
| Products | full previous year | uncached | 0.4186 | 0.4085 | 0.4682 | 3.0000 | yes | `4ecc5696ed4a66c2b298b54e4db7f0673a21ee68c305f6613e0bd9f8d0c9ee2c` |
| Products | full previous year | cached | 0.0768 | 0.0672 | 0.1125 | 1.0000 | yes | `4ecc5696ed4a66c2b298b54e4db7f0673a21ee68c305f6613e0bd9f8d0c9ee2c` |
| Product detail | full previous year | uncached | 0.2720 | 0.2502 | 0.3054 | 3.0000 | yes | `101e7787d8a6efe18b33872851fe439f14b7fdcdd85f5b8d3285357e7cfdc5eb` |
| Product detail | full previous year | cached | 0.0639 | 0.0633 | 0.0990 | 1.0000 | yes | `101e7787d8a6efe18b33872851fe439f14b7fdcdd85f5b8d3285357e7cfdc5eb` |
| Customers | full previous year | uncached | 0.6977 | 0.6181 | 0.8064 | 3.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Customers | full previous year | cached | 0.0693 | 0.0667 | 0.0956 | 1.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Projection | full previous year | uncached | 0.6123 | 0.5518 | 0.7720 | 3.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Projection | full previous year | cached | 0.0746 | 0.0658 | 0.0809 | 1.0000 | yes | `30897ec888a6cc6e70aa9d6e07653743932f5a87a096be5bafb847ff92b40413` |
| Overview | last 90 days, previous period | uncached | 0.1030 | 0.0938 | 0.1152 | 3.0000 | yes | `8b494e78a4a471996186fc1a89a5e111d1165cce7e0212b9ea5e344de25f2a62` |
| Overview | last 90 days, previous period | cached | 0.0723 | 0.0636 | 0.0781 | 1.0000 | yes | `8b494e78a4a471996186fc1a89a5e111d1165cce7e0212b9ea5e344de25f2a62` |
| Products | last 90 days, previous period | uncached | 0.1824 | 0.1711 | 0.2304 | 3.0000 | yes | `a88c9b396f29b350ff51c6cc5db2339e2e45d4ea4703b20a537867a7f53128d6` |
| Products | last 90 days, previous period | cached | 0.0666 | 0.0615 | 0.0734 | 1.0000 | yes | `a88c9b396f29b350ff51c6cc5db2339e2e45d4ea4703b20a537867a7f53128d6` |
| Product detail | last 90 days, previous period | uncached | 0.1186 | 0.1145 | 0.1247 | 3.0000 | yes | `57d6b5aabbfdaa7866938d8b9863b01036ab7a59c09aba1b9e987f8dd28909ac` |
| Product detail | last 90 days, previous period | cached | 0.0682 | 0.0621 | 0.0820 | 1.0000 | yes | `57d6b5aabbfdaa7866938d8b9863b01036ab7a59c09aba1b9e987f8dd28909ac` |
| Customers | last 90 days, previous period | uncached | 0.5126 | 0.4852 | 0.5713 | 3.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |
| Customers | last 90 days, previous period | cached | 0.0695 | 0.0676 | 0.0707 | 1.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |
| Projection | last 90 days, previous period | uncached | 0.4675 | 0.4569 | 0.5911 | 3.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |
| Projection | last 90 days, previous period | cached | 0.0666 | 0.0645 | 0.0824 | 1.0000 | yes | `a1116e0aa42d50048cad6b0be9d8f298ef662e808d457f18b6536ee83862139c` |

Additional #136 checks:

- The seven-column input has 500,000 rows and is 26,357,436 bytes. The five
  import samples had median 3.1048 s and maximum 3.3439 s.
- The six-column input is 23,304,814 bytes. Its five import samples had median
  2.8400 s and maximum 3.1140 s; all module medians also met their budgets.
- A five-run invalid-last-row rejection (the last date changed to
  `2027-01-02`) returned `ValidationResult` every time, with times
  2.2682–2.7007 s. The temporary dataset directory contained only its
  `uploads/` folder and no `.duckdb` file after each run.
- The largest recorded module outlier was 0.9048 s uncached; every single run
  therefore stayed below the 20% guard for its budget. `MAX_ROWS=500000` and
  `MAX_UPLOAD_BYTES=52428800` remain unchanged.
