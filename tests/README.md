# Focused regression tests

Run from the repository root. Python tests isolate the relevant functions and
do not require OCR dependencies or a browser. DOM tests use a captured,
account-free HKTicketing privilege dialog and synthetic codes, without making
requests to the ticketing website.

```sh
python -m unittest discover -s tests -p "test_*.py"
npm ci --prefix tests
npm test --prefix tests
```

The packaged cleanup test is optional: it runs only under CPython 3.11 when
`../settings.fixed.exe` exists. Otherwise it is reported as skipped.

## Windows release patch helpers

`build_scripts/patch_hkt_release.py` and `patch_settings_release.py` target the
known v2026.08.17 Windows executables only. They require CPython 3.11, verify the
original SHA256, refuse to overwrite output files, and preserve unrelated code.
Run from the distribution directory with a separate source checkout:

```sh
python source/build_scripts/patch_hkt_release.py nodriver_tixcraft.exe nodriver_tixcraft.fixed.exe
python source/build_scripts/patch_settings_release.py settings.exe settings.fixed.exe
```

The HKTicketing change reads the existing custom answer dictionary, fills only
the privilege form, and submits each page/title/answer combination once. It
does not infer or rotate eligibility codes. After rejection, correct the answer
and restart the bot. Normal pages continue through the existing flow.

Opening settings preserves all runtime state. An explicit bot launch still
clears only that instance's stale pause/stop flags. Historical temporary files
may remain on disk rather than risk deleting state owned by a running process.
