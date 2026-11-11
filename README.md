# fontisan-python

The Python face of the [fontisan](https://github.com/fontist/fontisan) font
engine (fontist/fontisan#166). A setuptools package that rides the existing
fontisan C-ABI cdylib (`fontisan-rs`, the same one the Ruby `:ffi` tier uses)
through `ctypes`, shipped as per-platform package data
(`fontisan/lib/libfontisan.{so,dylib}` / `fontisan.dll`). No second engine, no
new FFI surface. Modeled on `parsanol/parsanol-python`.

> **Provisional.** The package name `fontisan-python` and the Python floor
> (`requires-python >= 3.9`) are placeholders. The PyPI name (`fontisan` vs
> `fontisan-python`) and the floor are owner decisions; nothing is published
> until they are stated. The import name is `fontisan`.

## Surface (this release)

```python
import fontisan

faces = fontisan.read(open("a.ttf", "rb").read(), metadata=False, lazy=False)  # one dict per face
reports = fontisan.audit(data, "a.ttf", validate=True)                         # audit report per face
rows = fontisan.scan("/fonts")          # file or directory, recursive, sorted
rows = fontisan.audit_dir("/fonts")     # {path, status ok|unsupported|error, reports|error}
fontisan.engine_rev()                   # fontisan-rs rev the cdylib was built from
fontisan.abi_version()                  # 1
```

Payloads cross the boundary as packed JSON rows, decoded once per call.

The C ABI also exposes `convert`, `extract`, `woff2_encode`, `subset` and
`instance`; this release does not bind them. They (and anything the ABI never
had) answer with an explicit `UnsupportedError` (`ErrorKind.UNSUPPORTED`).
dfont and Type 1 are not read natively by the engine and also raise
`UnsupportedError` from `read`/`audit`; `scan`/`audit_dir` report them as rows
with `status: "unsupported"`. Errors carry `kind` (`ErrorKind`, from
`error_kind`), and for read/audit failures the Ruby error surface
(`error_class`, `message`, `causes`).

## Engine pin

`ENGINE_REV` holds the fontisan-rs commit the cdylib is built from. The pinned
engine exports no rev symbol, so `scripts/stage_cdylib.py` stamps
`fontisan/lib/ENGINE_REV` next to the vendored library; the loader refuses a
cdylib whose stamp (or `fontisan_cdylib_engine_rev`, where a newer engine
exports it) differs from the pin, or whose ABI version is not 1.

## Develop

```sh
cargo build -p fontisan-ffi --release          # in a fontisan-rs checkout at ENGINE_REV
python scripts/stage_cdylib.py <fontisan-rs>/target/release/libfontisan.dylib
python scripts/corpus_fetch.py                 # shared fontisan corpus -> .corpus/fontisan
pip install -e . pytest && pytest -q -s
```

`FONTISAN_CDYLIB` points at a cdylib elsewhere; `FONTISAN_CORPUS_DIR` at an
existing corpus root (the directory that contains `corpus/`).

## Corpus parity

`tests/test_parity.py` replays the Ruby-tier goldens in
`fontist/fontisan` `corpus/` (pinned by `CORPUS_REV`) through the cdylib: read
(four mode/lazy variants), audit (default and validate), scan, the 17
malformed goldens, and a mixed-directory `audit_dir`/`scan` run. It is a port
of the comparison in fontisan-rs `tests/ffi_read_ops.rs`. The corpus is fetched,
not vendored; only the ci tier is used.

## Wheels and CI

`.github/workflows/wheels.yml` builds one wheel per platform (linux glibc and
musl x86_64, macOS arm64 and x64, windows x64), retags each with its real
platform tag, and smokes the installed wheel with the parity suite.
`ci.yml` runs the suite against a freshly built cdylib. Neither has been run
yet; only the local macOS arm64 build is verified.
