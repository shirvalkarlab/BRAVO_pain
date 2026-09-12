"""Review B10 (2026-09-12): no function in `bravo_service` imports a sibling by the bare
container-only spelling (`from modules.Biomarkers.routines import ...`). The file already imports
`availability` at module level under the package-relative spelling that works on both runners;
the four function-local copies of the bare spelling are gone, and `psd_lsb_model` is imported
package-relative. Read off the source so the next copy fails a test rather than a runner."""
import inspect

from .. import bravo_service as B


def test_no_bare_container_only_import_in_the_service():
    src = inspect.getsource(B)
    offenders = [ln.strip() for ln in src.splitlines()
                 if ln.strip().startswith("from modules.Biomarkers")]
    assert offenders == [], offenders


if __name__ == "__main__":
    test_no_bare_container_only_import_in_the_service()
    print("import spelling OK")
