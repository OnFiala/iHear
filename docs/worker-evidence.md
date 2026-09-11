# Worker evidence

Evidence captured on 2026-09-11 on the local Apple Silicon development host. No credential, patient audio, signed URL, or private object path is retained here.

## Final source and container checks

- Integrated test image: `sha256:8c2a2652a32c3e9ae2befcf8604d8b8d58c74c76ff41a3998374a73dc157b9e3`, 478,789,426 bytes.
- Production image: `sha256:0435cb662b338d85118dc4afecd6b63dd2d04e1b546d3e0755e82a1dc764cf9d`, 476,172,854 bytes; command `python -m ihear_worker.main`.
- Image-contained `pytest -q`: 39 passed after final report-v2 integration. All 15 worker source/config file checksums match the running production container.
- `python3 -m compileall -q worker/src worker/tests`: passed.
- `git diff --check -- worker docs/AUDIO_PIPELINE.md config/models.json config/astra-pricing.json`: passed at the worker handoff.
- The tests cover WAV/DSP boundaries, exact Astra request and token-count parity, fail-closed token accounting, reservation release and overage freeze paths, provider ambiguity, no-key behavior, raw-audio custody retry, lease loss, fixed runtime settings, and searchable PDF content.

## Real model runtime probe

The integrated production-image probe generated a ten-second signal in memory and used the checksum-verified artifacts in the Docker `ihear_models` volume, mounted read-only. Docker enforced `--cpus=1 --memory=2g`. It wrote no audio file. These numbers supersede the earlier uncapped development-image timing.

```json
{"architecture":"aarch64","cold_load_and_inference_seconds":1.776,"duration_seconds":10,"maximum_rss_mib":685.9,"silero_fraction":0.0,"silero_status":"ready","warm_inference_seconds":0.105,"yamnet_status":"ready","yamnet_top_category":"Busy signal"}
```

This is one local functional measurement, not a latency or memory guarantee. Silero's zero speech fraction and YAMNet's `Busy signal` label are expected model estimates for the synthetic 440 Hz tone, not fixture substitutions.

## PDF artifact

The final template-v2 report generated from the two physical phone-test events has two A4 pages, 5,015 bytes and 1,907 extracted searchable characters. Both rendered pages were inspected: explicit illustrative/synthetic-use text, clinic timezone and local captured times, actual RMS values on a fixed axis, visible quality flags and unavailable/paused interpretation, intact tables and footers. The browser fixture report also passed searchable-label inspection. Empty/silent cases have no invented chart values. All generated artifacts remained private and far below the 4,000,000-byte delivery limit.

## Dependencies

`worker/dependency-licenses.json` inventories 53 direct and transitive production distributions from installed metadata. The one missing metadata field (`namex`) was resolved from its bundled Apache-2.0 license file. A package-vulnerability database audit was not run; the hash-locked versions therefore have reproducibility and license evidence, but no current vulnerability-database PASS claim. TensorFlow 2.18.1 remains pinned because this exact Python 3.11/aarch64 stack was exercised with the pinned YAMNet SavedModel; no broad dependency refresh was attempted without compatibility and vulnerability evidence.

## Evidence limits

The standalone worker checks do not prove browser behavior, Supabase policy behavior, production deployment, OpenAI credential availability, or a live paid Astra generation. Those remain separate integration and owner gates.
