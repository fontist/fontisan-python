# fontisan-python

The Python face of the [fontisan](https://github.com/fontist/fontisan) font
engine (fontist/fontisan#166). A setuptools package that rides the existing
Ruby `:ffi` tier’s C-ABI cdylib (`fontist/fontisan`
`ext/fontisan_cdylib`) through `ctypes`, shipped as per-platform package data
(`fontisan/lib/libfontisan_cdylib.{so,dylib}` / `fontisan_cdylib.dll`).
Modeled on `parsanol/parsanol-python`.

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

`FONTISAN_REV` pins the `fontist/fontisan` source commit containing
`ext/fontisan_cdylib`. Its `Cargo.toml` pins the `fontist/fontisan-rs` engine
dependency. `ENGINE_REV` and `src/fontisan/_engine.py` are generated from that
dependency using `scripts/stage_cdylib.py --update-engine-rev`; do not edit
them by hand.

Staging requires a checkout at `FONTISAN_REV` with its committed Cargo.toml,
checks that both generated engine pins match the dependency, and loads the
built binary to check its `fontisan_cdylib_engine_rev` export before copying
it. The runtime loader also requires that export to match `ENGINE_REV` and
requires ABI version 1. There is no revision stamp file.

## Develop

Building requires Rust and Cargo. The binding tests also require `rustc` on
`PATH` to compile small cdylib fixtures for revision-validation checks.

```sh
git clone https://github.com/fontist/fontisan /tmp/fontisan-source
git -C /tmp/fontisan-source checkout "$(cat FONTISAN_REV)"
cargo build --release --manifest-path /tmp/fontisan-source/ext/fontisan_cdylib/Cargo.toml
# macOS; use libfontisan_cdylib.so on Linux or fontisan_cdylib.dll on Windows
python scripts/stage_cdylib.py --fontisan-source /tmp/fontisan-source \
  /tmp/fontisan-source/ext/fontisan_cdylib/target/release/libfontisan_cdylib.dylib
python scripts/corpus_fetch.py                 # shared fontisan corpus -> .corpus/fontisan
pip install -e . pytest && pytest -q -s
```

To change the source pin, update `FONTISAN_REV`, check out that commit, then
regenerate the engine pins before building and staging:

```sh
python scripts/stage_cdylib.py --fontisan-source /tmp/fontisan-source --update-engine-rev
```

The generator and staging script support Python 3.9 without a TOML package.
They expect the pinned crate’s inline Git dependency declaration and fail if
upstream changes that layout.

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
`ci.yml` runs the suite against a freshly built cdylib. Both workflows check
out `fontist/fontisan` at `FONTISAN_REV`, build `ext/fontisan_cdylib`, and
verify the binary and Cargo dependency pin during staging. The wheels
workflow also runs when `FONTISAN_REV` changes.
