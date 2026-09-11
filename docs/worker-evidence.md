# Worker evidence

Evidence captured on 2026-09-11 on the local Apple Silicon development host. No credential, patient audio, signed URL, or private object path is retained here.

## Final source and container checks

- Test image: `sha256:a888064f0042222be6fa0d926df5f78b7675026bd26a1d1f0099ffda4c7002cb`, 478,785,382 bytes.
- Image-contained `pytest -q`: 33 passed after the final audio-size contract alignment.
- `python3 -m compileall -q worker/src worker/tests`: passed.
- `git diff --check -- worker docs/AUDIO_PIPELINE.md config/models.json config/astra-pricing.json`: passed at the worker handoff.
- The tests cover WAV/DSP boundaries, exact Astra request and token-count parity, fail-closed token accounting, reservation release and overage freeze paths, provider ambiguity, no-key behavior, raw-audio custody retry, lease loss, fixed runtime settings, and searchable PDF content.

## Real model runtime probe

The probe generated a ten-second signal in memory and used the checksum-verified artifacts in the Docker `ihear_models` volume. It wrote no audio file.

```json
{"architecture":"aarch64","cold_load_and_inference_seconds":1.73,"duration_seconds":10,"maximum_rss_mib":702.6,"silero_fraction":0.0,"silero_status":"ready","warm_inference_seconds":0.041,"yamnet_status":"ready","yamnet_top_category":"Busy signal"}
```

This is one local functional measurement, not a latency or memory guarantee. Silero's zero speech fraction and YAMNet's `Busy signal` label are expected model estimates for the synthetic 440 Hz tone, not fixture substitutions.

## PDF artifact

A 12-moment synthetic report rendered as eight A4 pages and 16,016 bytes. Visual inspection of the first, first evidence, and final pages confirmed searchable/wrapped evidence tables, fixed-axis actual RMS dBFS labels, follow-up and aid context, approved patient tips, limitations, method notes kept with their text, and intact footers. The artifact stayed far below the 4,000,000-byte delivery limit.

## Dependencies

`worker/dependency-licenses.json` inventories 53 direct and transitive production distributions from installed metadata. The one missing metadata field (`namex`) was resolved from its bundled Apache-2.0 license file. A package-vulnerability database audit was not run; the hash-locked versions therefore have reproducibility and license evidence, but no current vulnerability-database PASS claim. TensorFlow 2.18.1 remains pinned because this exact Python 3.11/aarch64 stack was exercised with the pinned YAMNet SavedModel; no broad dependency refresh was attempted without compatibility and vulnerability evidence.

## Evidence limits

The standalone worker checks do not prove browser behavior, Supabase policy behavior, production deployment, OpenAI credential availability, or a live paid Astra generation. Those remain separate integration and owner gates.
