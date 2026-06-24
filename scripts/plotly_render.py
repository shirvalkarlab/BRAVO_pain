"""Render a Plotly figure to PNG inside the agent sandbox (darwin).

Proven recipe (2026-06-22): the macOS app Chrome aborts under the sandbox and kaleido 1.x
cannot download Chrome-for-Testing, so pin kaleido==0.2.1 (bundles chromium, honors chromium_args)
and pass --no-zygote/--single-process. Usage:

    from scripts.plotly_render import render_png
    render_png(fig, "out.png", width=1500, height=820)
"""
import os


def render_png(fig, path, width=1500, height=820, scale=1):
    os.makedirs("/tmp/choreo_home", exist_ok=True)
    os.environ.setdefault("HOME", "/tmp/choreo_home")
    import plotly.io as pio
    # kaleido v0 flag API (removed in 1.x); requires `pip install kaleido==0.2.1`.
    pio.kaleido.scope.chromium_args = (
        "--single-process", "--no-zygote", "--no-sandbox",
        "--disable-gpu", "--disable-dev-shm-usage",
    )
    pio.write_image(fig, path, width=width, height=height, scale=scale)
    return path
